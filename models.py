from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel


class FailedPayment(BaseModel):
    id: str
    merchant_id: str
    customer_id: str
    amount_paise: int
    currency: str = "INR"
    failure_reason: Literal[
        "mandate_not_registered",
        "afa_required_not_completed",
        "upi_pin_failure",
        "insufficient_funds",
        "card_expired",
        "issuer_declined",
        "gateway_timeout",
        "mandate_lapsed_on_reissue",
        "pre_debit_notice_not_acked",
    ]
    attempt_count: int
    last_attempt_at: datetime
    subscription_id: Optional[str] = None
    payment_method: str
    customer_ltv_paise: int = 0
    notes: str = ""
    payment_state: Literal["confirmed_failed", "unknown", "possibly_debited"] = "confirmed_failed"


class InterventionDecision(BaseModel):
    chosen_action: Literal[
        "retry_now",
        "send_upi_pin_nudge",
        "request_mandate_reissue",
        "send_card_update_link",
        "escalate_to_human",
        "stop_and_writeoff",
        "resend_pre_debit_notice",
    ]
    reason: str
    confidence: float
    max_retries_left: int
    escalate: bool
    degraded_mode: bool = False
    decision_source: Literal["llm", "rule", "guard"] = "rule"
    guard_fired: Optional[str] = None


class AuditEntry(BaseModel):
    timestamp: datetime
    record_id: str
    failure_reason: str
    decision: InterventionDecision
    amount_at_risk_paise: int
    recovered_paise: int
    status: str
    cost_paise: int = 0
    violation: bool = False
    penalty_paise: int = 0
    case_id: Optional[str] = None
    decision_source: Literal["llm", "rule", "guard"] = "rule"
    guard_fired: Optional[str] = None
    seed: int = 0
    config_version: str = "1.0.0"

    def to_audit_log_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "case_id": self.case_id or f"case_{self.record_id}",
            "record_id": self.record_id,
            "failure_reason": self.failure_reason,
            "amount_at_risk_paise": self.amount_at_risk_paise,
            "decision_source": self.decision_source,
            "guard_fired": self.guard_fired,
            "chosen_action": self.decision.chosen_action,
            "reason": self.decision.reason,
            "confidence": self.decision.confidence,
            "escalate": self.decision.escalate,
            "degraded_mode": self.decision.degraded_mode,
            "cost_paise": self.cost_paise,
            "violation": self.violation,
            "penalty_paise": self.penalty_paise,
            "recovered_paise": self.recovered_paise,
            "status": self.status,
            "seed": self.seed,
            "config_version": self.config_version,
        }

