import asyncio
import json
import logging
import os
import urllib.request
from datetime import timezone
from zoneinfo import ZoneInfo

log = logging.getLogger("lumiere_invoice_bot.sheets")


def _staff_name(user):
    if not user:
        return ""
    if getattr(user, "username", None):
        return f"@{user.username}"
    return getattr(user, "full_name", "") or str(getattr(user, "id", ""))


def _build_payload(message, parsed, user):
    tz = ZoneInfo(os.getenv("TZ", "Asia/Phnom_Penh"))
    dt = message.date
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(tz)

    total = sum(float(x["amount"]) for x in parsed["items"])
    total_qty_kg = sum(
        float(x.get("physical_qty_kg", x.get("charged_qty", 0)))
        for x in parsed["items"]
    )

    return {
        "order_no": parsed.get("order_no") or "",
        "customer": parsed["customer"],
        "items": parsed["items"],
        "payment_status": parsed.get("payment_status", "Unpaid"),
        "payment_method": parsed.get("payment_method", ""),
        "staff": _staff_name(user),
        "telegram_message_id": str(message.message_id),
        "telegram_chat_id": str(message.chat_id),
        "telegram_topic_id": str(message.message_thread_id or ""),
        "raw_order": message.text or "",
        "date": local.strftime("%d/%m/%Y"),
        "time": local.strftime("%H:%M:%S"),
        "order_total": round(total, 2),
        "total_qty_kg": round(total_qty_kg, 4),
    }


def _post_sync(url, secret, payload):
    body = json.dumps({"secret": secret, "order": payload}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        text = response.read().decode("utf-8", errors="replace")
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"Google Sheets HTTP {response.status}: {text}")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            raise RuntimeError(f"Google Sheets returned invalid response: {text[:300]}")
        if not data.get("ok"):
            raise RuntimeError(data.get("error") or "Google Sheets sync failed")
        return data


async def sync_order_to_sheets(message, parsed, user):
    url = os.getenv("SHEETS_WEBHOOK_URL", "").strip()
    secret = os.getenv("SHEETS_WEBHOOK_SECRET", "").strip()

    if not url or not secret:
        log.warning(
            "Google Sheets integration is disabled. "
            "Set SHEETS_WEBHOOK_URL and SHEETS_WEBHOOK_SECRET in Railway."
        )
        return {"ok": False, "disabled": True}

    payload = _build_payload(message, parsed, user)
    return await asyncio.to_thread(_post_sync, url, secret, payload)
