"""
ReconAI — FastAPI Application Server
Enterprise-grade AI Reconciliation Engine API for the Razorpay AI Buildathon 2026.
"""
import os
from datetime import datetime
from typing import List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from backend.config import settings
from backend.database import get_db, init_db
from backend.models import (
    GatewayTransaction, BankTransaction, ReconciliationBatch,
    Exception_, AuditLog, AgentConversation,
    MatchStatus, ExceptionResolution, ExceptionType, AuditActor
)
from backend.schemas import (
    GatewayTransactionResponse, BankTransactionResponse,
    ReconciliationRequest, ReconciliationResult,
    ExceptionResponse, ExceptionResolveRequest,
    AuditLogResponse, AgentMessage, AgentResponse,
    DashboardStats, FileUploadResponse
)
from backend.services.reconciliation_engine import ReconciliationEngine
from backend.services.exception_analyzer import ExceptionAnalyzer
from backend.services.ai_agent import AIAgentService
from backend.services.audit_logger import AuditLogger
from backend.parsers.csv_parser import parse_gateway_csv
from backend.parsers.mt940_parser import parse_mt940
from backend.parsers.bank_csv_parser import parse_bank_csv
from backend.seed_data import seed_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    # Initialize DB schema
    await init_db()
    # Seed initial test records if empty
    try:
        await seed_database()
    except Exception as e:
        print(f"Notice on auto-seed: {e}")
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-Powered Transaction Reconciliation Engine (Track 4: AI Finance Controller)",
    lifespan=lifespan,
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────── Health & Stats ────────────────

@app.get("/api/health")
async def health_check():
    """System health check endpoint."""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "openai_connected": bool(settings.OPENAI_API_KEY),
        "database": "sqlite_async" if "sqlite" in settings.DATABASE_URL else "postgresql_async",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/api/stats", response_model=DashboardStats)
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    """Fetch live aggregate statistics for the dashboard."""
    total_gw = await db.scalar(select(func.count(GatewayTransaction.id))) or 0
    matched_gw = await db.scalar(
        select(func.count(GatewayTransaction.id)).where(GatewayTransaction.match_status == MatchStatus.MATCHED)
    ) or 0
    excs = await db.scalar(select(func.count(Exception_.id))) or 0
    unres = await db.scalar(
        select(func.count(Exception_.id)).where(Exception_.resolution == ExceptionResolution.PENDING)
    ) or 0

    total_val_proc = await db.scalar(select(func.sum(GatewayTransaction.amount))) or 0.0
    total_val_matched = await db.scalar(
        select(func.sum(GatewayTransaction.amount)).where(GatewayTransaction.match_status == MatchStatus.MATCHED)
    ) or 0.0

    rate = round((matched_gw / max(total_gw, 1)) * 100.0, 1) if total_gw > 0 else 0.0

    return DashboardStats(
        total_processed=total_gw,
        auto_matched=matched_gw,
        exceptions=excs,
        unresolved=unres,
        match_rate=rate,
        total_value_processed=round(float(total_val_proc), 2),
        total_value_matched=round(float(total_val_matched), 2),
    )


@app.get("/api/analytics")
async def get_analytics(db: AsyncSession = Depends(get_db)):
    """Fetch breakdown analytics for charts."""
    # Match Breakdown
    exact_count = await db.scalar(
        select(func.count(GatewayTransaction.id)).where(GatewayTransaction.match_method == "exact")
    ) or 0
    fuzzy_count = await db.scalar(
        select(func.count(GatewayTransaction.id)).where(GatewayTransaction.match_method == "fuzzy")
    ) or 0
    exception_count = await db.scalar(select(func.count(Exception_.id))) or 0

    # Source breakdown
    sources_data = {}
    for src in ["razorpay", "stripe", "paytm"]:
        c = await db.scalar(
            select(func.count(GatewayTransaction.id)).where(GatewayTransaction.source == src)
        ) or 0
        sources_data[src] = c

    # Bank breakdown
    banks_data = {}
    for b in ["hdfc", "icici", "sbi", "axis"]:
        c = await db.scalar(
            select(func.count(BankTransaction.id)).where(BankTransaction.bank == b)
        ) or 0
        banks_data[b] = c

    return {
        "match_distribution": {
            "exact_matches": exact_count,
            "fuzzy_matches": fuzzy_count,
            "exceptions": exception_count,
        },
        "gateway_distribution": sources_data,
        "bank_distribution": banks_data,
    }


# ──────────────── Transactions ────────────────

@app.get("/api/transactions/gateway", response_model=List[GatewayTransactionResponse])
async def list_gateway_transactions(
    source: Optional[str] = None,
    match_status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Query gateway transactions with filters."""
    stmt = select(GatewayTransaction).order_by(desc(GatewayTransaction.transaction_time))
    if source:
        stmt = stmt.where(GatewayTransaction.source == source)
    if match_status:
        stmt = stmt.where(GatewayTransaction.match_status == match_status)

    stmt = stmt.offset(offset).limit(limit)
    res = await db.execute(stmt)
    return res.scalars().all()


@app.get("/api/transactions/bank", response_model=List[BankTransactionResponse])
async def list_bank_transactions(
    bank: Optional[str] = None,
    match_status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Query bank statement records with filters."""
    stmt = select(BankTransaction).order_by(desc(BankTransaction.value_date))
    if bank:
        stmt = stmt.where(BankTransaction.bank == bank)
    if match_status:
        stmt = stmt.where(BankTransaction.match_status == match_status)

    stmt = stmt.offset(offset).limit(limit)
    res = await db.execute(stmt)
    return res.scalars().all()


# ──────────────── File Ingestion ────────────────

@app.post("/api/upload/gateway", response_model=FileUploadResponse)
async def upload_gateway_file(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload and parse Gateway CSV (Razorpay, Stripe, PayTM)."""
    contents = await file.read()
    records, errors = parse_gateway_csv(contents, file.filename or "export.csv")

    if not records and errors:
        raise HTTPException(status_code=400, detail={"message": "Failed to parse CSV", "errors": errors})

    added_count = 0
    for r in records:
        # Check duplicate
        exists = await db.scalar(
            select(GatewayTransaction.id).where(GatewayTransaction.transaction_id == r["transaction_id"])
        )
        if not exists:
            gw = GatewayTransaction(**r)
            db.add(gw)
            added_count += 1

    await db.commit()

    await AuditLogger.log_action(
        db=db,
        actor=AuditActor.USER,
        action="FILE_UPLOAD_GATEWAY",
        details=f"Uploaded {file.filename}: {added_count} new records parsed.",
        entity_type="file",
        entity_id=file.filename,
    )

    return FileUploadResponse(
        filename=file.filename,
        records_parsed=added_count,
        source_type="gateway_csv",
        status="success",
        errors=errors[:5],
    )


@app.post("/api/upload/bank", response_model=FileUploadResponse)
async def upload_bank_file(
    file: UploadFile = File(...),
    bank: str = Query("hdfc", description="Bank identifier (hdfc, icici, sbi, axis)"),
    db: AsyncSession = Depends(get_db),
):
    """Upload and parse Bank Statement (SWIFT MT940 or CSV)."""
    contents = await file.read()
    filename = (file.filename or "").lower()

    if filename.endswith(".sta") or filename.endswith(".940") or b":20:" in contents:
        records, errors = parse_mt940(contents, filename)
    else:
        records, errors = parse_bank_csv(contents, bank)

    if not records and errors:
        raise HTTPException(status_code=400, detail={"message": "Failed to parse bank file", "errors": errors})

    added_count = 0
    for r in records:
        exists = await db.scalar(
            select(BankTransaction.id).where(BankTransaction.bank_reference == r["bank_reference"])
        )
        if not exists:
            bt = BankTransaction(**r)
            db.add(bt)
            added_count += 1

    await db.commit()

    await AuditLogger.log_action(
        db=db,
        actor=AuditActor.USER,
        action="FILE_UPLOAD_BANK",
        details=f"Uploaded {file.filename}: {added_count} bank settlement records parsed.",
        entity_type="file",
        entity_id=file.filename,
    )

    return FileUploadResponse(
        filename=file.filename,
        records_parsed=added_count,
        source_type="bank_statement",
        status="success",
        errors=errors[:5],
    )


# ──────────────── Reconciliation Runs ────────────────

@app.post("/api/reconciliation/run", response_model=ReconciliationResult)
async def run_reconciliation(
    req: Optional[ReconciliationRequest] = None,
    db: AsyncSession = Depends(get_db),
):
    """Trigger automated multi-pass transaction reconciliation."""
    engine = ReconciliationEngine(db)
    batch = await engine.run_reconciliation(
        batch_name=req.batch_name if req else None,
        source_filter=req.source_filter if req else None,
        bank_filter=req.bank_filter if req else None,
        date_from=req.date_from if req else None,
        date_to=req.date_to if req else None,
    )

    return ReconciliationResult(
        batch_id=batch.id,
        status=batch.status,
        total_gateway_records=batch.total_gateway_records,
        total_bank_records=batch.total_bank_records,
        exact_matches=batch.exact_matches,
        fuzzy_matches=batch.fuzzy_matches,
        exceptions=batch.exceptions,
        unresolved=batch.unresolved,
        match_rate=batch.match_rate,
        avg_confidence=batch.avg_confidence,
        processing_time_seconds=batch.processing_time_seconds,
        total_value_processed=batch.total_value_processed,
        total_value_matched=batch.total_value_matched,
    )


@app.get("/api/reconciliation/batches")
async def list_batches(
    limit: int = 10,
    db: AsyncSession = Depends(get_db)
):
    """List recent reconciliation batches."""
    stmt = select(ReconciliationBatch).order_by(desc(ReconciliationBatch.started_at)).limit(limit)
    res = await db.execute(stmt)
    return res.scalars().all()


# ──────────────── Exceptions ────────────────

@app.get("/api/exceptions", response_model=List[ExceptionResponse])
async def list_exceptions(
    resolution: Optional[str] = None,
    exception_type: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """List flagged reconciliation exceptions."""
    stmt = select(Exception_).order_by(desc(Exception_.created_at))
    if resolution:
        stmt = stmt.where(Exception_.resolution == resolution)
    if exception_type:
        stmt = stmt.where(Exception_.exception_type == exception_type)

    stmt = stmt.limit(limit)
    res = await db.execute(stmt)
    return res.scalars().all()


@app.get("/api/exceptions/{exception_id}", response_model=ExceptionResponse)
async def get_exception_details(
    exception_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get single exception details."""
    stmt = select(Exception_).where(
        (Exception_.id == exception_id) | (Exception_.exception_code == exception_id)
    )
    res = await db.execute(stmt)
    exc = res.scalars().first()
    if not exc:
        raise HTTPException(status_code=404, detail="Exception not found")
    return exc


@app.post("/api/exceptions/{exception_id}/analyze")
async def analyze_exception(
    exception_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Run AI root-cause analysis on an exception."""
    analyzer = ExceptionAnalyzer(db)
    # Find by ID or code
    stmt = select(Exception_.id).where(
        (Exception_.id == exception_id) | (Exception_.exception_code == exception_id)
    )
    real_id = await db.scalar(stmt)
    if not real_id:
        raise HTTPException(status_code=404, detail="Exception not found")

    result = await analyzer.analyze_exception(real_id)
    return result


@app.post("/api/exceptions/{exception_id}/resolve", response_model=ExceptionResponse)
async def resolve_exception(
    exception_id: str,
    req: ExceptionResolveRequest,
    db: AsyncSession = Depends(get_db),
):
    """Resolve an exception."""
    analyzer = ExceptionAnalyzer(db)
    stmt = select(Exception_.id).where(
        (Exception_.id == exception_id) | (Exception_.exception_code == exception_id)
    )
    real_id = await db.scalar(stmt)
    if not real_id:
        raise HTTPException(status_code=404, detail="Exception not found")

    try:
        res_enum = ExceptionResolution(req.resolution)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid resolution: {req.resolution}")

    try:
        resolved = await analyzer.resolve_exception(
            exception_id=real_id,
            resolution=res_enum,
            resolved_by=req.resolved_by,
            resolution_note=req.resolution_note,
        )
        return resolved
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


# ──────────────── AI Finance Controller Agent ────────────────

@app.post("/api/agent/chat", response_model=AgentResponse)
async def chat_with_agent(
    req: AgentMessage,
    db: AsyncSession = Depends(get_db),
):
    """Conversational AI agent endpoint."""
    agent = AIAgentService(db)
    response = await agent.chat(message=req.message, session_id=req.session_id)
    return AgentResponse(
        message=response["message"],
        session_id=response["session_id"],
        tool_calls=response.get("tool_calls"),
    )


# ──────────────── Audit Logs ────────────────

@app.get("/api/audit-logs", response_model=List[AuditLogResponse])
async def get_audit_logs(
    actor: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Query immutable audit logs."""
    logs = await AuditLogger.get_logs(db=db, actor=actor, limit=limit, offset=offset)
    return logs


@app.get("/api/audit-logs/verify")
async def verify_audit_logs(db: AsyncSession = Depends(get_db)):
    """Cryptographically verify SHA-256 hash chain of the entire audit trail."""
    result = await AuditLogger.verify_chain_integrity(db=db)
    return result


# ──────────────── Serve Frontend ────────────────

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

@app.get("/")
async def serve_index():
    index_path = os.path.join(WORKSPACE_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "ReconAI API running. Frontend index.html not found."}

if os.path.exists(os.path.join(WORKSPACE_DIR, "styles.css")):
    app.mount("/static", StaticFiles(directory=WORKSPACE_DIR), name="static")
