"""
ReconAI — Seed Data Generator
Generates realistic multi-source payment gateway transactions (Razorpay, Stripe, PayTM)
and bank settlements (HDFC, ICICI, SBI, Axis) for demonstration and testing.
"""
import asyncio
import random
from datetime import datetime, timedelta

from backend.database import async_session, init_db
from backend.models import (
    GatewayTransaction, BankTransaction, TransactionSource,
    BankName, MatchStatus
)
from backend.services.reconciliation_engine import ReconciliationEngine
from backend.services.audit_logger import AuditLogger, AuditActor


MERCHANTS = [
    ("merch_01", "Swiggy India"),
    ("merch_02", "Zomato Ltd"),
    ("merch_03", "Flipkart Internet"),
    ("merch_04", "BookMyShow"),
    ("merch_05", "Zerodha Broking"),
]

PAYMENT_METHODS = [
    ("UPI", "user@okhdfcbank"),
    ("UPI", "pay@icici"),
    ("UPI", "9876543210@paytm"),
    ("Card", "VISA 4111-XXXX-XXXX-1234"),
    ("Card", "Mastercard 5424-XXXX-XXXX-5678"),
    ("NetBanking", "HDFC NetBanking Direct"),
]


async def seed_database():
    """Populate database with realistic demonstration transactions."""
    await init_db()

    async with async_session() as db:
        engine = ReconciliationEngine(db)

        # Check if records already exist
        from sqlalchemy import select, func
        count = await db.scalar(select(func.count(GatewayTransaction.id)))
        if count and count > 10:
            print(f"Database already populated with {count} transactions.")
            return

        print("Generating realistic synthetic financial data for ReconAI...")

        now = datetime.utcnow()
        gw_records = []
        bank_records = []

        # Base counter for IDs
        counter = 1000

        # 1. Generate 40 Transactions that match EXACTLY
        for i in range(40):
            counter += 1
            source = random.choice([TransactionSource.RAZORPAY, TransactionSource.STRIPE, TransactionSource.PAYTM])
            bank = random.choice([BankName.HDFC, BankName.ICICI, BankName.SBI, BankName.AXIS])
            merchant = random.choice(MERCHANTS)
            pm, pd = random.choice(PAYMENT_METHODS)

            amount = round(random.uniform(500.0, 45000.0), 2)
            fee_rate = 0.018 if source == TransactionSource.RAZORPAY else (0.025 if source == TransactionSource.STRIPE else 0.012)
            gateway_fee = round(amount * fee_rate, 2)
            tax_on_fee = round(gateway_fee * 0.18, 2)
            settlement_amount = round(amount - gateway_fee - tax_on_fee, 2)

            txn_time = now - timedelta(days=random.randint(1, 4), hours=random.randint(1, 23))
            value_date = txn_time + timedelta(days=1, hours=4)  # T+1 settlement

            pay_id = f"pay_{source.value[:3]}_{counter}"
            order_id = f"order_99_{counter}"
            utr = f"UTR{bank.value.upper()}{counter:06d}"

            gw = GatewayTransaction(
                transaction_id=pay_id,
                source=source,
                amount=amount,
                currency="INR",
                payment_method=pm,
                payment_detail=pd,
                merchant_id=merchant[0],
                merchant_name=merchant[1],
                reference_id=order_id,
                order_id=order_id,
                status="captured",
                gateway_fee=gateway_fee,
                tax_on_fee=tax_on_fee,
                settlement_amount=settlement_amount,
                transaction_time=txn_time,
                match_status=MatchStatus.PENDING,
            )
            gw_records.append(gw)

            narration = f"CMS/COLL/{source.value.upper()}/STL/{order_id}/{utr}"
            bank_txn = BankTransaction(
                bank_reference=f"BNK-REF-{counter}",
                bank=bank,
                amount=amount,  # Gross settlement match
                currency="INR",
                transaction_type="CR",
                narration=narration,
                value_date=value_date,
                posting_date=value_date,
                merchant_reference=order_id,
                utr_number=utr,
                match_status=MatchStatus.PENDING,
            )
            bank_records.append(bank_txn)

        # 2. Generate 8 Transactions that match FUZZY (SBI truncated references / net settlement)
        for i in range(8):
            counter += 1
            amount = round(random.uniform(1000.0, 25000.0), 2)
            gateway_fee = round(amount * 0.02, 2)
            tax_on_fee = round(gateway_fee * 0.18, 2)
            settlement_amount = round(amount - gateway_fee - tax_on_fee, 2)

            txn_time = now - timedelta(days=random.randint(2, 5))
            value_date = txn_time + timedelta(days=2)

            pay_id = f"pay_rzp_{counter}"
            order_id = f"order_fuzz_{counter}"
            utr = f"UTRSBI{counter:06d}"

            gw = GatewayTransaction(
                transaction_id=pay_id,
                source=TransactionSource.RAZORPAY,
                amount=amount,
                currency="INR",
                payment_method="UPI",
                payment_detail="customer@sbi",
                reference_id=order_id,
                order_id=order_id,
                status="captured",
                gateway_fee=gateway_fee,
                tax_on_fee=tax_on_fee,
                settlement_amount=settlement_amount,
                transaction_time=txn_time,
                match_status=MatchStatus.PENDING,
            )
            gw_records.append(gw)

            # Bank settled net amount with truncated narration
            bank_txn = BankTransaction(
                bank_reference=f"BNK-REF-{counter}",
                bank=BankName.SBI,
                amount=settlement_amount,  # Net settlement amount
                currency="INR",
                transaction_type="CR",
                narration=f"INB/UPI/{order_id[:10]}/NET_STL",
                value_date=value_date,
                posting_date=value_date,
                merchant_reference=order_id[:10],
                utr_number=utr,
                match_status=MatchStatus.PENDING,
            )
            bank_records.append(bank_txn)

        # 3. Generate 3 Discrepant Transactions (Exceptions)
        # Exception A: Amount mismatch (MDR variance dispute)
        counter += 1
        pay_id_mismatch = f"pay_rzp_{counter}"
        order_id_mismatch = f"order_mismatch_{counter}"
        gw_exc1 = GatewayTransaction(
            transaction_id=pay_id_mismatch,
            source=TransactionSource.RAZORPAY,
            amount=42500.00,
            currency="INR",
            payment_method="Card",
            payment_detail="Corporate VISA Platinum",
            reference_id=order_id_mismatch,
            order_id=order_id_mismatch,
            status="captured",
            gateway_fee=850.00,
            tax_on_fee=153.00,
            settlement_amount=41497.00,
            transaction_time=now - timedelta(days=2),
            match_status=MatchStatus.PENDING,
        )
        gw_records.append(gw_exc1)

        bank_exc1 = BankTransaction(
            bank_reference=f"BNK-HDFC-{counter}",
            bank=BankName.HDFC,
            amount=41195.00,  # ₹302 extra fee deducted
            currency="INR",
            transaction_type="CR",
            narration=f"CMS/RAZORPAY/{order_id_mismatch}/MDR_ADJ",
            value_date=now - timedelta(days=1),
            merchant_reference=order_id_mismatch,
            utr_number=f"UTRHDFC{counter:06d}",
            match_status=MatchStatus.PENDING,
        )
        bank_records.append(bank_exc1)

        # Exception B: Missing Bank Settlement (T+2 SLA breached)
        counter += 1
        gw_exc2 = GatewayTransaction(
            transaction_id=f"pay_str_{counter}",
            source=TransactionSource.STRIPE,
            amount=18400.00,
            currency="INR",
            payment_method="Card",
            payment_detail="AMEX Centurion",
            reference_id=f"order_delayed_{counter}",
            order_id=f"order_delayed_{counter}",
            status="captured",
            gateway_fee=552.00,
            tax_on_fee=99.36,
            settlement_amount=17748.64,
            transaction_time=now - timedelta(days=4),  # 4 days ago!
            match_status=MatchStatus.PENDING,
        )
        gw_records.append(gw_exc2)

        # Exception C: Missing Gateway Capture (Direct Bank Credit / Dropped Webhook)
        counter += 1
        bank_exc3 = BankTransaction(
            bank_reference=f"BNK-ICICI-{counter}",
            bank=BankName.ICICI,
            amount=29800.00,
            currency="INR",
            transaction_type="CR",
            narration="NEFT/DIRECT/VENDOR_SETTLEMENT/ICIC0001",
            value_date=now - timedelta(days=1),
            merchant_reference=f"REF-DIR-{counter}",
            utr_number=f"UTRICICI{counter:06d}",
            match_status=MatchStatus.PENDING,
        )
        bank_records.append(bank_exc3)

        # Insert all into DB
        db.add_all(gw_records)
        db.add_all(bank_records)
        await db.commit()

        print(f"Inserted {len(gw_records)} gateway records and {len(bank_records)} bank records.")
        print("Running initial automated multi-tier reconciliation engine...")

        # Run Reconciliation Engine
        batch = await engine.run_reconciliation(batch_name="Initial_Master_Batch_2026")

        print(f"Reconciliation completed successfully!")
        print(f"Batch ID: {batch.id}")
        print(f"Exact Matches: {batch.exact_matches}")
        print(f"Fuzzy Matches: {batch.fuzzy_matches}")
        print(f"Exceptions Flagged: {batch.exceptions}")
        print(f"Automated Match Rate: {batch.match_rate}%")
        print(f"Time Taken: {batch.processing_time_seconds}s")


if __name__ == "__main__":
    asyncio.run(seed_database())
