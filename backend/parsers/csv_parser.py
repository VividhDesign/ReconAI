"""
ReconAI — CSV Parser for Payment Gateway Exports
Handles Razorpay, Stripe, PayTM CSV formats with normalization.
"""
import csv
import io
from datetime import datetime
from typing import List, Tuple, Union

from backend.models import TransactionSource


# Expected column mappings per gateway
COLUMN_MAPS = {
    "razorpay": {
        "transaction_id": ["Payment ID", "payment_id", "Transaction ID", "id"],
        "amount": ["Amount", "amount", "Total Amount"],
        "payment_method": ["Method", "method", "Payment Method"],
        "payment_detail": ["Card Network", "UPI ID", "Bank", "Wallet"],
        "reference_id": ["Order ID", "order_id", "Reference"],
        "merchant_id": ["Merchant ID", "merchant_id"],
        "status": ["Status", "status"],
        "gateway_fee": ["Fee", "fee", "MDR"],
        "tax_on_fee": ["Tax", "tax", "GST"],
        "settlement_amount": ["Settlement Amount", "settlement_amount"],
        "transaction_time": ["Created At", "created_at", "Date", "Timestamp"],
        "customer_email": ["Email", "email", "Customer Email"],
    },
    "stripe": {
        "transaction_id": ["id", "Payment Intent", "Charge ID"],
        "amount": ["Amount", "amount"],
        "payment_method": ["Payment Method Type", "Type"],
        "payment_detail": ["Card Brand", "Card Last4"],
        "reference_id": ["Description", "Metadata"],
        "status": ["Status", "status"],
        "gateway_fee": ["Fee", "Stripe Fee"],
        "transaction_time": ["Created", "Created (UTC)", "Date"],
        "customer_email": ["Customer Email", "Email"],
    },
    "paytm": {
        "transaction_id": ["Order Id", "Transaction ID", "TXNID"],
        "amount": ["TXNAMOUNT", "Amount", "Transaction Amount"],
        "payment_method": ["PAYMENTMODE", "Payment Mode"],
        "reference_id": ["ORDERID", "Order ID"],
        "status": ["STATUS", "Status"],
        "transaction_time": ["TXNDATE", "Transaction Date", "Date"],
    },
}

# Date format patterns to try
DATE_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%d/%m/%Y %H:%M:%S",
    "%d-%m-%Y %H:%M:%S",
    "%d %b %Y, %H:%M",
    "%d %b %Y %H:%M:%S",
    "%m/%d/%Y %H:%M:%S",
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d%m%Y",  # SBI non-standard format
]


def detect_source(headers: List[str]) -> str:
    """Detect the gateway source based on CSV headers."""
    header_set = set(h.strip().lower() for h in headers)

    if any(k in header_set for k in ["payment id", "payment_id", "razorpay"]):
        return "razorpay"
    elif any(k in header_set for k in ["payment intent", "stripe fee", "charge id"]):
        return "stripe"
    elif any(k in header_set for k in ["txnid", "paymentmode", "txnamount"]):
        return "paytm"
    return "other"


def find_column(row: dict, candidates: List[str]) -> str:
    """Find the first matching column name from candidates."""
    for candidate in candidates:
        # Try exact match
        if candidate in row:
            return row[candidate]
        # Try case-insensitive
        for key in row:
            if key.strip().lower() == candidate.lower():
                return row[key]
    return ""


def parse_date(date_str: str) -> datetime:
    """Parse a date string trying multiple formats."""
    if not date_str:
        return datetime.utcnow()

    date_str = date_str.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    # Last resort: try parsing with common separators removed
    cleaned = date_str.replace("T", " ").replace("Z", "").strip()
    for fmt in DATE_FORMATS[:6]:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue

    raise ValueError(f"Cannot parse date: {date_str}")


def parse_amount(amount_str: str) -> float:
    """Parse amount string, handling currency symbols and commas."""
    if not amount_str:
        return 0.0
    # Remove currency symbols and commas
    cleaned = str(amount_str).replace("₹", "").replace("$", "").replace(",", "").strip()
    # Handle parentheses for negative numbers
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def parse_gateway_csv(
    file_content: Union[str, bytes],
    source_override: str = None,
) -> Tuple[List[dict], List[str]]:
    """
    Parse a payment gateway CSV file and return normalized transaction records.

    Returns:
        Tuple of (records, errors)
    """
    if isinstance(file_content, bytes):
        file_content = file_content.decode("utf-8-sig")  # Handle BOM

    reader = csv.DictReader(io.StringIO(file_content))
    headers = reader.fieldnames or []

    source = source_override or detect_source(headers)
    col_map = COLUMN_MAPS.get(source, COLUMN_MAPS["razorpay"])

    records = []
    errors = []

    for row_num, row in enumerate(reader, start=2):
        try:
            txn_id = find_column(row, col_map.get("transaction_id", []))
            if not txn_id:
                errors.append(f"Row {row_num}: Missing transaction ID")
                continue

            amount = parse_amount(find_column(row, col_map.get("amount", [])))
            if amount <= 0:
                errors.append(f"Row {row_num}: Invalid amount for {txn_id}")
                continue

            txn_time_str = find_column(row, col_map.get("transaction_time", []))
            try:
                txn_time = parse_date(txn_time_str)
            except ValueError as e:
                errors.append(f"Row {row_num}: {str(e)} for {txn_id}")
                txn_time = datetime.utcnow()

            gateway_fee = parse_amount(
                find_column(row, col_map.get("gateway_fee", []))
            )
            tax_on_fee = parse_amount(
                find_column(row, col_map.get("tax_on_fee", []))
            )
            settlement_str = find_column(row, col_map.get("settlement_amount", []))
            settlement_amount = parse_amount(settlement_str) if settlement_str else (
                amount - gateway_fee - tax_on_fee
            )

            record = {
                "transaction_id": txn_id.strip(),
                "source": source,
                "amount": amount,
                "currency": "INR",
                "payment_method": find_column(
                    row, col_map.get("payment_method", [])
                ) or None,
                "payment_detail": find_column(
                    row, col_map.get("payment_detail", [])
                ) or None,
                "merchant_id": find_column(
                    row, col_map.get("merchant_id", [])
                ) or None,
                "merchant_name": None,
                "customer_email": find_column(
                    row, col_map.get("customer_email", [])
                ) or None,
                "reference_id": find_column(
                    row, col_map.get("reference_id", [])
                ) or None,
                "order_id": find_column(
                    row, col_map.get("reference_id", [])
                ) or None,
                "status": find_column(
                    row, col_map.get("status", [])
                ) or "captured",
                "gateway_fee": gateway_fee,
                "tax_on_fee": tax_on_fee,
                "settlement_amount": settlement_amount,
                "transaction_time": txn_time,
            }

            # Build embedding text for fuzzy matching
            record["embedding_text"] = (
                f"{txn_id} {source} {amount} {record['payment_method'] or ''} "
                f"{record['reference_id'] or ''} {txn_time.isoformat()}"
            )

            records.append(record)

        except Exception as e:
            errors.append(f"Row {row_num}: Unexpected error — {str(e)}")

    return records, errors
