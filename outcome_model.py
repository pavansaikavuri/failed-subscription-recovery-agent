import hashlib
from typing import Optional, Dict
from pydantic import BaseModel
from models import FailedPayment

# Base recovery probabilities by failure reason and action
RECOVERY_MATRIX: Dict[str, Dict[str, float]] = {
    "insufficient_funds": {
        "retry_now": 0.28,
        "send_upi_pin_nudge": 0.05,
        "request_mandate_reissue": 0.02,
        "send_card_update_link": 0.05,
        "escalate_to_human": 0.35,
        "stop_and_writeoff": 0.0,
        "resend_pre_debit_notice": 0.06,
    },
    "gateway_timeout": {
        "retry_now": 0.78,
        "send_upi_pin_nudge": 0.05,
        "request_mandate_reissue": 0.02,
        "send_card_update_link": 0.03,
        "escalate_to_human": 0.40,
        "stop_and_writeoff": 0.0,
        "resend_pre_debit_notice": 0.04,
    },
    "upi_pin_failure": {
        "retry_now": 0.12,
        "send_upi_pin_nudge": 0.55,
        "request_mandate_reissue": 0.02,
        "send_card_update_link": 0.02,
        "escalate_to_human": 0.30,
        "stop_and_writeoff": 0.0,
        "resend_pre_debit_notice": 0.04,
    },
    "card_expired": {
        "retry_now": 0.01,
        "send_upi_pin_nudge": 0.01,
        "request_mandate_reissue": 0.02,
        "send_card_update_link": 0.48,
        "escalate_to_human": 0.25,
        "stop_and_writeoff": 0.0,
        "resend_pre_debit_notice": 0.02,
    },
    "mandate_not_registered": {
        "retry_now": 0.02,
        "send_upi_pin_nudge": 0.03,
        "request_mandate_reissue": 0.45,
        "send_card_update_link": 0.05,
        "escalate_to_human": 0.30,
        "stop_and_writeoff": 0.0,
        "resend_pre_debit_notice": 0.03,
    },
    "mandate_lapsed_on_reissue": {
        "retry_now": 0.01,
        "send_upi_pin_nudge": 0.02,
        "request_mandate_reissue": 0.40,
        "send_card_update_link": 0.10,
        "escalate_to_human": 0.28,
        "stop_and_writeoff": 0.0,
        "resend_pre_debit_notice": 0.02,
    },
    "afa_required_not_completed": {
        "retry_now": 0.08,
        "send_upi_pin_nudge": 0.10,
        "request_mandate_reissue": 0.15,
        "send_card_update_link": 0.12,
        "escalate_to_human": 0.35,
        "stop_and_writeoff": 0.0,
        "resend_pre_debit_notice": 0.05,
    },
    "issuer_declined": {
        "retry_now": 0.06,
        "send_upi_pin_nudge": 0.02,
        "request_mandate_reissue": 0.03,
        "send_card_update_link": 0.08,
        "escalate_to_human": 0.22,
        "stop_and_writeoff": 0.0,
        "resend_pre_debit_notice": 0.02,
    },
    "pre_debit_notice_not_acked": {
        "retry_now": 0.20,
        "send_upi_pin_nudge": 0.10,
        "request_mandate_reissue": 0.05,
        "send_card_update_link": 0.03,
        "escalate_to_human": 0.30,
        "stop_and_writeoff": 0.0,
        "resend_pre_debit_notice": 0.52,
    },
}

# Cost per intervention action in paise
ACTION_COSTS: Dict[str, int] = {
    "retry_now": 100,
    "send_upi_pin_nudge": 50,
    "send_card_update_link": 50,
    "request_mandate_reissue": 200,
    "resend_pre_debit_notice": 50,
    "escalate_to_human": 15000,
    "stop_and_writeoff": 0,
}

VIOLATION_PENALTY_PAISE = 50000


class OutcomeResult(BaseModel):
    recovered_paise: int
    cost_paise: int
    violation: bool
    penalty_paise: int
    contacted: bool
    retried: bool
    effective_probability: float


def check_compliance_violation(
    record: FailedPayment, action: str, retry_cap: int = 3
) -> bool:
    """Returns True if the chosen action violates RBI/network regulatory rules."""
    if action == "retry_now":
        # 1. RBI mandate: No debit without acknowledged 24h pre-debit notice
        if record.failure_reason == "pre_debit_notice_not_acked":
            return True
        # 2. Hard decline reasons: never retry issuer declines
        if record.failure_reason == "issuer_declined":
            return True
        # 3. No valid mandate = unauthorized debit attempt
        if record.failure_reason == "mandate_lapsed_on_reissue":
            return True
        # 4. Network retry caps per payment method
        if record.attempt_count >= retry_cap:
            return True
        # 5. Payment state reconciliation check (risk of double debit)
        if getattr(record, "payment_state", "confirmed_failed") != "confirmed_failed":
            return True
    return False


def get_effective_probability(record: FailedPayment, action: str) -> float:
    """Calculates recovery probability with exponential attempt decay."""
    reason_matrix = RECOVERY_MATRIX.get(record.failure_reason, {})
    base_prob = reason_matrix.get(action, 0.0)
    decay = 0.75 ** (max(1, record.attempt_count) - 1)
    return base_prob * decay


def simulate_outcome(
    record: FailedPayment,
    action: str,
    seed: int = 0,
    retry_cap: int = 3,
    penalty_amount_paise: int = VIOLATION_PENALTY_PAISE,
) -> OutcomeResult:
    """
    Simulates genuine recovery outcome using stable cryptographic hashing.
    The same (record, action, seed) guarantees identical outcome across strategies.
    """
    effective_prob = get_effective_probability(record, action)

    # Cryptographically stable pseudo-random draw in [0, 1)
    hash_input = f"{record.id}:{action}:{seed}".encode("utf-8")
    hash_bytes = hashlib.sha256(hash_input).digest()[:8]
    hash_int = int.from_bytes(hash_bytes, byteorder="big")
    draw = hash_int / (2**64)

    # Evaluate recovery
    if draw < effective_prob:
        recovered_paise = record.amount_paise
    else:
        recovered_paise = 0

    # Evaluate compliance violation
    violation = check_compliance_violation(record, action, retry_cap=retry_cap)
    penalty_paise = penalty_amount_paise if violation else 0
    cost_paise = ACTION_COSTS.get(action, 0)

    contacted = action in [
        "send_upi_pin_nudge",
        "send_card_update_link",
        "request_mandate_reissue",
        "resend_pre_debit_notice",
    ]
    retried = (action == "retry_now")

    return OutcomeResult(
        recovered_paise=recovered_paise,
        cost_paise=cost_paise,
        violation=violation,
        penalty_paise=penalty_paise,
        contacted=contacted,
        retried=retried,
        effective_probability=effective_prob,
    )
