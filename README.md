# Lumiere Invoice Telegram Bot

This bot watches one Telegram forum topic (your **Drop Order** topic), reads order messages, shows a confirmation preview, and generates the approved Lumiere Coffee Roastery PDF invoice with your payment QR code.

## Supported example

```text
37: Prime : LV55 10kg (14.5$)
```

Multiple products:

```text
38: ABC Coffee
LV55 5kg (14.5$)
BV55 10kg (16$)
Paid by cash
```

Buy-10-get-1 style quantity is also supported:

```text
39: Customer Name : BV55 10+1kg (16$)
```

The invoice displays `10+1 kg`, but charges only the first `10 kg`.

For grams, the price is treated as price per kg. Example: `Colombia Cookies 200g (65$)` becomes 0.2 × $65 = $13.

## Railway deployment

1. Create a new GitHub repository.
2. Upload every file/folder from this project to the repository. Keep the `assets` folder.
3. In Railway, create a new project from that GitHub repository.
4. In Railway **Variables**, add:
   - `BOT_TOKEN` = the token from @BotFather
   - `DATA_DIR` = `/data`
   - `TZ` = `Asia/Phnom_Penh`
5. Add a Railway Volume and mount it at `/data` so your setup and invoice records survive redeploys.
6. Deploy. The included `railway.json` starts the bot with `python bot.py`.
7. In Telegram, open your **Drop Order** topic and send:

```text
/setup
```

The bot will save that group ID and topic ID automatically.

## Normal workflow

1. Staff posts an order in Drop Order.
2. Bot replies with invoice preview.
3. Tap **Generate Invoice**, **Edit**, or **Cancel**.
4. Generate Invoice sends the PDF into the same topic.

## Security

Never put your real BotFather token in GitHub or in any file. Put it only in Railway Variables as `BOT_TOKEN`.
