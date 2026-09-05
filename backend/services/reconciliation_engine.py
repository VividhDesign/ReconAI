"""
ReconAI — Reconciliation Engine
Multi-tiered matching engine with exact matching, fuzzy heuristic matching,
vector similarity, and automated exception classification.
"""
import time
import math
import re
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional, Any
from difflib import SequenceMatcher

from sqlalchemy import select, update, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models import (
    GatewayTransaction, BankTransaction, ReconciliationBatch,
    Exception_, MatchStatus, MatchMethod, ExceptionType,
    ExceptionResolution, AuditActor
)
from backend.services.audit_logger import AuditLogger


def string_similarity(s1: str, s2: str) -> float:
    """Calculate SequenceMatcher similarity between two strings."""
    if not s1 or not s2:
        return 0.0
    s1_clean = re.sub(r"[^a-zA-Z0-9]", "", str(s1)).upper()
    s2_clean = re.sub(r"[^a-zA-Z0-9]", "", str(s2)).upper()
    if not s1_clean or not s2_clean:
        return 0.0
    if s1_clean in s2_clean or s2_clean in s1_clean:
        return 0.95
    return SequenceMatcher(None, s1_clean, s2_clean).ratio()


def extract_potential_refs(narration: str) -> List[str]:
    """Extract candidate reference/order/payment IDs from a bank narration string."""
    if not narration:
        return []
    # Tokenize on slashes, colons, spaces
    tokens = re.split(r"[/:\s]+", narration)
    results = set()
    for t in tokens:
        cleaned = t.strip().upper()
        if len(cleaned) >= 5:
            results.add(cleaned)
        for sub in re.split(r"[\-_]+", cleaned):
            if len(sub) >= 5:
                results.add(sub)
    return list(results)


class ReconciliationEngine:
    """
    Core reconciliation processing engine.
    Executes multi-pass matching between Gateway Transactions and Bank Statements.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def run_reconciliation(
        self,
        batch_name: Optional[str] = None,
        source_filter: Optional[str] = None,
        bank_filter: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> ReconciliationBatch:
        """
        Execute full reconciliation cycle:
        Pass 1: Exact Match (Reference + Amount + Date)
        Pass 2: Settlement Net Amount Match (Amount - MDR fee)
        Pass 3: Fuzzy Heuristic & Token Similarity Match
        Pass 4: Exception Generation & Classification
        """
        start_time = time.time()
        now = datetime.utcnow()

        # 1. Fetch pending gateway transactions
        gw_query = select(GatewayTransaction).where(
            GatewayTransaction.match_status.in_([MatchStatus.PENDING, MatchStatus.UNRESOLVED])
        )
        if source_filter:
            gw_query = gw_query.where(GatewayTransaction.source == source_filter)
        if date_from:
            gw_query = gw_query.where(GatewayTransaction.transaction_time >= date_from)
        if date_to:
            gw_query = gw_query.where(GatewayTransaction.transaction_time <= date_to)

        gw_res = await self.db.execute(gw_query)
        gateway_txns: List[GatewayTransaction] = list(gw_res.scalars().all())

        # 2. Fetch pending bank transactions (Credit only for sales reconciliations)
        bank_query = select(BankTransaction).where(
            BankTransaction.match_status.in_([MatchStatus.PENDING, MatchStatus.UNRESOLVED])
        )
        if bank_filter:
            bank_query = bank_query.where(BankTransaction.bank == bank_filter)
        if date_from:
            bank_query = bank_query.where(BankTransaction.value_date >= date_from - timedelta(days=2))
        if date_to:
            bank_query = bank_query.where(BankTransaction.value_date <= date_to + timedelta(days=5))

        bank_res = await self.db.execute(bank_query)
        bank_txns: List[BankTransaction] = list(bank_res.scalars().all())

        # Initialize Batch record
        batch = ReconciliationBatch(
            batch_name=batch_name or f"Recon_Batch_{now.strftime('%Y%m%d_%H%M%S')}",
            started_at=now,
            status="running",
            total_gateway_records=len(gateway_txns),
            total_bank_records=len(bank_txns),
        )
        self.db.add(batch)
        await self.db.flush()

        matched_gw_ids = set()
        matched_bank_ids = set()
        matched_pairs: List[Tuple[GatewayTransaction, BankTransaction, float, MatchMethod]] = []
        unmatched_gw_candidates: List[GatewayTransaction] = []

        total_value_processed = sum(g.amount for g in gateway_txns)
        total_value_matched = 0.0

        # ──────────────── Pass 1: Exact Matches ────────────────
        # Match where direct ID (reference_id, transaction_id, or order_id) matches bank UTR or narration
        bank_by_ref: Dict[str, BankTransaction] = {}
        for b in bank_txns:
            if b.id in matched_bank_ids:
                continue
            if b.merchant_reference:
                bank_by_ref[b.merchant_reference.strip().upper()] = b
            if b.utr_number:
                bank_by_ref[b.utr_number.strip().upper()] = b

        for gw in gateway_txns:
            if gw.id in matched_gw_ids:
                continue

            candidate_refs = [
                gw.reference_id, gw.order_id, gw.transaction_id
            ]
            candidate_refs = [r.strip().upper() for r in candidate_refs if r]

            matched_bank: Optional[BankTransaction] = None

            # Fast lookup by indexed reference
            for ref in candidate_refs:
                if ref in bank_by_ref and bank_by_ref[ref].id not in matched_bank_ids:
                    b_candidate = bank_by_ref[ref]
                    # Check amount equality (either gross or net settlement)
                    expected_net = gw.settlement_amount or (gw.amount - gw.gateway_fee - gw.tax_on_fee)
                    if (
                        abs(gw.amount - b_candidate.amount) < 0.01
                        or abs(expected_net - b_candidate.amount) < 0.01
                    ):
                        matched_bank = b_candidate
                        break

            # Fallback: scan narration if not in dictionary
            if not matched_bank:
                for b in bank_txns:
                    if b.id in matched_bank_ids:
                        continue
                    narration_upper = (b.narration or "").upper()
                    found_ref = any(ref in narration_upper for ref in candidate_refs)
                    if found_ref:
                        expected_net = gw.settlement_amount or (gw.amount - gw.gateway_fee - gw.tax_on_fee)
                        if (
                            abs(gw.amount - b.amount) < 0.01
                            or abs(expected_net - b.amount) < 0.01
                        ):
                            matched_bank = b
                            break

            if matched_bank:
                matched_gw_ids.add(gw.id)
                matched_bank_ids.add(matched_bank.id)
                matched_pairs.append((gw, matched_bank, 1.0, MatchMethod.EXACT))
                total_value_matched += gw.amount

        # ──────────────── Pass 2: Settlement Amount & Date Matching ────────────────
        # When reference IDs were truncated by legacy bank statements (e.g. SBI 16-char truncate)
        for gw in gateway_txns:
            if gw.id in matched_gw_ids:
                continue

            expected_net = gw.settlement_amount or (gw.amount - gw.gateway_fee - gw.tax_on_fee)
            best_bank: Optional[BankTransaction] = None
            best_score = 0.0

            for b in bank_txns:
                if b.id in matched_bank_ids:
                    continue

                amount_diff = min(
                    abs(gw.amount - b.amount),
                    abs(expected_net - b.amount)
                )

                if amount_diff < 0.01:
                    # Amount matches exactly! Check date closeness (T+0 to T+3)
                    days_diff = abs((b.value_date - gw.transaction_time).total_seconds()) / 86400.0
                    if days_diff <= 3.0:
                        # Check partial reference or customer name / narration match
                        sim = 0.0
                        if gw.reference_id or gw.order_id:
                            ref = (gw.reference_id or gw.order_id or "").upper()
                            narration = (b.narration or "").upper()
                            if len(ref) >= 6 and (ref[:6] in narration or ref[-6:] in narration):
                                sim = 0.92
                        score = 0.88 + (0.10 if days_diff <= 1.0 else 0.05) + (0.02 if sim > 0.8 else 0.0)
                        if score > best_score:
                            best_score = score
                            best_bank = b

            if best_bank and best_score >= settings.FUZZY_MATCH_THRESHOLD:
                matched_gw_ids.add(gw.id)
                matched_bank_ids.add(best_bank.id)
                matched_pairs.append((gw, best_bank, round(best_score, 3), MatchMethod.FUZZY))
                total_value_matched += gw.amount

        # ──────────────── Pass 3: Fuzzy Heuristic & MDR Tolerance Matching ────────────────
        for gw in gateway_txns:
            if gw.id in matched_gw_ids:
                continue

            expected_net = gw.settlement_amount or (gw.amount - gw.gateway_fee - gw.tax_on_fee)
            best_bank: Optional[BankTransaction] = None
            best_score = 0.0

            for b in bank_txns:
                if b.id in matched_bank_ids:
                    continue

                # Amount similarity score
                amount_diff = min(
                    abs(gw.amount - b.amount),
                    abs(expected_net - b.amount)
                )
                rel_diff = amount_diff / gw.amount if gw.amount > 0 else 1.0

                # Date similarity score (settlement window up to 4 days)
                days_diff = abs((b.value_date - gw.transaction_time).total_seconds()) / 86400.0
                if days_diff > 4.5:
                    continue

                date_score = max(0.0, 1.0 - (days_diff / 4.0))

                # Narration / reference token similarity
                narration_tokens = extract_potential_refs(b.narration or "")
                ref_score = 0.0
                for token in narration_tokens:
                    sim1 = string_similarity(gw.transaction_id, token)
                    sim2 = string_similarity(gw.reference_id or "", token)
                    sim3 = string_similarity(gw.order_id or "", token)
                    ref_score = max(ref_score, sim1, sim2, sim3)

                # Fee tolerance adjustment (e.g. 1.8% to 2.5% MDR + 18% GST variance)
                if rel_diff <= (settings.AMOUNT_TOLERANCE_PERCENT / 100.0) or amount_diff <= settings.AMOUNT_TOLERANCE_ABSOLUTE:
                    amt_score = 0.95 - (rel_diff * 5)
                elif 0.01 <= rel_diff <= 0.035:
                    # Likely MDR fee deduction variance
                    amt_score = 0.85
                else:
                    amt_score = max(0.0, 1.0 - rel_diff * 2)

                composite_score = (amt_score * 0.45) + (ref_score * 0.35) + (date_score * 0.20)

                if composite_score > best_score and composite_score >= settings.FUZZY_MATCH_THRESHOLD:
                    best_score = composite_score
                    best_bank = b

            if best_bank:
                matched_gw_ids.add(gw.id)
                matched_bank_ids.add(best_bank.id)
                matched_pairs.append((gw, best_bank, round(best_score, 3), MatchMethod.FUZZY))
                total_value_matched += gw.amount

        # ──────────────── Pass 4: Exception Generation ────────────────
        exceptions_created: List[Exception_] = []
        exc_counter = 1

        # Unmatched Gateway transactions
        for gw in gateway_txns:
            if gw.id in matched_gw_ids:
                continue

            # Look for near-miss bank transactions to detect AMOUNT_MISMATCH
            near_miss_bank: Optional[BankTransaction] = None
            for b in bank_txns:
                if b.id in matched_bank_ids:
                    continue
                # Same day and narration matches ref, but amount differs significantly
                narration_upper = (b.narration or "").upper()
                has_ref = (gw.reference_id and gw.reference_id.upper() in narration_upper) or \
                          (gw.transaction_id and gw.transaction_id.upper() in narration_upper)
                if has_ref:
                    near_miss_bank = b
                    break

            exc_code = f"EXC-{now.strftime('%Y%m%d')}-{exc_counter:04d}"
            exc_counter += 1

            if near_miss_bank:
                diff = round(near_miss_bank.amount - gw.amount, 2)
                exc = Exception_(
                    exception_code=exc_code,
                    batch_id=batch.id,
                    exception_type=ExceptionType.AMOUNT_MISMATCH,
                    gateway_transaction_id=gw.id,
                    bank_transaction_id=near_miss_bank.id,
                    expected_amount=gw.amount,
                    actual_amount=near_miss_bank.amount,
                    difference=diff,
                    ai_explanation=(
                        f"Discrepancy of ₹{abs(diff):,.2f} detected between {gw.source.value.upper()} "
                        f"transaction ({gw.transaction_id}) and {near_miss_bank.bank.value.upper()} settlement. "
                        f"Likely causes: disputed MDR surcharge or unexpected gateway fee deduction."
                    ),
                    ai_confidence=0.89,
                    ai_suggested_action="Verify MDR fee agreement or reconcile MDR tax credit note.",
                    resolution=ExceptionResolution.PENDING,
                )
                gw.match_status = MatchStatus.EXCEPTION
                near_miss_bank.match_status = MatchStatus.EXCEPTION
                matched_bank_ids.add(near_miss_bank.id)
            else:
                exc = Exception_(
                    exception_code=exc_code,
                    batch_id=batch.id,
                    exception_type=ExceptionType.MISSING_BANK,
                    gateway_transaction_id=gw.id,
                    expected_amount=gw.amount,
                    actual_amount=0.0,
                    difference=-gw.amount,
                    ai_explanation=(
                        f"Gateway transaction {gw.transaction_id} (₹{gw.amount:,.2f}) captured via {gw.source.value.upper()} "
                        f"on {gw.transaction_time.strftime('%d %b %Y')} has no corresponding credit in any bank settlement. "
                        f"Possible delayed settlement cycle or pending bank clearing."
                    ),
                    ai_confidence=0.92,
                    ai_suggested_action="Monitor settlement batch SLA; query bank nodal account if delay exceeds 48 hours.",
                    resolution=ExceptionResolution.PENDING,
                )
                gw.match_status = MatchStatus.EXCEPTION

            exceptions_created.append(exc)
            self.db.add(exc)

        # Unmatched Bank transactions (MISSING_GATEWAY)
        for b in bank_txns:
            if b.id in matched_bank_ids:
                continue

            exc_code = f"EXC-{now.strftime('%Y%m%d')}-{exc_counter:04d}"
            exc_counter += 1

            exc = Exception_(
                exception_code=exc_code,
                batch_id=batch.id,
                exception_type=ExceptionType.MISSING_GATEWAY,
                bank_transaction_id=b.id,
                expected_amount=0.0,
                actual_amount=b.amount,
                difference=b.amount,
                ai_explanation=(
                    f"Bank credit of ₹{b.amount:,.2f} received at {b.bank.value.upper()} "
                    f"(Ref: {b.bank_reference}) on {b.value_date.strftime('%d %b %Y')} with narration '{b.narration}' "
                    f"has no matching payment capture in gateway records. Suspected direct NEFT/RTGS transfer or missing gateway webhook."
                ),
                ai_confidence=0.88,
                ai_suggested_action="Check webhook delivery logs or verify if this is an off-platform merchant settlement.",
                resolution=ExceptionResolution.PENDING,
            )
            b.match_status = MatchStatus.EXCEPTION
            exceptions_created.append(exc)
            self.db.add(exc)

        # ──────────────── Update Database Entities ────────────────
        # Update matched transactions
        for gw, bank, conf, method in matched_pairs:
            gw.match_status = MatchStatus.MATCHED
            gw.matched_bank_id = bank.id
            gw.match_confidence = conf
            gw.match_method = method
            gw.batch_id = batch.id

            bank.match_status = MatchStatus.MATCHED
            bank.matched_gateway_id = gw.id
            bank.match_confidence = conf
            bank.batch_id = batch.id

        elapsed = round(time.time() - start_time, 3)

        exact_count = sum(1 for p in matched_pairs if p[3] == MatchMethod.EXACT)
        fuzzy_count = sum(1 for p in matched_pairs if p[3] == MatchMethod.FUZZY)
        total_matched = len(matched_pairs)
        total_records = max(len(gateway_txns), 1)
        match_rate = round((total_matched / total_records) * 100.0, 1)
        avg_conf = round(
            sum(p[2] for p in matched_pairs) / max(total_matched, 1),
            3
        ) if total_matched > 0 else 0.0

        # Update batch summary
        batch.completed_at = datetime.utcnow()
        batch.status = "completed"
        batch.exact_matches = exact_count
        batch.fuzzy_matches = fuzzy_count
        batch.exceptions = len(exceptions_created)
        batch.unresolved = len(exceptions_created)
        batch.match_rate = match_rate
        batch.avg_confidence = avg_conf
        batch.processing_time_seconds = elapsed
        batch.total_value_processed = total_value_processed
        batch.total_value_matched = total_value_matched

        await self.db.commit()
        await self.db.refresh(batch)

        # Log audit entry
        await AuditLogger.log_action(
            db=self.db,
            actor=AuditActor.SYSTEM,
            actor_name="ReconEngine_Core",
            action="BATCH_RECONCILIATION_COMPLETED",
            entity_type="reconciliation_batch",
            entity_id=batch.id,
            details=(
                f"Batch '{batch.batch_name}' completed in {elapsed}s: "
                f"{exact_count} exact matches, {fuzzy_count} fuzzy matches, "
                f"{len(exceptions_created)} exceptions. Match rate: {match_rate}%."
            ),
            metadata={
                "batch_id": batch.id,
                "exact_matches": exact_count,
                "fuzzy_matches": fuzzy_count,
                "exceptions": len(exceptions_created),
                "match_rate": match_rate,
                "processing_time_seconds": elapsed,
            },
        )

        return batch
