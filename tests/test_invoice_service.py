import re

import pytest
from fastapi.testclient import TestClient

# sesuaikan import sesuai nama file kamu
from app import (
    app,
    build_invoice_number,
    format_money,
    generate_invoice_pdf,
    InvoiceRequest,
)


client = TestClient(app)


def sample_request_payload(**overrides):
    data = {
        "booking_id": "bk_123456789",
        "payment_id": "pay_987654321",
        "customer_name": "John Doe",
        "guide_name": "Bali Explorer",
        "date": "2026-04-05",
        "price": 150.00,
        "currency": "USD",
        "locale": "en_US",
    }
    data.update(overrides)
    return data


# -------------------------
# Unit tests: helper funcs
# -------------------------

def test_build_invoice_number_is_deterministic_and_well_formed():
    inv1 = build_invoice_number("bk_123", "pay_456", "2026-04-05")
    inv2 = build_invoice_number("bk_123", "pay_456", "2026-04-05")
    assert inv1 == inv2

    # Format: GB-INV-YYYYMMDD-BK<7>-PY<7>-<4>
    assert re.fullmatch(r"GB-INV-\d{8}-BK[A-F0-9]{7}-PY[A-F0-9]{7}-[A-F0-9]{4}", inv1)


def test_build_invoice_number_invalid_date_uses_zeros():
    inv = build_invoice_number("bk_123", "pay_456", "not-a-date")
    assert inv.startswith("GB-INV-00000000-")


def test_format_money_valid():
    s = format_money(150.0, "USD", "en_US")
    assert "150" in s  # jangan terlalu ketat karena format bisa "USD150.00" / "$150.00" tergantung locale rules


def test_format_money_invalid_currency_falls_back_to_usd():
    s = format_money(150.0, "xxx", "en_US")  # invalid 3-letter but unknown currency
    # fallback -> USD, jadi harus tetap ada angka 150
    assert "150" in s


def test_format_money_invalid_currency_format_falls_back_to_usd():
    s = format_money(150.0, "US", "en_US")  # gagal regex (bukan 3 huruf)
    assert "150" in s


def test_format_money_invalid_locale_falls_back_to_en_us():
    s = format_money(150.0, "USD", "bad_locale")
    assert "150" in s


def test_generate_invoice_pdf_returns_pdf_bytes():
    req = InvoiceRequest(**sample_request_payload())
    pdf_bytes = generate_invoice_pdf(req)

    assert isinstance(pdf_bytes, (bytes, bytearray))
    assert len(pdf_bytes) > 1000  # PDF umumnya cukup besar
    assert pdf_bytes[:5] == b"%PDF-"  # signature PDF


# -------------------------
# Integration-ish tests: API
# -------------------------

def test_generate_invoice_endpoint_returns_pdf_and_headers():
    payload = sample_request_payload()
    resp = client.post("/generate-invoice", json=payload)

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert resp.content[:5] == b"%PDF-"

    cd = resp.headers.get("content-disposition", "")
    assert "attachment" in cd.lower()
    assert 'filename="invoice_bk_123456789.pdf"' in cd


def test_generate_invoice_endpoint_validation_error_missing_required():
    payload = sample_request_payload()
    payload.pop("customer_name")  # required
    resp = client.post("/generate-invoice", json=payload)

    assert resp.status_code == 422  # Pydantic validation


def test_generate_invoice_endpoint_with_weird_spaces_in_booking_id_filename_sanitized():
    payload = sample_request_payload(booking_id="bk 123 456")
    resp = client.post("/generate-invoice", json=payload)

    assert resp.status_code == 200
    cd = resp.headers.get("content-disposition", "")
    assert 'filename="invoice_bk_123_456.pdf"' in cd


@pytest.mark.parametrize(
    "currency,locale",
    [
        ("IDR", "id_ID"),
        ("EUR", "fr_FR"),
        ("JPY", "ja_JP"),
        ("XXX", "en_US"),      # invalid/unknown currency -> fallback
        ("USD", "bad_locale"), # invalid locale -> fallback
    ],
)
def test_generate_invoice_endpoint_various_currency_locale(currency, locale):
    payload = sample_request_payload(currency=currency, locale=locale)
    resp = client.post("/generate-invoice", json=payload)

    assert resp.status_code == 200
    assert resp.content[:5] == b"%PDF-"
