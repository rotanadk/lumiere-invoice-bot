import os
from datetime import datetime
from zoneinfo import ZoneInfo

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor, black
from reportlab.lib.utils import ImageReader

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_PATH = os.path.join(BASE_DIR, "assets", "lumiere_logo.png")
QR_PATH = os.path.join(BASE_DIR, "assets", "payment_qr.png")


def money(v):
    return f"$ {float(v):,.2f}"


def create_invoice(order, invoice_no, output_path):
    W, H = A4
    c = canvas.Canvas(output_path, pagesize=A4)

    dark = HexColor("#303030")
    gray = HexColor("#8A8A8A")
    light = HexColor("#BEBEBE")
    white = HexColor("#FFFFFF")

    c.setFillColor(white)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # Logo
    c.drawImage(ImageReader(LOGO_PATH), 48, H-170, width=125, height=114,
                preserveAspectRatio=True, mask="auto")

    # Header
    c.setFillColor(black)
    c.setFont("Helvetica", 25)
    c.drawRightString(W-50, H-88, "INVOICE")
    c.setFont("Helvetica", 9.5)
    c.drawRightString(W-50, H-108, f"Invoice ID :    #{invoice_no}")
    local_date = datetime.now(ZoneInfo(os.getenv("TZ", "Asia/Phnom_Penh"))).strftime("%d %b %Y")
    c.drawRightString(W-50, H-124, f"Date :    {local_date}")

    # Bill to / from
    y = H-205
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "BILL TO")
    c.setFont("Helvetica-Bold", 12.5)
    c.drawString(50, y-32, order["customer"][:45])
    c.setFont("Helvetica", 9.5)
    c.setFillColor(gray)
    c.drawString(50, y-49, "Customer")
    c.setFillColor(black)

    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(W-50, y, "FROM")
    c.setFont("Helvetica-Bold", 12.5)
    c.drawRightString(W-50, y-32, "Lumiere Coffee Roastery")
    c.setFont("Helvetica", 9.5)
    c.setFillColor(gray)
    c.drawRightString(W-50, y-49, "Phnom Penh, Cambodia")
    c.setFillColor(black)

    # Table header
    table_x = 50
    table_w = W-100
    header_y = H-325
    c.setFillColor(dark)
    c.roundRect(table_x, header_y, table_w, 30, 5, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(table_x+14, header_y+10, "PRODUCT")
    c.drawString(table_x+285, header_y+10, "PRICE")
    c.drawString(table_x+380, header_y+10, "QTY")
    c.drawRightString(table_x+table_w-14, header_y+10, "TOTAL")

    # Items
    row_y = header_y - 32
    row_gap = 31
    subtotal = 0.0
    for item in order["items"][:8]:
        subtotal += float(item["amount"])
        c.setFillColor(black)
        c.setFont("Helvetica-Bold", 10.5)
        c.drawString(table_x+14, row_y, item["product"][:38])
        c.setFont("Helvetica", 10)
        c.drawString(table_x+285, row_y, money(item["unit_price"]))
        c.drawString(table_x+380, row_y, item["qty_display"])
        c.drawRightString(table_x+table_w-14, row_y, money(item["amount"]))
        c.setStrokeColor(light)
        c.setLineWidth(0.6)
        c.line(table_x+14, row_y-18, table_x+table_w-14, row_y-18)
        row_y -= row_gap

    # Keep totals/payment below item table.
    tot_y = min(H-470, row_y-30)

    # Payment method + QR
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 10.5)
    c.drawString(50, tot_y, "PAYMENT METHOD")
    c.drawImage(ImageReader(QR_PATH), 50, tot_y-160, width=130, height=130,
                preserveAspectRatio=True, mask="auto")
    c.setFont("Helvetica", 9.2)
    c.drawString(50, tot_y-178, f"Status: {order.get('payment_status') or 'Unpaid'}")
    if order.get("payment_method"):
        c.drawString(50, tot_y-194, f"Method: {order['payment_method']}")

    # Totals
    discount = 0.0
    total = subtotal - discount
    right_label_x = W-235
    right_val_x = W-50
    c.setFont("Helvetica-Bold", 10.5)
    c.drawString(right_label_x, tot_y, "SUB-TOTAL")
    c.drawRightString(right_val_x, tot_y, money(subtotal))
    c.drawString(right_label_x, tot_y-27, "DISCOUNT")
    c.drawRightString(right_val_x, tot_y-27, money(discount))

    bar_y = tot_y-82
    c.setFillColor(dark)
    c.roundRect(right_label_x-7, bar_y, 192, 32, 5, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(right_label_x+6, bar_y+10, "TOTAL")
    c.drawRightString(right_val_x, bar_y+10, money(total))

    # Footer
    c.setFillColor(black)
    c.setFont("Helvetica-Oblique", 16)
    c.drawString(50, 78, "Thank You For Your Business")
    c.setStrokeColor(light)
    c.line(W-155, 93, W-50, 93)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawRightString(W-50, 73, "LUMIERE COFFEE ROASTERY")

    c.save()
    return output_path
