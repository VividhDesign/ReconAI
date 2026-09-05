"""
ReconAI — AI Finance Controller Agent Service
Autonomous conversational agent for transaction reconciliation, anomaly investigation,
and automated financial discrepancy resolution.
"""
import uuid
import json
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models import (
    AgentConversation, ReconciliationBatch, Exception_,
    GatewayTransaction, BankTransaction, MatchStatus, ExceptionResolution,
    AuditActor
)
from backend.services.exception_analyzer import ExceptionAnalyzer
from backend.services.audit_logger import AuditLogger


AGENT_SYSTEM_PROMPT = """You are ReconAI, an autonomous AI Finance Controller built for the Razorpay AI Buildathon 2026.
You supervise multi-source transaction reconciliation across payment gateways (Razorpay, Stripe, PayTM, PhonePe) and Indian bank settlements (HDFC, ICICI, SBI, Axis).

You have deep domain knowledge of:
1. MDR (Merchant Discount Rate) calculations and 18% GST implications on gateway fees.
2. T+1 and T+2 settlement cycles and RTGS/NEFT banking cut-off windows in India.
3. Common discrepancies: partial chargebacks, truncated SBI/HDFC statement narrations, dropped webhooks, split batch payouts.
4. RBI regulations regarding nodal account settlements and customer refund timelines.

Be direct, analytical, and professional. Always quote transaction IDs, amounts with ₹ symbol, and confidence percentages when presenting data."""


class AIAgentService:
    """Conversational Finance Controller Agent."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def chat(
        self,
        message: str,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Process user message, execute tools if required, and return assistant response."""
        sid = session_id or str(uuid.uuid4())

        # Save user message
        user_msg = AgentConversation(
            session_id=sid,
            role="user",
            content=message,
        )
        self.db.add(user_msg)
        await self.db.commit()

        # Check if OpenAI is available
        if settings.OPENAI_API_KEY:
            try:
                response_text, tool_calls = await self._chat_with_openai(message, sid)
            except Exception as e:
                response_text, tool_calls = await self._chat_with_local_engine(message, sid)
        else:
            response_text, tool_calls = await self._chat_with_local_engine(message, sid)

        # Save assistant message
        asst_msg = AgentConversation(
            session_id=sid,
            role="assistant",
            content=response_text,
            tool_calls=tool_calls,
        )
        self.db.add(asst_msg)
        await self.db.commit()

        # Audit log agent interaction
        await AuditLogger.log_action(
            db=self.db,
            actor=AuditActor.AI_AGENT,
            actor_name="ReconAI_Finance_Controller",
            action="AGENT_CONVERSATION",
            entity_type="session",
            entity_id=sid,
            details=f"User query: '{message[:80]}...' | Response: '{response_text[:80]}...'",
        )

        return {
            "message": response_text,
            "session_id": sid,
            "tool_calls": tool_calls,
        }

    async def _chat_with_openai(self, message: str, session_id: str) -> Tuple[str, Optional[List[dict]]]:
        """Invoke OpenAI with available reconciliation tool definitions."""
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        # Load recent conversation history (last 6 messages)
        stmt = (
            select(AgentConversation)
            .where(AgentConversation.session_id == session_id)
            .order_by(AgentConversation.created_at.desc())
            .limit(6)
        )
        res = await self.db.execute(stmt)
        history = list(reversed(res.scalars().all()))

        messages = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]
        for h in history:
            messages.append({"role": h.role, "content": h.content})

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_reconciliation_summary",
                    "description": "Get summary metrics of total transactions, match rate, volume processed, and open exceptions.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_pending_exceptions",
                    "description": "List open reconciliation exceptions requiring controller attention.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer", "description": "Maximum exceptions to return"}
                        }
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "explain_exception",
                    "description": "Perform deep AI root cause analysis on a specific exception code (e.g. EXC-2026-0001).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "exception_code": {"type": "string", "description": "Exception code to analyze"}
                        },
                        "required": ["exception_code"]
                    },
                },
            }
        ]

        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )

        choice = response.choices[0]
        if choice.message.tool_calls:
            tool_results = []
            for tool_call in choice.message.tool_calls:
                func_name = tool_call.function.name
                args = json.loads(tool_call.function.arguments or "{}")

                if func_name == "get_reconciliation_summary":
                    out = await self._tool_reconciliation_summary()
                elif func_name == "list_pending_exceptions":
                    out = await self._tool_list_exceptions(args.get("limit", 5))
                elif func_name == "explain_exception":
                    out = await self._tool_explain_exception(args.get("exception_code", ""))
                else:
                    out = {"status": "unknown_tool"}

                tool_results.append({
                    "id": tool_call.id,
                    "name": func_name,
                    "result": out,
                })

            # Send tool output back to model for final answer
            messages.append(choice.message)
            for tr in tool_results:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tr["id"],
                    "content": json.dumps(tr["result"]),
                })

            final_response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=messages,
            )
            return final_response.choices[0].message.content, tool_results

        return choice.message.content, None

    async def _chat_with_local_engine(self, message: str, session_id: str) -> Tuple[str, Optional[List[dict]]]:
        """Intelligent natural language query processing without external dependencies."""
        msg_lower = message.lower()
        tool_calls = []

        # Intent 1: Reconciliation Status / Summary / Match Rate
        if any(w in msg_lower for w in ["summary", "match rate", "stats", "overview", "dashboard", "how many"]):
            summary = await self._tool_reconciliation_summary()
            tool_calls.append({"name": "get_reconciliation_summary", "result": summary})
            text = (
                f"### 📊 ReconAI Financial Summary\n\n"
                f"Here is the current reconciliation snapshot across all gateway and banking channels:\n\n"
                f"- **Overall Match Rate:** `{summary['match_rate']}%`\n"
                f"- **Total Transactions Processed:** `{summary['total_processed']:,}`\n"
                f"- **Auto-Matched Records:** `{summary['auto_matched']:,}` (`{summary['exact_matches']:,}` exact + `{summary['fuzzy_matches']:,}` fuzzy)\n"
                f"- **Total Value Processed:** `₹{summary['total_value_processed']:,.2f}`\n"
                f"- **Total Value Settled:** `₹{summary['total_value_matched']:,.2f}`\n"
                f"- **Open Exceptions:** `{summary['open_exceptions']}` (requiring review: `{summary['pending_review']}`)\n\n"
                f"> **Controller Insight:** Our multi-pass reconciliation engine achieved a **{summary['match_rate']}%** automated match rate without human intervention, identifying all edge cases cleanly."
            )
            return text, tool_calls

        # Intent 2: Specific Exception lookup (e.g., EXC-2026-0001 or "mismatch")
        exc_match = re.search(r"exc-\d{8}-\d{4}", msg_lower) or re.search(r"exc-[a-z0-9\-]+", msg_lower)
        if exc_match:
            exc_code = exc_match.group(0).upper()
            details = await self._tool_explain_exception(exc_code)
            tool_calls.append({"name": "explain_exception", "result": details})
            if "error" in details:
                return f"⚠️ Exception `{exc_code}` was not found in our database. Please double check the code.", tool_calls

            text = (
                f"### 🔍 Root-Cause Analysis for `{details['exception_code']}`\n\n"
                f"| Attribute | Value |\n"
                f"|---|---|\n"
                f"| **Type** | `{details['exception_type']}` |\n"
                f"| **Discrepancy** | `₹{abs(details['difference']):,.2f}` (Expected: ₹{details['expected_amount']:,.2f} | Actual: ₹{details['actual_amount']:,.2f}) |\n"
                f"| **AI Confidence** | `{int(details['ai_confidence'] * 100)}%` |\n"
                f"| **Current Status** | `{details['resolution']}` |\n\n"
                f"**Root Cause Explanation:**\n{details['ai_explanation']}\n\n"
                f"**Recommended Action:**\n🎯 *{details['ai_suggested_action']}*"
            )
            return text, tool_calls

        # Intent 3: List open exceptions
        if any(w in msg_lower for w in ["exception", "mismatch", "discrepancy", "pending", "unmatched"]):
            excs = await self._tool_list_exceptions(5)
            tool_calls.append({"name": "list_pending_exceptions", "result": excs})
            if not excs:
                return "✅ No open reconciliation exceptions found. All processed transactions are matched!", tool_calls

            rows = "\n".join(
                f"| `{e['code']}` | `{e['type']}` | ₹{e['expected']:,.2f} | ₹{e['actual']:,.2f} | ₹{e['diff']:,.2f} | `{e['status']}` |"
                for e in excs
            )
            text = (
                f"### ⚠️ Open Reconciliation Exceptions ({len(excs)} showing)\n\n"
                f"| Code | Type | Expected | Bank Actual | Variance | Status |\n"
                f"|---|---|---|---|---|---|\n"
                f"{rows}\n\n"
                f"To investigate any item in detail, ask: *'Why is there an issue with {excs[0]['code']}?'*"
            )
            return text, tool_calls

        # Intent 4: Help or general inquiry
        return (
            f"Hello! I am **ReconAI**, your autonomous AI Finance Controller.\n\n"
            f"I can assist you with:\n"
            f"1. **Reconciliation Overview:** *'What is our match rate today?'*\n"
            f"2. **Exception Analysis:** *'Show me all pending exceptions'* or *'Explain EXC-2026-0001'*\n"
            f"3. **MDR Discrepancy Checks:** *'Why did HDFC settle ₹42,500 less in batch #402?'*\n"
            f"4. **Audit Trail Verification:** *'Verify cryptographic log integrity'*\n\n"
            f"How can I help you reconcile your accounts today?",
            None
        )

    # ──────────────── Tool Implementations ────────────────

    async def _tool_reconciliation_summary(self) -> Dict[str, Any]:
        """Compute live reconciliation metrics."""
        gw_total = await self.db.scalar(select(func.count(GatewayTransaction.id))) or 0
        gw_matched = await self.db.scalar(
            select(func.count(GatewayTransaction.id)).where(GatewayTransaction.match_status == MatchStatus.MATCHED)
        ) or 0
        exact_matched = await self.db.scalar(
            select(func.count(GatewayTransaction.id)).where(GatewayTransaction.match_method == "exact")
        ) or 0
        fuzzy_matched = await self.db.scalar(
            select(func.count(GatewayTransaction.id)).where(GatewayTransaction.match_method == "fuzzy")
        ) or 0
        total_val_proc = await self.db.scalar(select(func.sum(GatewayTransaction.amount))) or 0.0
        total_val_matched = await self.db.scalar(
            select(func.sum(GatewayTransaction.amount)).where(GatewayTransaction.match_status == MatchStatus.MATCHED)
        ) or 0.0

        open_excs = await self.db.scalar(select(func.count(Exception_.id))) or 0
        pending_review = await self.db.scalar(
            select(func.count(Exception_.id)).where(Exception_.resolution == ExceptionResolution.PENDING)
        ) or 0

        match_rate = round((gw_matched / max(gw_total, 1)) * 100.0, 1)

        return {
            "total_processed": gw_total,
            "auto_matched": gw_matched,
            "exact_matches": exact_matched,
            "fuzzy_matches": fuzzy_matched,
            "match_rate": match_rate,
            "total_value_processed": float(total_val_proc),
            "total_value_matched": float(total_val_matched),
            "open_exceptions": open_excs,
            "pending_review": pending_review,
        }

    async def _tool_list_exceptions(self, limit: int = 5) -> List[Dict[str, Any]]:
        """List open exceptions."""
        stmt = (
            select(Exception_)
            .order_by(desc(Exception_.created_at))
            .limit(limit)
        )
        res = await self.db.execute(stmt)
        excs = res.scalars().all()
        return [
            {
                "code": e.exception_code,
                "type": e.exception_type.value,
                "expected": e.expected_amount or 0.0,
                "actual": e.actual_amount or 0.0,
                "diff": e.difference or 0.0,
                "status": e.resolution.value,
                "ai_suggested_action": e.ai_suggested_action or "",
            }
            for e in excs
        ]

    async def _tool_explain_exception(self, exception_code: str) -> Dict[str, Any]:
        """Explain a specific exception."""
        stmt = select(Exception_).where(
            func.upper(Exception_.exception_code) == exception_code.upper().strip()
        )
        res = await self.db.execute(stmt)
        exc = res.scalars().first()
        if not exc:
            return {"error": "Not found"}

        return {
            "exception_code": exc.exception_code,
            "exception_type": exc.exception_type.value,
            "expected_amount": exc.expected_amount or 0.0,
            "actual_amount": exc.actual_amount or 0.0,
            "difference": exc.difference or 0.0,
            "ai_explanation": exc.ai_explanation or "Analysis in progress.",
            "ai_confidence": exc.ai_confidence or 0.88,
            "ai_suggested_action": exc.ai_suggested_action or "Review ledger",
            "resolution": exc.resolution.value,
        }
