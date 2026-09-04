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
    decision_source: Optional[Literal["llm", "rules", "guard"]] = None
    guard_triggered: Optional[str] = None
    model_version: Optional[str] = None
    injection_flagged: bool = False


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
    model_version: str = "rules-v1"
    policy_version: str = ""
    decision_source: Literal["llm", "rules", "guard"] = "rules"
    guard_triggered: Optional[str] = None
    cycle_number: int = 1
