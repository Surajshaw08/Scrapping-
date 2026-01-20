import re
from datetime import datetime
from typing import Optional

def parse_float(value: Optional[str]) -> Optional[float]:
    """
    Converts '₹10 per share' → 10.0
    Converts '2,500 Cr' → 2500.0
    """
    if not value:
        return None

    value = value.replace(",", "")
    match = re.search(r"(\d+(\.\d+)?)", value)
    return float(match.group(1)) if match else None


def parse_int(value: Optional[str]) -> Optional[int]:
    """
    Converts '120 Shares' → 120
    """
    if not value:
        return None

    match = re.search(r"\d+", value.replace(",", ""))
    return int(match.group()) if match else None


def parse_date(value: Optional[str]) -> Optional[str]:
    """
    Converts 'Wed, Jan 28, 2026T' → 2026-01-28
    """
    if not value:
        return None

    value = (value[:-1] if value.endswith("T") else value).strip()

    try:
        dt = datetime.strptime(value, "%a, %b %d, %Y")
        return dt.date()
    except ValueError:
        return None
