from decimal import Decimal

from solution.normalization import (
    normalize_phone,
    normalize_date,
    normalize_decimal,
)


def test_phone_with_country_code():
    assert normalize_phone("+91 98765 43210") == "+919876543210"


def test_phone_with_leading_zero():
    assert normalize_phone("09876543210") == "+919876543210"


def test_invalid_phone():
    assert normalize_phone("12345") is None


def test_invalid_phone_start_digit():
    assert normalize_phone("5123456789") is None


def test_date_yyyy_mm_dd():
    assert normalize_date("2026-12-29") == "2026-12-29"


def test_date_dd_mm_yyyy():
    assert normalize_date("29/12/2026") == "2026-12-29"


def test_date_dd_mon_yyyy():
    assert normalize_date("29-Dec-2026") == "2026-12-29"


def test_invalid_date():
    assert normalize_date("31/02/2026") is None


def test_decimal_rupee():
    assert normalize_decimal("₹27,554") == Decimal("27554.00")


def test_decimal_rs_prefix():
    assert normalize_decimal("Rs. 1,250.50") == Decimal("1250.50")


def test_negative_decimal():
    assert normalize_decimal("-100") is None


def test_invalid_decimal():
    assert normalize_decimal("invalid") is None