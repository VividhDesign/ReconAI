"""
ReconAI — SQLAlchemy Models
"""
import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Column, String, Float, DateTime, Text, Integer,
    Enum, Boolean, ForeignKey, Index, JSON
)
from sqlalchemy.orm import relationship
from backend.database import Base


# ──────────────────── Enums ────────────────────

class TransactionSource(str, PyEnum):
    RAZORPAY = "razorpay"
    STRIPE = "stripe"
    PAYTM = "paytm"
    PHONEPE = "phonepe"
    OTHER = "other"


class BankName(str, PyEnum):
    HDFC = "hdfc"
    ICICI = "icici"
    SBI = "sbi"
    AXIS = "axis"
    KOTAK = "kotak"
    OTHER = "other"


class MatchStatus(str, PyEnum):
    PENDING = "pending"
    MATCHED = "matched"
    EXCEPTION = "exception"
    UNRESOLVED = "unresolved"


class ExceptionType(str, PyEnum):
    AMOUNT_MISMATCH = "amount_mismatch"
    MISSING_BANK = "missing_bank"
    MISSING_GATEWAY = "missing_gateway"
    DUPLICATE = "duplicate"
    DATE_MISMATCH = "date_mismatch"
    REFERENCE_MISMATCH = "reference_mismatch"


class ExceptionResolution(str, PyEnum):
    PENDING = "pending"
    AUTO_RESOLVED = "auto_resolved"
    MANUALLY_RESOLVED = "manually_resolved"
    ESCALATED = "escalated"
    REJECTED = "rejected"


class AuditActor(str, PyEnum):
    AI_AGENT = "ai_agent"
    SYSTEM = "system"
    USER = "user"


class MatchMethod(str, PyEnum):
    EXACT = "exact"
    FUZZY = "fuzzy"
    AI_ASSISTED = "ai_assisted"
    MANUAL = "manual"


# ──────────────────── Models ────────────────────

def generate_uuid():
    return str(uuid.uuid4())


class GatewayTransaction(Base):
    """Payment gateway transaction record."""
    __tablename__ = "gateway_transactions"

    id = Column(String, primary_key=True, default=generate_uuid)
    transaction_id = Column(String, unique=True, nullable=False, index=True)
    source = Column(Enum(TransactionSource), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="INR")
    payment_method = Column(String)  # UPI, Card, NetBanking, Wallet
    payment_detail = Column(String)  # e.g., user@oksbi, **** 4521
    merchant_id = Column(String)
    merchant_name = Column(String)
    customer_email = Column(String)
    reference_id = Column(String, index=True)
    order_id = Column(String)
    status = Column(String)  # captured, refunded, failed
    gateway_fee = Column(Float, default=0.0)
    tax_on_fee = Column(Float, default=0.0)
    settlement_amount = Column(Float)
    transaction_time = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Reconciliation status
    match_status = Column(Enum(MatchStatus), default=MatchStatus.PENDING)
    matched_bank_id = Column(String, ForeignKey("bank_transactions.id"), nullable=True)
    match_confidence = Column(Float, default=0.0)
    match_method = Column(Enum(MatchMethod), nullable=True)
    batch_id = Column(String, ForeignKey("reconciliation_batches.id"), nullable=True)

    # Embedding for fuzzy match
    embedding_text = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_gateway_amount_time", "amount", "transaction_time"),
        Index("idx_gateway_status", "match_status"),
    )


class BankTransaction(Base):
    """Bank settlement / statement record."""
    __tablename__ = "bank_transactions"

    id = Column(String, primary_key=True, default=generate_uuid)
    bank_reference = Column(String, unique=True, nullable=False, index=True)
    bank = Column(Enum(BankName), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="INR")
    transaction_type = Column(String)  # CR (Credit), DR (Debit)
    narration = Column(Text)
    value_date = Column(DateTime, nullable=False)
    posting_date = Column(DateTime)
    closing_balance = Column(Float, nullable=True)
    merchant_reference = Column(String, index=True)
    utr_number = Column(String, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Reconciliation status
    match_status = Column(Enum(MatchStatus), default=MatchStatus.PENDING)
    matched_gateway_id = Column(String, nullable=True)
    match_confidence = Column(Float, default=0.0)
    batch_id = Column(String, ForeignKey("reconciliation_batches.id"), nullable=True)

    # Embedding
    embedding_text = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_bank_amount_date", "amount", "value_date"),
        Index("idx_bank_status", "match_status"),
    )


class ReconciliationBatch(Base):
    """A batch reconciliation run."""
    __tablename__ = "reconciliation_batches"

    id = Column(String, primary_key=True, default=generate_uuid)
    batch_name = Column(String)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String, default="running")  # running, completed, failed

    # Counts
    total_gateway_records = Column(Integer, default=0)
    total_bank_records = Column(Integer, default=0)
    exact_matches = Column(Integer, default=0)
    fuzzy_matches = Column(Integer, default=0)
    exceptions = Column(Integer, default=0)
    unresolved = Column(Integer, default=0)

    # Metrics
    match_rate = Column(Float, default=0.0)
    avg_confidence = Column(Float, default=0.0)
    processing_time_seconds = Column(Float, default=0.0)
    total_value_processed = Column(Float, default=0.0)
    total_value_matched = Column(Float, default=0.0)


class Exception_(Base):
    """Reconciliation exception record."""
    __tablename__ = "exceptions"

    id = Column(String, primary_key=True, default=generate_uuid)
    exception_code = Column(String, unique=True, nullable=False)
    batch_id = Column(String, ForeignKey("reconciliation_batches.id"))
    exception_type = Column(Enum(ExceptionType), nullable=False)

    # Transaction references
    gateway_transaction_id = Column(String, ForeignKey("gateway_transactions.id"), nullable=True)
    bank_transaction_id = Column(String, ForeignKey("bank_transactions.id"), nullable=True)

    # Amounts
    expected_amount = Column(Float)
    actual_amount = Column(Float, nullable=True)
    difference = Column(Float, default=0.0)

    # AI Analysis
    ai_explanation = Column(Text)
    ai_confidence = Column(Float, default=0.0)
    ai_suggested_action = Column(String)

    # Resolution
    resolution = Column(Enum(ExceptionResolution), default=ExceptionResolution.PENDING)
    resolved_by = Column(String, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    resolution_note = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_exception_type", "exception_type"),
        Index("idx_exception_resolution", "resolution"),
    )


class AuditLog(Base):
    """Immutable audit trail."""
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=generate_uuid)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    actor = Column(Enum(AuditActor), nullable=False)
    actor_name = Column(String)
    action = Column(String, nullable=False)
    details = Column(Text)
    entity_type = Column(String)  # e.g., "transaction", "exception", "batch"
    entity_id = Column(String)
    status = Column(String, default="success")
    metadata_ = Column("metadata", JSON, nullable=True)

    __table_args__ = (
        Index("idx_audit_timestamp", "timestamp"),
        Index("idx_audit_actor", "actor"),
    )


class AgentConversation(Base):
    """AI Agent chat history."""
    __tablename__ = "agent_conversations"

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, index=True)
    role = Column(String, nullable=False)  # user, assistant, system, tool
    content = Column(Text, nullable=False)
    tool_calls = Column(JSON, nullable=True)
    tool_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
