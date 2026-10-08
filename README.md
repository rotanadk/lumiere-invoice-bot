# Lumiere Invoice Bot — Auto Invoice + Google Sheets

## Workflow

1. Staff posts an order in **Drop Order**.
2. The bot silently parses the order.
3. Each product is written to the `Order_Items` tab (one row per product).
4. One complete order record is written to the `Orders` tab.
5. The approved Lumiere PDF invoice is generated.
6. The PDF is sent to the separate **Invoice** topic.
7. Nothing is posted in Drop Order unless staff posts it.

Example:

```
45: Arata:
LV55 10kg (14$)
BV55 5kg (16$)
```

Google Sheets result:
- 2 rows in `Order_Items`
- 1 row in `Orders`
- Order total = $220.00
- Total quantity = 15 kg

The parser also accepts:
`45: Arata: LV55 10kg (14$), BV55 5kg (16$)`

## Existing Railway variables

Keep:
- `BOT_TOKEN`
- `DATA_DIR=/data`
- `TZ=Asia/Phnom_Penh`

## New Railway variables

Add:
- `SHEETS_WEBHOOK_URL` = your Google Apps Script Web App URL ending in `/exec`
- `SHEETS_WEBHOOK_SECRET` = the same secret configured in Apps Script

## Google Sheet

Spreadsheet:
`Lumiere Order Transactions`

Required tabs:
- `Order_Items`
- `Orders`
- `Summary`

## Apps Script setup

1. Open the Google Sheet.
2. Go to **Extensions → Apps Script**.
3. Replace the default code with `google_apps_script.gs`.
4. Open **Project Settings → Script Properties**.
5. Add:
   - Property: `WEBHOOK_SECRET`
   - Value: your secret
6. Click **Deploy → New deployment**.
7. Select **Web app**.
8. Execute as: **Me**
9. Who has access: **Anyone**
10. Deploy and copy the Web App URL ending in `/exec`.
11. Put that URL into Railway as `SHEETS_WEBHOOK_URL`.
12. Put the same secret into Railway as `SHEETS_WEBHOOK_SECRET`.
13. Redeploy Railway.

## Telegram setup

Your existing topic setup remains the same:
- Drop Order: `/setup_orders`
- Invoice topic: `/setup_invoices`

If `/data` is on a Railway persistent volume, you do not need to run these again after normal redeploys.

## Error behavior

- If Google Sheets has a problem, the invoice is still generated.
- The error is reported only in the Invoice topic.
- Drop Order stays clean.
