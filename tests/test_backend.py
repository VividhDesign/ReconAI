"""
ReconAI — Test Suite
Validates parsers, reconciliation matching engine, exception analyzer, and audit logging.
Compatible with standard library unittest and pytest.
"""
import unittest
from datetime import datetime

from backend.parsers.csv_parser import parse_gateway_csv
from backend.parsers.mt940_parser import parse_mt940
from backend.parsers.bank_csv_parser import parse_bank_csv
from backend.services.reconciliation_engine import string_similarity, extract_potential_refs
from backend.services.audit_logger import compute_log_hash


class TestReconAI(unittest.TestCase):

    def test_razorpay_csv_parser(self):
        """Test parsing standard Razorpay transaction export."""
        csv_data = """Payment ID,Amount,Method,Order ID,Fee,Tax,Created At,Status
pay_test_001,15000.00,UPI,order_test_901,270.00,48.60,2026-09-01 10:30:00,captured
pay_test_002,2500.50,card,order_test_902,50.00,9.00,2026-09-01 11:15:00,captured
"""
        records, errors = parse_gateway_csv(csv_data)
        self.assertEqual(len(records), 2)
        self.assertEqual(len(errors), 0)
        self.assertEqual(records[0]["transaction_id"], "pay_test_001")
        self.assertEqual(records[0]["amount"], 15000.00)
        self.assertEqual(str(records[0]["source"]), "razorpay")
        self.assertEqual(records[0]["settlement_amount"], 14681.40)

    def test_mt940_bank_parser(self):
        """Test parsing SWIFT MT940 bank statement."""
        mt940_data = """:20:START
:25:HDFCBANK0012345
:28C:001/1
:60F:C260901INR100000,00
:61:2609010901CR15000,00NTRFNONREF//BNK-REF-001
:86:CMS/COLL/RAZORPAY/STL/order_test_901/UTRHDFC001234
:62F:C260901INR115000,00
-"""
        records, errors = parse_mt940(mt940_data)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["amount"], 15000.00)
        self.assertEqual(str(records[0]["bank"]), "hdfc")
        self.assertIn("order_test_901", records[0]["narration"])

    def test_bank_csv_parser(self):
        """Test parsing bank settlement CSV."""
        bank_csv = """Ref No,Amount,Type,Narration,Date,UTR
BNK-CSV-01,14681.40,CR,CMS/STL/order_test_901,2026-09-02,UTRHDFC999
"""
        records, errors = parse_bank_csv(bank_csv, "hdfc")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["amount"], 14681.40)
        self.assertEqual(records[0]["bank_reference"], "BNK-CSV-01")

    def test_string_similarity_and_extraction(self):
        """Test fuzzy similarity matching and token extraction."""
        sim_exact = string_similarity("order_test_901", "order_test_901")
        self.assertGreaterEqual(sim_exact, 0.95)

        sim_diff = string_similarity("order_test_901", "order_unrelated_888")
        self.assertLess(sim_diff, 0.80)

        refs = extract_potential_refs("CMS/COLL/RAZORPAY/STL/order_test_901/UTRHDFC001234")
        self.assertTrue("ORDER_TEST_901" in refs or "order_test_901".upper() in refs)

    def test_audit_hash_computation(self):
        """Test SHA-256 hash chaining logic."""
        prev = "GENESIS_ROOT_HASH_RECON_AI"
        now = datetime(2026, 9, 5, 12, 0, 0)
        h1 = compute_log_hash(prev, now, "system", "BATCH_RUN", "batch", "b1", "details")
        self.assertEqual(len(h1), 64)

        h2 = compute_log_hash(h1, now, "user", "APPROVE", "exception", "e1", "approved")
        self.assertEqual(len(h2), 64)
        self.assertNotEqual(h1, h2)


if __name__ == "__main__":
    unittest.main()
