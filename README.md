# Lumiere Invoice Bot — Auto Invoice Mode

This version keeps the **Drop Order** topic clean.

## Workflow

1. Staff posts a normal order in the **Drop Order** topic.
2. The bot silently reads and parses it.
3. The bot immediately generates the approved Lumiere PDF invoice.
4. The PDF is sent automatically to a separate **Invoice** topic.
5. No preview/buttons are posted in Drop Order.

Example order:

`37: Prime : LV55 10kg (14.5$)`

Result: Invoice #37, total $145.00.

## Railway variables

- `BOT_TOKEN` = your BotFather token
- `DATA_DIR` = `/data`
- `TZ` = `Asia/Phnom_Penh`

Use a Railway persistent volume mounted at `/data`.

## Telegram setup

After deploying this version:

### Source topic
Open **Drop Order** and send:

`/setup_orders`

(`/setup` is also accepted for backward compatibility.)

### Destination topic
Create/open a separate topic such as **Invoices** and send:

`/setup_invoices`

After both commands succeed, new orders are processed automatically.

## Notes

- Valid orders create invoices silently in the destination topic.
- If an order cannot be parsed, the error is posted to the Invoice topic, not Drop Order.
- The bot stores processed source message IDs so a restart/retry does not create duplicate invoices for the same Telegram message.
