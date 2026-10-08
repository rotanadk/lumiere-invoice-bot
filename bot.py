import logging
import os
import tempfile

from telegram import Update
from telegram.constants import ChatType, ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from db import (
    create_order,
    get_invoice_topic,
    get_order,
    get_order_topic,
    init_db,
    mark_order,
    next_invoice_no,
    save_invoice_topic,
    save_order_topic,
    source_message_exists,
)
from invoice import create_invoice
from parser import parse_order
from sheets import sync_order_to_sheets

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("lumiere_invoice_bot")


async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    return member.status in ("administrator", "creator")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == ChatType.PRIVATE:
        await update.message.reply_text(
            "Lumiere Invoice Bot is ready.\n\n"
            "1) In the Drop Order topic send /setup_orders\n"
            "2) In the Invoice topic send /setup_invoices\n\n"
            "After that, new orders are converted to PDF invoices automatically."
        )


async def _validate_topic_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if update.effective_chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await msg.reply_text("Please use this command inside a Telegram group topic.")
        return None
    if not await is_admin(update, context):
        await msg.reply_text("Only a group admin can run this setup command.")
        return None
    if not msg.message_thread_id:
        await msg.reply_text("Please run this command inside a topic, not the main group chat.")
        return None
    return msg


async def setup_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await _validate_topic_setup(update, context)
    if not msg:
        return
    save_order_topic(update.effective_chat.id, msg.message_thread_id)
    await msg.reply_text(
        "✅ <b>Order topic connected.</b>\n"
        "New valid orders posted here will be converted automatically.\n"
        "The bot will not post invoice previews in this topic.",
        parse_mode=ParseMode.HTML,
    )


# Keep /setup working as an alias for the source order topic.
async def setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await setup_orders(update, context)


async def setup_invoices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await _validate_topic_setup(update, context)
    if not msg:
        return
    save_invoice_topic(update.effective_chat.id, msg.message_thread_id)
    await msg.reply_text(
        "✅ <b>Invoice topic connected.</b>\n"
        "Automatically generated PDF invoices will be sent to this topic.",
        parse_mode=ParseMode.HTML,
    )


def order_total(order):
    return sum(float(item["amount"]) for item in order["items"])


async def handle_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.text or msg.text.startswith("/"):
        return

    source = get_order_topic()
    destination = get_invoice_topic()
    if not source or not destination:
        return

    source_chat, source_topic = source
    if update.effective_chat.id != source_chat or msg.message_thread_id != source_topic:
        return

    # Avoid duplicate invoices if Telegram retries an update or Railway restarts.
    if source_message_exists(update.effective_chat.id, msg.message_thread_id, msg.message_id):
        return

    dest_chat, dest_topic = destination

    try:
        parsed = parse_order(msg.text)
    except ValueError as e:
        # Keep Drop Order clean. Put parsing problems in the invoice topic instead.
        try:
            await context.bot.send_message(
                chat_id=dest_chat,
                message_thread_id=dest_topic,
                text=(
                    "⚠️ <b>Invoice not generated</b>\n"
                    f"I couldn't understand order message #{msg.message_id}.\n"
                    f"Reason: {e}\n\n"
                    f"<code>{msg.text[:1200]}</code>"
                ),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            log.exception("Could not report parsing error to invoice topic")
        return

    # Save every parsed transaction to Google Sheets.
    # If the Sheet sync fails, keep Drop Order clean and report only in Invoice topic.
    try:
        sheet_result = await sync_order_to_sheets(msg, parsed, update.effective_user)
        if sheet_result.get("disabled"):
            log.warning("Order parsed, but Google Sheets integration is not configured yet.")
    except Exception as e:
        log.exception("Google Sheets sync failed for message_id=%s", msg.message_id)
        try:
            await context.bot.send_message(
                chat_id=dest_chat,
                message_thread_id=dest_topic,
                text=(
                    "⚠️ <b>Google Sheet not updated</b>\n"
                    f"Order message #{msg.message_id} was parsed, and the invoice will still be generated.\n"
                    f"Reason: <code>{str(e)[:700]}</code>"
                ),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

    order_id = create_order(
        update.effective_chat.id,
        msg.message_thread_id,
        msg.message_id,
        parsed,
        msg.text,
        update.effective_user.id if update.effective_user else None,
    )
    order = get_order(order_id)

    invoice_no = next_invoice_no(order.get("order_no"))
    tmp_dir = tempfile.mkdtemp(prefix="lumiere_invoice_")
    filename = f"Lumiere_Invoice_{invoice_no}.pdf"
    path = os.path.join(tmp_dir, filename)

    try:
        create_invoice(order, invoice_no, path)
        total = order_total(order)
        with open(path, "rb") as f:
            await context.bot.send_document(
                chat_id=dest_chat,
                message_thread_id=dest_topic,
                document=f,
                filename=filename,
                caption=(
                    f"🧾 Invoice #{invoice_no} — {order['customer']}\n"
                    f"Total: ${total:,.2f}"
                ),
            )
        mark_order(order_id, "generated", invoice_no)
    except Exception:
        mark_order(order_id, "failed")
        log.exception("Invoice generation failed for order_id=%s", order_id)
        try:
            await context.bot.send_message(
                chat_id=dest_chat,
                message_thread_id=dest_topic,
                text=f"❌ Failed to generate Invoice #{invoice_no}. Check Railway logs.",
            )
        except Exception:
            pass


async def error_handler(update, context):
    log.exception("Unhandled error", exc_info=context.error)


def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN is missing. Add it in Railway Variables.")

    init_db()
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setup", setup))
    app.add_handler(CommandHandler("setup_orders", setup_orders))
    app.add_handler(CommandHandler("setup_invoices", setup_invoices))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_order))
    app.add_error_handler(error_handler)

    log.info("Starting Lumiere Invoice Bot in AUTO mode with long polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
