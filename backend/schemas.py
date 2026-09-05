"""
ReconAI — Pydantic Schemas for API Request/Response
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# ──────────────── Gateway Transaction ────────────────

class GatewayTransactionCreate(BaseModel):
    transaction_id: str
    source: str
    amount: float
    currency: str = "INR"
    payment_method: Optional[str] = None
    payment_detail: Optional[str] = None
    merchant_id: Optional[str] = None
    merchant_name: Optional[str] = None
    reference_id: Optional[str] = None
    order_id: Optional[str] = None
    status: str = "captured"
    gateway_fee: float = 0.0
    tax_on_fee: float = 0.0
    settlement_amount: Optional[float] = None
    transaction_time: datetime


class GatewayTransactionResponse(BaseModel):
    id: str
    transaction_id: str
    source: str
    amount: float
    currency: str
    payment_method: Optional[str]
    payment_detail: Optional[str]
    reference_id: Optional[str]
    status: str
    match_status: str
    match_confidence: float
    match_method: Optional[str]
    transaction_time: datetime

    class Config:
        from_attributes = True


# ──────────────── Bank Transaction ────────────────

class BankTransactionCreate(BaseModel):
    bank_reference: str
    bank: str
    amount: float
    currency: str = "INR"
    transaction_type: str = "CR"
    narration: Optional[str] = None
    value_date: datetime
    posting_date: Optional[datetime] = None
    merchant_reference: Optional[str] = None
    utr_number: Optional[str] = None


class BankTransactionResponse(BaseModel):
    id: str
    bank_reference: str
    bank: str
    amount: float
    transaction_type: str
    narration: Optional[str]
    value_date: datetime
    match_status: str
    match_confidence: float

    class Config:
        from_attributes = True


# ──────────────── Reconciliation ────────────────

class ReconciliationRequest(BaseModel):
    """Request to start a reconciliation batch."""
    batch_name: Optional[str] = None
    source_filter: Optional[str] = None
    bank_filter: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


class ReconciliationResult(BaseModel):
    """Result of a reconciliation run."""
    batch_id: str
    status: str
    total_gateway_records: int
    total_bank_records: int
    exact_matches: int
    fuzzy_matches: int
    exceptions: int
    unresolved: int
    match_rate: float
    avg_confidence: float
    processing_time_seconds: float
    total_value_processed: float
    total_value_matched: float


class MatchPair(BaseModel):
    """A matched pair of gateway and bank transactions."""
    gateway_transaction: GatewayTransactionResponse
    bank_transaction: BankTransactionResponse
    confidence: float
    method: str


# ──────────────── Exceptions ────────────────

class ExceptionResponse(BaseModel):
    id: str
    exception_code: str
    exception_type: str
    gateway_transaction_id: Optional[str]
    bank_transaction_id: Optional[str]
    expected_amount: Optional[float]
    actual_amount: Optional[float]
    difference: float
    ai_explanation: Optional[str]
    ai_confidence: float
    ai_suggested_action: Optional[str]
    resolution: str
    created_at: datetime

    class Config:
        from_attributes = True


class ExceptionResolveRequest(BaseModel):
    """Request to resolve an exception."""
    resolution: str  # auto_resolved, manually_resolved, rejected
    resolution_note: Optional[str] = None
    resolved_by: str = "user"


# ──────────────── Audit Log ────────────────

class AuditLogResponse(BaseModel):
    id: str
    timestamp: datetime
    actor: str
    actor_name: Optional[str]
    action: str
    details: Optional[str]
    entity_type: Optional[str]
    entity_id: Optional[str]
    status: str

    class Config:
        from_attributes = True


# ──────────────── AI Agent ────────────────

class AgentMessage(BaseModel):
    """Chat message to/from AI agent."""
    message: str
    session_id: Optional[str] = None


class AgentResponse(BaseModel):
    """Response from the AI agent."""
    message: str
    session_id: str
    tool_calls: Optional[List[dict]] = None


# ──────────────── Dashboard Stats ────────────────

class DashboardStats(BaseModel):
    total_processed: int
    auto_matched: int
    exceptions: int
    unresolved: int
    match_rate: float
    total_value_processed: float
    total_value_matched: float


class TrendDataPoint(BaseModel):
    date: str
    processed: int
    matched: int
    exceptions: int


# ──────────────── File Upload ────────────────

class FileUploadResponse(BaseModel):
    filename: str
    records_parsed: int
    source_type: str
    status: str
    errors: List[str] = []
