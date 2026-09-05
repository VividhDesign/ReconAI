"""
ReconAI — MT940 Bank Statement Parser
Handles SWIFT MT940 format used by Indian banks (HDFC, ICICI, SBI, Axis).
Includes SBI non-standard format workarounds.
"""
import re
from datetime import datetime
from typing import List, Tuple, Union


# MT940 tag patterns
TAG_PATTERNS = {
    "account": re.compile(r":25:(.+)"),
    "statement_number": re.compile(r":28C:(.+)"),
    "opening_balance": re.compile(r":60[FM]:([CD])(\d{6})([A-Z]{3})([\d,]+)"),
    "transaction": re.compile(r":61:(\d{6})(\d{4})?([CD])([A-Z]?)([\d,]+)(.{4})(.*)"),
    "info": re.compile(r":86:(.+)"),
    "closing_balance": re.compile(r":62[FM]:([CD])(\d{6})([A-Z]{3})([\d,]+)"),
}

# Bank detection from account patterns
BANK_PATTERNS = {
    "hdfc": ["HDFC", "hdfc", "HDFCBANK"],
    "icici": ["ICICI", "icici", "ICICINDIA"],
    "sbi": ["SBI", "sbi", "SBININBB", "STATE BANK"],
    "axis": ["AXIS", "axis", "UTIB", "AXISINBB"],
    "kotak": ["KOTAK", "kotak", "KKBK"],
}


def detect_bank(content: str) -> str:
    """Detect bank from MT940 content."""
    upper = content[:500].upper()
    for bank, patterns in BANK_PATTERNS.items():
        if any(p.upper() in upper for p in patterns):
            return bank
    return "other"


def parse_mt940_date(date_str: str, bank: str = "other") -> datetime:
    """
    Parse MT940 date format.
    Standard: YYMMDD
    SBI non-standard: DDMMYY or DDMMYYYY
    """
    date_str = date_str.strip()

    if bank == "sbi" and len(date_str) == 8:
        # SBI uses DDMMYYYY
        try:
            return datetime.strptime(date_str, "%d%m%Y")
        except ValueError:
            pass

    if len(date_str) == 6:
        # Standard YYMMDD
        try:
            return datetime.strptime(date_str, "%y%m%d")
        except ValueError:
            pass
        # Try DDMMYY (SBI variant)
        try:
            return datetime.strptime(date_str, "%d%m%y")
        except ValueError:
            pass

    raise ValueError(f"Cannot parse MT940 date: {date_str}")


def parse_mt940_amount(amount_str: str) -> float:
    """Parse MT940 amount (uses comma as decimal separator)."""
    return float(amount_str.replace(",", "."))


def extract_merchant_reference(info_line: str, bank: str) -> str:
    """
    Extract merchant reference from :86: information line.
    Different banks encode references differently.
    """
    if not info_line:
        return ""

    # SBI truncates references to 12 chars — we handle this in fuzzy matching
    if bank == "sbi":
        # Try to find reference pattern
        ref_match = re.search(r"REF[:\s]*(\S+)", info_line, re.IGNORECASE)
        if ref_match:
            return ref_match.group(1)[:12]  # SBI truncation

    # HDFC uses /REF/ tag
    ref_match = re.search(r"/REF/(\S+)", info_line)
    if ref_match:
        return ref_match.group(1)

    # ICICI uses CUSTREF
    ref_match = re.search(r"CUSTREF[:\s]*(\S+)", info_line, re.IGNORECASE)
    if ref_match:
        return ref_match.group(1)

    # Generic: try to find any alphanumeric reference-like string
    ref_match = re.search(r"(?:REF|TXN|PAY|ORD)[_\-:\s]*([A-Za-z0-9_]+)", info_line, re.IGNORECASE)
    if ref_match:
        return ref_match.group(1)

    return info_line.strip()[:50]  # Fallback: first 50 chars


def parse_mt940(
    file_content: Union[str, bytes],
    bank_override: str = None,
) -> Tuple[List[dict], List[str]]:
    """
    Parse an MT940 bank statement file.

    Returns:
        Tuple of (records, errors)
    """
    if isinstance(file_content, bytes):
        file_content = file_content.decode("utf-8", errors="replace")

    bank = bank_override or detect_bank(file_content)
    records = []
    errors = []

    # Split into statement blocks
    blocks = re.split(r"\n(?=:20:)", file_content)

    for block in blocks:
        lines = block.strip().split("\n")
        current_txn = None
        closing_balance = None

        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue

            # Transaction line :61:
            txn_match = TAG_PATTERNS["transaction"].match(line)
            if txn_match:
                if current_txn:
                    records.append(current_txn)

                value_date_str = txn_match.group(1)
                entry_date_str = txn_match.group(2) or ""
                dc_mark = txn_match.group(3)  # C=Credit, D=Debit
                funds_code = txn_match.group(4)
                amount_str = txn_match.group(5)
                txn_type = txn_match.group(6).strip()
                reference = txn_match.group(7).strip() if txn_match.group(7) else ""

                try:
                    value_date = parse_mt940_date(value_date_str, bank)
                except ValueError as e:
                    errors.append(f"Date parse error: {e}")
                    value_date = datetime.utcnow()

                posting_date = None
                if entry_date_str:
                    try:
                        # Entry date is MMDD, use value_date's year
                        month = int(entry_date_str[:2])
                        day = int(entry_date_str[2:4])
                        posting_date = value_date.replace(month=month, day=day)
                    except (ValueError, IndexError):
                        pass

                amount = parse_mt940_amount(amount_str)

                # Generate a unique bank reference
                bank_ref = f"{bank.upper()}_{reference}" if reference else (
                    f"{bank.upper()}_REF_{value_date_str}_{amount_str}"
                )

                current_txn = {
                    "bank_reference": bank_ref.strip(),
                    "bank": bank,
                    "amount": amount,
                    "currency": "INR",
                    "transaction_type": dc_mark,  # C or D
                    "narration": "",
                    "value_date": value_date,
                    "posting_date": posting_date,
                    "merchant_reference": "",
                    "utr_number": reference,
                }
                continue

            # Information line :86:
            info_match = TAG_PATTERNS["info"].match(line)
            if info_match and current_txn:
                info_text = info_match.group(1).strip()
                current_txn["narration"] = info_text
                current_txn["merchant_reference"] = extract_merchant_reference(
                    info_text, bank
                )

                # Build embedding text
                current_txn["embedding_text"] = (
                    f"{current_txn['bank_reference']} {bank} "
                    f"{current_txn['amount']} {current_txn['transaction_type']} "
                    f"{current_txn['merchant_reference']} "
                    f"{current_txn['value_date'].isoformat()}"
                )
                continue

            # Closing balance :62F:
            balance_match = TAG_PATTERNS["closing_balance"].match(line)
            if balance_match:
                closing_balance = parse_mt940_amount(balance_match.group(4))

        # Don't forget the last transaction in block
        if current_txn:
            if closing_balance is not None:
                current_txn["closing_balance"] = closing_balance
            records.append(current_txn)

    # Post-processing: ensure unique bank references
    seen_refs = set()
    for record in records:
        ref = record["bank_reference"]
        if ref in seen_refs:
            record["bank_reference"] = f"{ref}_{len(seen_refs)}"
        seen_refs.add(record["bank_reference"])

        # Default embedding text if missing
        if "embedding_text" not in record:
            record["embedding_text"] = (
                f"{record['bank_reference']} {bank} "
                f"{record['amount']} {record.get('narration', '')}"
            )

    return records, errors
