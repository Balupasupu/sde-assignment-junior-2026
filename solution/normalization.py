
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def normalize_phone(value):
    if value is None:
        return None

    digits = re.sub(r"\D", "", str(value))

    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]

    if len(digits) != 10:
        return None

    if digits[0] not in "6789":
        return None

    return "+91" + digits


def normalize_date(value):
    if value is None or not str(value).strip():
        return None

    value = str(value).strip()

    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d-%b-%Y",
    ]

    for fmt in formats:
        try:
            parsed_date = datetime.strptime(value, fmt)
            return parsed_date.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None


def normalize_decimal(value):
    if value is None or not str(value).strip():
        return None

    value = str(value).strip()

    # Remove currency prefixes
    value = re.sub(
        r"^(₹|Rs\.?|INR)\s*",
        "",
        value,
        flags=re.IGNORECASE
    )

    # Remove thousands separators
    value = value.replace(",", "")

    try:
        amount = Decimal(value)

        if not amount.is_finite() or amount < 0:
            return None

        return amount.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP
        )

    except InvalidOperation:
        return None
