from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from io import BytesIO

from fastapi import FastAPI
from fastapi.responses import Response
from pydantic import BaseModel, Field, constr

from babel.core import Locale
from babel.numbers import format_currency, get_currency_name, UnknownCurrencyError

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from mangum import Mangum


app = FastAPI(title="Guide Booker Invoice Generator", version="1.1.0")


CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
LOCALE_RE = re.compile(r"^[a-z]{2}(_[A-Z]{2})?$")


class InvoiceRequest(BaseModel):
    booking_id: constr(strip_whitespace=True, min_length=1) = Field("bk_123456789", example="bk_123456789")
    payment_id: constr(strip_whitespace=True, min_length=1) = Field("pay_987654321", example="pay_987654321")

    customer_name: constr(strip_whitespace=True, min_length=1) = Field(..., example="John Doe")
    guide_name: constr(strip_whitespace=True, min_length=1) = Field(..., example="Bali Explorer")
    date: constr(strip_whitespace=True, min_length=1) = Field(..., example="2026-04-05")

    price: float = Field(..., ge=0, example=150.00)

    currency: constr(strip_whitespace=True, min_length=3, max_length=3) = Field("USD", example="USD")

    locale: constr(strip_whitespace=True, min_length=2, max_length=10) = Field("id_ID", example="en_US")


def _parse_booking_date(date_str: str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return date_str


def _short_hash(value: str, length: int = 7) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest().upper()
    return digest[:length]


def build_invoice_number(booking_id: str, payment_id: str, booking_date: str) -> str:
    """
    Deterministic, traceable invoice number tied to booking/payment.
    Format: GB-INV-YYYYMMDD-BK<hash>-PY<hash>-<chk>
    """
    date_compact = booking_date.replace("-", "") if re.match(r"^\d{4}-\d{2}-\d{2}$", booking_date) else "00000000"

    bk = _short_hash(booking_id, 7)
    py = _short_hash(payment_id, 7)

    checksum_src = f"{date_compact}|{booking_id}|{payment_id}"
    checksum = _short_hash(checksum_src, 4)

    return f"GB-INV-{date_compact}-BK{bk}-PY{py}-{checksum}"


def format_money(amount: float, currency: str, locale_str: str) -> str:
    currency = currency.strip().upper()
    locale_str = locale_str.strip()

    if not CURRENCY_RE.match(currency):
        currency = "USD"

    if not LOCALE_RE.match(locale_str):
        locale_str = "en_US"

    try:
        Locale.parse(locale_str)
    except Exception:
        locale_str = "en_US"

    try:
        _ = get_currency_name(currency, locale=locale_str)
    except UnknownCurrencyError:
        currency = "USD"

    return format_currency(amount, currency, locale=locale_str)


def generate_invoice_pdf(data: InvoiceRequest) -> bytes:
    booking_date = _parse_booking_date(data.date)
    issue_dt = datetime.now(timezone.utc)
    local_dt = issue_dt.astimezone()

    invoice_no = build_invoice_number(data.booking_id, data.payment_id, data.date)
    amount_str = format_money(data.price, data.currency, data.locale)

    buffer = BytesIO()
    width, height = A4
    c = canvas.Canvas(buffer, pagesize=A4)

    margin_x = 18 * mm
    top_y = height - 18 * mm

    c.setFont("Helvetica-Bold", 18)
    c.drawString(margin_x, top_y, "INVOICE")

    c.setFont("Helvetica", 10)
    c.drawRightString(width - margin_x, top_y + 2, "Guide Booker")
    c.drawRightString(width - margin_x, top_y - 12, "Invoice PDF Generator Service")

    c.setLineWidth(1)
    c.line(margin_x, top_y - 22, width - margin_x, top_y - 22)

    meta_y = top_y - 45
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin_x, meta_y, "Invoice Details")
    c.setFont("Helvetica", 10)

    c.drawString(margin_x, meta_y - 18, f"Invoice No: {invoice_no}")
    c.drawString(margin_x, meta_y - 34, f"Issue Date (UTC{local_dt:%z}): {local_dt.strftime('%Y-%m-%d %H:%M:%S')}")
    c.drawString(margin_x, meta_y - 50, f"Booking Date: {booking_date}")

    # c.drawString(margin_x, meta_y - 70, f"Booking ID: {data.booking_id}")
    # c.drawString(margin_x, meta_y - 86, f"Payment ID: {data.payment_id}")

    bill_y = meta_y - 120
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin_x, bill_y, "Bill To")
    c.setFont("Helvetica", 10)
    c.drawString(margin_x, bill_y - 18, data.customer_name)

    table_y = bill_y - 60
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin_x, table_y, "Service")
    c.drawString(width - margin_x - 120, table_y, "Amount")

    c.setLineWidth(0.8)
    c.line(margin_x, table_y - 8, width - margin_x, table_y - 8)

    c.setFont("Helvetica", 10)
    c.drawString(margin_x, table_y - 28, f"Guided Tour: {data.guide_name}")
    c.drawRightString(width - margin_x, table_y - 28, amount_str)

    total_y = table_y - 70
    c.setLineWidth(0.8)
    c.line(margin_x, total_y + 12, width - margin_x, total_y + 12)

    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin_x, total_y - 2, "TOTAL")
    c.drawRightString(width - margin_x, total_y - 2, amount_str)

    footer_y = 28 * mm
    c.setFont("Helvetica", 9)
    c.drawString(margin_x, footer_y, "Thank you for your booking!")
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(margin_x, footer_y - 12, "This invoice was generated automatically.")

    c.showPage()
    c.save()

    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


@app.post("/generate-invoice")
def generate_invoice(req: InvoiceRequest):
    pdf_bytes = generate_invoice_pdf(req)

    filename = f"invoice_{req.booking_id.strip().replace(' ', '_')}.pdf"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}

    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)

handler = Mangum(app)
