import logging
import os
import tempfile

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType, ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from db import (
    create_order,
    get_order,
    get_setup,
    init_db,
    mark_order,
    next_invoice_no,
    save_setup,
    set_preview_message,
    update_order,
)
from invoice import create_invoice
from parser import parse_order

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("lumiere_invoice_bot")


def preview_text(order):
    lines = ["🧾 <b>Invoice preview</b>"]
    if order.get("order_no"):
        lines.append(f"Order: <b>#{order['order_no']}</b>")
    lines.append(f"Customer: <b>{order['customer']}</b>")
    lines.append("")
    total = 0.0
    for item in order["items"]:
        total += float(item["amount"])
        lines.append(
            f"• <b>{item['product']}</b> — {item['qty_display']} × ${item['unit_price']:.2f} = <b>${item['amount']:.2f}</b>"
        )
    lines.append("")
    lines.append(f"Payment: <b>{order.get('payment_status') or 'Unpaid'}</b>" +
                 (f" ({order['payment_method']})" if order.get("payment_method") else ""))
    lines.append(f"Total: <b>${total:.2f}</b>")
    lines.append("")
    lines.append("Check the details before generating the PDF.")
    return "\n".join(lines)


def buttons(order_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Generate Invoice", callback_data=f"gen:{order_id}")],
        [InlineKeyboardButton("✏️ Edit", callback_data=f"edit:{order_id}"),
         InlineKeyboardButton("❌ Cancel", callback_data=f"cancel:{order_id}")],
    ])


async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    return member.status in ("administrator", "creator")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == ChatType.PRIVATE:
        await update.message.reply_text(
            "Lumiere Invoice Bot is ready. Add me to your Telegram group, make me admin, "
            "then open the Drop Order topic and send /setup."
        )


async def setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if update.effective_chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await msg.reply_text("Please use /setup inside your Telegram group topic.")
        return
    if not await is_admin(update, context):
        await msg.reply_text("Only a group admin can run /setup.")
        return
    topic_id = msg.message_thread_id
    if not topic_id:
        await msg.reply_text("Please open the Drop Order topic and send /setup inside that topic.")
        return

    save_setup(update.effective_chat.id, topic_id)
    await msg.reply_text(
        "✅ <b>Lumiere Invoice Bot connected.</b>\n\n"
        "I will only read order messages in this topic.\n"
        "Example:\n<code>37: Prime : LV55 10kg (14.5$)</code>",
        parse_mode=ParseMode.HTML,
    )


async def handle_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.text or msg.text.startswith("/"):
        return

    setup_value = get_setup()
    if not setup_value:
        return
    configured_chat, configured_topic = setup_value
    if update.effective_chat.id != configured_chat or msg.message_thread_id != configured_topic:
        return

    # If this user is currently editing an order, replace that pending order.
    editing_order_id = context.user_data.pop("editing_order_id", None)
    try:
        parsed = parse_order(msg.text)
    except ValueError as e:
        if editing_order_id:
            context.user_data["editing_order_id"] = editing_order_id
        await msg.reply_text(
            "⚠️ I couldn't read this order yet.\n"
            f"{e}\n\n"
            "Try this format:\n"
            "<code>37: Prime : LV55 10kg (14.5$)</code>\n\n"
            "For multiple items, put one item on each line.",
            parse_mode=ParseMode.HTML,
        )
        return

    if editing_order_id:
        update_order(editing_order_id, parsed, msg.text)
        order = get_order(editing_order_id)
        preview_id = order.get("preview_message_id")
        if preview_id:
            try:
                await context.bot.edit_message_text(
                    chat_id=order["telegram_chat_id"],
                    message_id=preview_id,
                    text=preview_text(order),
                    parse_mode=ParseMode.HTML,
                    reply_markup=buttons(editing_order_id),
                )
            except Exception:
                pass
        await msg.reply_text("✅ Order updated. Check the invoice preview above.")
        return

    order_id = create_order(
        update.effective_chat.id,
        msg.message_thread_id,
        msg.message_id,
        parsed,
        msg.text,
        update.effective_user.id,
    )
    order = get_order(order_id)
    preview = await msg.reply_text(
        preview_text(order),
        parse_mode=ParseMode.HTML,
        reply_markup=buttons(order_id),
    )
    set_preview_message(order_id, preview.message_id)


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    action, order_id_s = q.data.split(":", 1)
    order_id = int(order_id_s)
    order = get_order(order_id)
    if not order:
        await q.edit_message_text("This order no longer exists.")
        return

    if action == "cancel":
        mark_order(order_id, "cancelled")
        await q.edit_message_text("❌ Invoice cancelled.")
        return

    if action == "edit":
        context.user_data["editing_order_id"] = order_id
        await q.message.reply_text(
            "✏️ Send the corrected order text now in this same topic.\n"
            "I will update this invoice preview instead of creating a new one."
        )
        return

    if action == "gen":
        invoice_no = next_invoice_no(order.get("order_no"))
        tmp_dir = tempfile.mkdtemp(prefix="lumiere_invoice_")
        filename = f"Lumiere_Invoice_{invoice_no}.pdf"
        path = os.path.join(tmp_dir, filename)
        create_invoice(order, invoice_no, path)

        with open(path, "rb") as f:
            await context.bot.send_document(
                chat_id=order["telegram_chat_id"],
                message_thread_id=order["topic_id"],
                document=f,
                filename=filename,
                caption=f"✅ Invoice #{invoice_no} — {order['customer']}",
                reply_to_message_id=order.get("source_message_id"),
            )
        mark_order(order_id, "generated", invoice_no)
        try:
            await q.edit_message_reply_markup(reply_markup=None)
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
    app.add_handler(CallbackQueryHandler(callback, pattern=r"^(gen|edit|cancel):\d+$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_order))
    app.add_error_handler(error_handler)

    log.info("Starting Lumiere Invoice Bot with long polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
