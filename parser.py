import re
from decimal import Decimal, InvalidOperation

PAYMENT_RE = re.compile(r"\bpaid\s+by\s+(.+)$", re.I)
PAID_RE = re.compile(r"\bpaid\b", re.I)
UNPAID_RE = re.compile(r"\bunpaid\b", re.I)

ITEM_RE = re.compile(
    r"^\s*(?P<product>.+?)\s+"
    r"(?P<qty>\d+(?:\.\d+)?(?:\s*\+\s*\d+(?:\.\d+)?)?)\s*"
    r"(?P<unit>kg|kgs|g|gram|grams)?\s*"
    r"(?:\(\s*\$?\s*(?P<price>\d+(?:\.\d+)?)\s*\$?\s*\))\s*$",
    re.I,
)


def _to_decimal(s):
    try:
        return Decimal(str(s))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _split_item_entries(text):
    # Supports:
    # LV55 10kg (14$); BV55 5kg (16$)
    # LV55 10kg (14$), BV55 5kg (16$)
    # LV55 10kg (14$) and BV55 5kg (16$)
    parts = re.split(r"\s*;\s*|\s*,\s*|\s+(?:and|&)\s+", text, flags=re.I)
    return [p.strip() for p in parts if p.strip()]


def _normalize_qty(qty_raw, unit_raw):
    qty_raw = re.sub(r"\s+", "", qty_raw)
    unit = (unit_raw or "kg").lower()
    if unit == "kgs":
        unit = "kg"
    if unit in ("gram", "grams"):
        unit = "g"

    if "+" in qty_raw:
        base_s, bonus_s = qty_raw.split("+", 1)
        base = _to_decimal(base_s)
        bonus = _to_decimal(bonus_s)
    else:
        base = _to_decimal(qty_raw)
        bonus = Decimal("0")

    if unit == "g":
        charged_qty_kg = base / Decimal("1000")
        physical_qty_kg = (base + bonus) / Decimal("1000")
    else:
        charged_qty_kg = base
        physical_qty_kg = base + bonus

    display = f"{qty_raw} {unit}"
    return display, qty_raw, unit, charged_qty_kg, bonus, physical_qty_kg


def parse_order(text):
    if not text or not text.strip():
        raise ValueError("Empty order message")

    raw_lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not raw_lines:
        raise ValueError("Empty order message")

    order_no = None
    customer = None
    item_lines = []
    payment_status = "Unpaid"
    payment_method = ""

    first = raw_lines[0]

    # Examples:
    # 37: Prime : LV55 10kg (14.5$)
    # 45: Arata: LV55 10kg (14$), BV55 5kg (16$)
    # 33: walk-in
    m = re.match(r"^\s*(\d+)\s*:\s*([^:]+?)(?:\s*:\s*(.+))?$", first)
    if m:
        order_no = m.group(1).strip()
        customer = m.group(2).strip()
        if m.group(3):
            item_lines.extend(_split_item_entries(m.group(3).strip()))
        rest = raw_lines[1:]
    else:
        # Also support: Prime : LV55 10kg (14.5$)
        m2 = re.match(r"^\s*([^:]+?)\s*:\s*(.+)$", first)
        if m2:
            candidate_items = _split_item_entries(m2.group(2).strip())
            if candidate_items and all(ITEM_RE.match(x) for x in candidate_items):
                customer = m2.group(1).strip()
                item_lines.extend(candidate_items)
                rest = raw_lines[1:]
            else:
                customer = first.strip(" :")
                rest = raw_lines[1:]
        else:
            # Fallback: first line is customer, following lines are items.
            customer = first.strip(" :")
            rest = raw_lines[1:]

    for line in rest:
        pm = PAYMENT_RE.search(line)
        if pm:
            payment_status = "Paid"
            payment_method = pm.group(1).strip().title()
            continue
        if UNPAID_RE.search(line):
            payment_status = "Unpaid"
            continue
        if PAID_RE.search(line) and not ITEM_RE.match(line):
            payment_status = "Paid"
            continue

        item_lines.extend(_split_item_entries(line))

    items = []
    unparsed = []
    for line in item_lines:
        im = ITEM_RE.match(line)
        if not im:
            unparsed.append(line)
            continue

        qty_display, qty_raw, unit, charged_qty_kg, bonus, physical_qty_kg = _normalize_qty(
            im.group("qty"), im.group("unit")
        )
        unit_price = _to_decimal(im.group("price"))
        amount = (charged_qty_kg * unit_price).quantize(Decimal("0.01"))

        items.append({
            "product": im.group("product").strip(),
            "qty_display": qty_display,
            "qty": qty_raw,
            "unit": unit,
            "charged_qty": float(charged_qty_kg),
            "bonus_qty": float(bonus),
            "physical_qty_kg": float(physical_qty_kg),
            "unit_price": float(unit_price),
            "amount": float(amount),
        })

    if not customer:
        raise ValueError("Customer name not found")
    if not items:
        detail = f" I couldn't read: {', '.join(unparsed)}" if unparsed else ""
        raise ValueError("No product line with quantity and price was found." + detail)
    if unparsed:
        raise ValueError("I couldn't understand this line: " + " | ".join(unparsed))

    return {
        "order_no": order_no,
        "customer": customer,
        "items": items,
        "payment_status": payment_status,
        "payment_method": payment_method,
    }
