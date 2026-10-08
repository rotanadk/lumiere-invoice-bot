import re
from decimal import Decimal, InvalidOperation

# Supports:
#   Pay by AC
#   Paid by AC
#   Paid by cash
PAYMENT_SUFFIX_RE = re.compile(r"\s+(?:pay|paid)\s+by\s+(.+?)\s*$", re.I)
PAYMENT_ONLY_RE = re.compile(r"^\s*(?:pay|paid)\s+by\s+(.+?)\s*$", re.I)
PAID_RE = re.compile(r"^\s*paid\s*$", re.I)
UNPAID_RE = re.compile(r"^\s*unpaid\s*$", re.I)

# Product examples:
#   LV55 10kg (14$)
#   Brazil 500g (20$)
#   Colombia Cookie: 200g (65$)
#   - Costa Rica: 200g (65$)
ITEM_RE = re.compile(
    r"^\s*(?:[-•*]\s*)?"
    r"(?P<product>.+?)\s+"
    r"(?P<qty>\d+(?:\.\d+)?(?:\s*\+\s*\d+(?:\.\d+)?)?)\s*"
    r"(?P<unit>kg|kgs|g|gram|grams)?\s*"
    r"\(\s*\$?\s*(?P<price>\d+(?:\.\d+)?)\s*\$?\s*\)\s*$",
    re.I,
)

# Used for orders where staff forget the customer/product colon:
#   44: JiJi LV91 1kg (17$)
TAIL_QTY_PRICE_RE = re.compile(
    r"^(?P<prefix>.+?)\s+"
    r"(?P<qty>\d+(?:\.\d+)?(?:\s*\+\s*\d+(?:\.\d+)?)?)\s*"
    r"(?P<unit>kg|kgs|g|gram|grams)?\s*"
    r"\(\s*\$?\s*(?P<price>\d+(?:\.\d+)?)\s*\$?\s*\)\s*$",
    re.I,
)


def _to_decimal(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _clean_product(name):
    name = re.sub(r"^\s*[-•*]\s*", "", name or "").strip()
    return name.rstrip(":").strip()


def _split_item_entries(text):
    # Supports multiple products on one line:
    # LV55 10kg (14$), BV55 5kg (16$)
    # LV55 10kg (14$); BV55 5kg (16$)
    # LV55 10kg (14$) and BV55 5kg (16$)
    parts = re.split(r"\s*;\s*|\s*,\s*|\s+(?:and|&)\s+", text, flags=re.I)
    return [p.strip() for p in parts if p.strip()]


def _strip_payment_suffix(line):
    """
    Returns: (clean_line, payment_status_or_None, payment_method_or_empty)
    Example:
      "Brazil 500g (20$) Pay by AC"
      -> ("Brazil 500g (20$)", "Paid", "AC")
    """
    line = (line or "").strip()

    m = PAYMENT_ONLY_RE.match(line)
    if m:
        return "", "Paid", m.group(1).strip()

    m = PAYMENT_SUFFIX_RE.search(line)
    if m:
        clean = line[:m.start()].rstrip(" -,:")
        return clean, "Paid", m.group(1).strip()

    if PAID_RE.match(line):
        return "", "Paid", ""

    if UNPAID_RE.match(line):
        return "", "Unpaid", ""

    return line, None, ""


def _normalize_qty(qty_raw, unit_raw):
    qty_raw = re.sub(r"\s+", "", qty_raw)
    unit = (unit_raw or "kg").lower()

    if unit == "kgs":
        unit = "kg"
    elif unit in ("gram", "grams"):
        unit = "g"

    if "+" in qty_raw:
        base_s, bonus_s = qty_raw.split("+", 1)
        base = _to_decimal(base_s)
        bonus = _to_decimal(bonus_s)
    else:
        base = _to_decimal(qty_raw)
        bonus = Decimal("0")

    # Price is treated as price per kg, matching the existing bot behavior.
    if unit == "g":
        charged_qty_kg = base / Decimal("1000")
        physical_qty_kg = (base + bonus) / Decimal("1000")
    else:
        charged_qty_kg = base
        physical_qty_kg = base + bonus

    display = f"{qty_raw} {unit}"
    return display, qty_raw, unit, charged_qty_kg, bonus, physical_qty_kg


def _parse_item(line):
    m = ITEM_RE.match(line)
    if not m:
        return None

    qty_display, qty_raw, unit, charged_qty_kg, bonus, physical_qty_kg = _normalize_qty(
        m.group("qty"), m.group("unit")
    )
    unit_price = _to_decimal(m.group("price"))
    amount = (charged_qty_kg * unit_price).quantize(Decimal("0.01"))

    return {
        "product": _clean_product(m.group("product")),
        "qty_display": qty_display,
        "qty": qty_raw,
        "unit": unit,
        "charged_qty": float(charged_qty_kg),
        "bonus_qty": float(bonus),
        "physical_qty_kg": float(physical_qty_kg),
        "unit_price": float(unit_price),
        "amount": float(amount),
    }


def _split_customer_and_inline_item(body):
    """
    Returns (customer, inline_item_text_or_empty).

    Normal:
      Arata: LV55 10kg (14$)
      Walk-in Customer:

    Fallback for missing customer/product colon:
      JiJi LV91 1kg (17$)
      -> customer JiJi, item LV91 1kg (17$)

    The no-colon fallback assumes the product is the last word/code before
    the quantity. This works well for LV91, LV55, BV55, Brazil, etc.
    For multi-word product names, staff should keep using a colon.
    """
    body = (body or "").strip()

    # Explicit customer/product separator.
    if ":" in body:
        customer, item_text = body.split(":", 1)
        return customer.strip(), item_text.strip()

    # Missing separator fallback.
    m = TAIL_QTY_PRICE_RE.match(body)
    if m:
        prefix = m.group("prefix").strip()
        tokens = prefix.split()
        if len(tokens) >= 2:
            # Treat last token before quantity as product.
            customer = " ".join(tokens[:-1]).strip()
            product = tokens[-1].strip()
            item_text = f"{product} {m.group('qty')}{m.group('unit') or ''} ({m.group('price')}$)"
            return customer, item_text

    # Customer-only header.
    return body.rstrip(":").strip(), ""


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

    # First try: order number at the front.
    m = re.match(r"^\s*(\d+)\s*:\s*(.*)$", first)
    if m:
        order_no = m.group(1).strip()
        body = m.group(2).strip()

        body, status, method = _strip_payment_suffix(body)
        if status:
            payment_status = status
            payment_method = method

        customer, inline_item = _split_customer_and_inline_item(body)
        if inline_item:
            item_lines.extend(_split_item_entries(inline_item))
        rest = raw_lines[1:]

    else:
        # No order number. Support:
        # Prime: LV55 10kg (14$)
        clean_first, status, method = _strip_payment_suffix(first)
        if status:
            payment_status = status
            payment_method = method

        customer, inline_item = _split_customer_and_inline_item(clean_first)
        if inline_item:
            item_lines.extend(_split_item_entries(inline_item))
        rest = raw_lines[1:]

    # Parse following product/payment lines.
    for line in rest:
        clean_line, status, method = _strip_payment_suffix(line)

        if status:
            payment_status = status
            if method:
                payment_method = method

        if not clean_line:
            continue

        item_lines.extend(_split_item_entries(clean_line))

    items = []
    unparsed = []

    for line in item_lines:
        item = _parse_item(line)
        if item:
            items.append(item)
        else:
            unparsed.append(line)

    if not customer:
        raise ValueError(
            "Customer name not found. Use: 44: Customer: Product 1kg (17$)"
        )

    if not items:
        detail = f" I couldn't read: {', '.join(unparsed)}" if unparsed else ""
        raise ValueError(
            "No product line with quantity and price was found." + detail
        )

    if unparsed:
        raise ValueError(
            "I couldn't understand this line: " + " | ".join(unparsed)
        )

    return {
        "order_no": order_no,
        "customer": customer.rstrip(":").strip(),
        "items": items,
        "payment_status": payment_status,
        "payment_method": payment_method,
    }
