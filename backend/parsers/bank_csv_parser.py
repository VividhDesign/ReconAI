"""
ReconAI — Bank CSV Parser
Simple CSV parser for bank settlement files (alternative to MT940/OFX).
"""
import csv
import io
from datetime import datetime
from typing import List, Tuple, Union

from backend.parsers.csv_parser import parse_date, parse_amount


# Column mappings for bank CSVs
BANK_COLUMN_MAPS = {
    "hdfc": {
        "bank_reference": ["Ref No", "Reference", "Txn Ref", "Transaction ID"],
        "amount": ["Amount", "Cr Amount", "Credit Amount", "Withdrawal Amt(INR)", "Deposit Amt(INR)"],
        "transaction_type": ["Type", "Cr/Dr", "Transaction Type"],
        "narration": ["Narration", "Description", "Particulars", "Remarks"],
        "value_date": ["Date", "Value Date", "Txn Date", "Transaction Date"],
        "posting_date": ["Posting Date"],
        "merchant_reference": ["Chq/Ref No", "Reference No", "UTR", "Merchant Ref"],
        "utr_number": ["UTR", "UTR Number", "UTR No"],
        "closing_balance": ["Balance", "Closing Balance"],
    },
    "default": {
        "bank_reference": ["Reference", "Ref", "Transaction ID", "Txn ID"],
        "amount": ["Amount", "Credit", "Debit"],
        "transaction_type": ["Type", "Dr/Cr"],
        "narration": ["Description", "Narration", "Particulars"],
        "value_date": ["Date", "Value Date", "Transaction Date"],
        "merchant_reference": ["Reference", "Merchant Ref", "UTR"],
        "utr_number": ["UTR", "UTR Number"],
    },
}


def find_column(row: dict, candidates: List[str]) -> str:
    """Find the first matching column name from candidates."""
    for candidate in candidates:
        if candidate in row:
            return row[candidate]
        for key in row:
            if key.strip().lower() == candidate.lower():
                return row[key]
    return ""


def parse_bank_csv(
    file_content: Union[str, bytes],
    bank: str = "hdfc",
) -> Tuple[List[dict], List[str]]:
    """
    Parse a bank settlement CSV file.

    Returns:
        Tuple of (records, errors)
    """
    if isinstance(file_content, bytes):
        file_content = file_content.decode("utf-8-sig")

    reader = csv.DictReader(io.StringIO(file_content))
    col_map = BANK_COLUMN_MAPS.get(bank, BANK_COLUMN_MAPS["default"])

    records = []
    errors = []

    for row_num, row in enumerate(reader, start=2):
        try:
            bank_ref = find_column(row, col_map.get("bank_reference", []))
            if not bank_ref:
                bank_ref = f"{bank.upper()}_ROW_{row_num}"

            amount_str = find_column(row, col_map.get("amount", []))
            amount = parse_amount(amount_str)
            if amount <= 0:
                errors.append(f"Row {row_num}: Invalid amount")
                continue

            date_str = find_column(row, col_map.get("value_date", []))
            try:
                value_date = parse_date(date_str)
            except ValueError:
                errors.append(f"Row {row_num}: Cannot parse date '{date_str}'")
                value_date = datetime.utcnow()

            posting_str = find_column(row, col_map.get("posting_date", []))
            posting_date = None
            if posting_str:
                try:
                    posting_date = parse_date(posting_str)
                except ValueError:
                    pass

            txn_type = find_column(row, col_map.get("transaction_type", []))
            if not txn_type:
                txn_type = "CR"

            narration = find_column(row, col_map.get("narration", []))
            merchant_ref = find_column(row, col_map.get("merchant_reference", []))
            utr = find_column(row, col_map.get("utr_number", []))

            balance_str = find_column(row, col_map.get("closing_balance", []))
            closing_balance = parse_amount(balance_str) if balance_str else None

            record = {
                "bank_reference": bank_ref.strip(),
                "bank": bank,
                "amount": amount,
                "currency": "INR",
                "transaction_type": txn_type.strip().upper()[:2],
                "narration": narration or None,
                "value_date": value_date,
                "posting_date": posting_date,
                "merchant_reference": merchant_ref or None,
                "utr_number": utr or None,
                "closing_balance": closing_balance,
                "embedding_text": (
                    f"{bank_ref} {bank} {amount} {txn_type} "
                    f"{merchant_ref} {narration} {value_date.isoformat()}"
                ),
            }

            records.append(record)

        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")

    return records, errors
