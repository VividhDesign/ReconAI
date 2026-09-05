"""
ReconAI — Audit Logger Service
Immutable audit logging with SHA-256 hash chaining for fintech compliance (SOC-2, RBI).
"""
import hashlib
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AuditLog, AuditActor


def compute_log_hash(
    prev_hash: str,
    timestamp: datetime,
    actor: str,
    action: str,
    entity_type: Optional[str],
    entity_id: Optional[str],
    details: Optional[str],
) -> str:
    """Compute SHA-256 hash of log entry chained to previous log entry hash."""
    payload = (
        f"{prev_hash}|{timestamp.isoformat()}|{actor}|{action}|"
        f"{entity_type or ''}|{entity_id or ''}|{details or ''}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AuditLogger:
    """Service to record and verify tamper-evident audit logs."""

    @staticmethod
    async def log_action(
        db: AsyncSession,
        actor: AuditActor,
        action: str,
        actor_name: Optional[str] = None,
        details: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        status: str = "success",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditLog:
        """Create a new audit log record."""
        # Get latest record to chain hash
        stmt = select(AuditLog).order_by(desc(AuditLog.timestamp)).limit(1)
        result = await db.execute(stmt)
        latest_log = result.scalars().first()

        prev_hash = "GENESIS_ROOT_HASH_RECON_AI"
        if latest_log and latest_log.metadata_ and "hash" in latest_log.metadata_:
            prev_hash = latest_log.metadata_["hash"]

        now = datetime.utcnow()
        actor_val = actor.value if hasattr(actor, "value") else str(actor)
        current_hash = compute_log_hash(
            prev_hash=prev_hash,
            timestamp=now,
            actor=actor_val,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
        )

        meta_dict = metadata or {}
        meta_dict["hash"] = current_hash
        meta_dict["prev_hash"] = prev_hash

        log_entry = AuditLog(
            timestamp=now,
            actor=actor,
            actor_name=actor_name or actor_val,
            action=action,
            details=details,
            entity_type=entity_type,
            entity_id=entity_id,
            status=status,
            metadata_=meta_dict,
        )

        db.add(log_entry)
        await db.commit()
        await db.refresh(log_entry)
        return log_entry

    @staticmethod
    async def get_logs(
        db: AsyncSession,
        actor: Optional[str] = None,
        entity_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[AuditLog]:
        """Fetch audit logs with optional filters."""
        stmt = select(AuditLog).order_by(desc(AuditLog.timestamp))

        if actor:
            stmt = stmt.where(AuditLog.actor == actor)
        if entity_type:
            stmt = stmt.where(AuditLog.entity_type == entity_type)

        stmt = stmt.offset(offset).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def verify_chain_integrity(db: AsyncSession) -> Dict[str, Any]:
        """Verify that all cryptographic links in the audit log chain are intact."""
        stmt = select(AuditLog).order_by(AuditLog.timestamp.asc())
        result = await db.execute(stmt)
        logs = list(result.scalars().all())

        if not logs:
            return {"verified": True, "total_logs": 0, "message": "No logs recorded yet."}

        prev_hash = "GENESIS_ROOT_HASH_RECON_AI"
        corrupted_index = None

        for idx, log in enumerate(logs):
            meta = log.metadata_ or {}
            stored_hash = meta.get("hash")
            stored_prev = meta.get("prev_hash")

            if stored_prev != prev_hash:
                corrupted_index = idx
                break

            actor_val = log.actor.value if hasattr(log.actor, "value") else str(log.actor)
            expected_hash = compute_log_hash(
                prev_hash=prev_hash,
                timestamp=log.timestamp,
                actor=actor_val,
                action=log.action,
                entity_type=log.entity_type,
                entity_id=log.entity_id,
                details=log.details,
            )

            if stored_hash != expected_hash:
                corrupted_index = idx
                break

            prev_hash = stored_hash

        if corrupted_index is not None:
            return {
                "verified": False,
                "total_logs": len(logs),
                "corrupted_at_index": corrupted_index,
                "corrupted_log_id": logs[corrupted_index].id,
                "message": f"Audit trail tampering detected at record {logs[corrupted_index].id}!",
            }

        return {
            "verified": True,
            "total_logs": len(logs),
            "root_hash": prev_hash,
            "message": "All audit logs cryptographically verified. Zero tampering detected.",
        }
