import sys
from pathlib import Path
from datetime import datetime

# Ensure root package modules are importable in test runner
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from models import FailedPayment
from outcome_model import simulate_outcome
from strategies import strategy_agent_rules, strategy_always_retry
from pipeline import get_retry_cap, VALID_FAILURE_REASONS
from data.sample_batch import BATCH


def test_always_retry_pre_debit_notice_violation():
    """always_retry on pre_debit_notice_not_acked produces a compliance violation."""
    record = FailedPayment(
        id="pay_test_01",
        merchant_id="mer_01",
        customer_id="cust_01",
        amount_paise=150000,
        currency="INR",
        failure_reason="pre_debit_notice_not_acked",
        attempt_count=1,
        last_attempt_at=datetime(2026, 9, 1, 10, 0, 0),
        payment_method="card",
        customer_ltv_paise=500000,
        notes="Pre-debit notice unacknowledged",
        payment_state="confirmed_failed",
    )
    decision = strategy_always_retry(record)
    outcome = simulate_outcome(record, decision.chosen_action, seed=0)

    assert decision.chosen_action == "retry_now"
    assert outcome.violation is True
    assert outcome.penalty_paise == 50000


def test_always_retry_issuer_declined_violation():
    """always_retry on issuer_declined produces a compliance violation."""
    record = FailedPayment(
        id="pay_test_02",
        merchant_id="mer_01",
        customer_id="cust_02",
        amount_paise=299900,
        currency="INR",
        failure_reason="issuer_declined",
        attempt_count=1,
        last_attempt_at=datetime(2026, 9, 1, 10, 0, 0),
        payment_method="card",
        customer_ltv_paise=1000000,
        notes="Hard decline by issuer",
        payment_state="confirmed_failed",
    )
    decision = strategy_always_retry(record)
    outcome = simulate_outcome(record, decision.chosen_action, seed=0)

    assert decision.chosen_action == "retry_now"
    assert outcome.violation is True
    assert outcome.penalty_paise == 50000


def test_agent_rules_zero_violations_full_batch():
    """agent_rules never produces a violation across the full sample batch."""
    valid_records = [
        FailedPayment(**r) if isinstance(r, dict) else r
        for r in BATCH
        if (r.get("failure_reason") if isinstance(r, dict) else r.failure_reason) in VALID_FAILURE_REASONS
    ]

    for rec in valid_records:
        decision = strategy_agent_rules(rec)
        retry_cap = get_retry_cap(rec.payment_method)
        outcome = simulate_outcome(rec, decision.chosen_action, seed=0, retry_cap=retry_cap)

        assert outcome.violation is False, (
            f"Violation detected for record {rec.id} ({rec.failure_reason}) "
            f"with action {decision.chosen_action}"
        )
        assert outcome.penalty_paise == 0


def test_reconciliation_guard_blocks_possibly_debited():
    """Reconciliation guard blocks autonomous retry when payment_state is possibly_debited."""
    record = FailedPayment(
        id="pay_test_03",
        merchant_id="mer_01",
        customer_id="cust_03",
        amount_paise=99900,
        currency="INR",
        failure_reason="gateway_timeout",
        attempt_count=1,
        last_attempt_at=datetime(2026, 9, 1, 10, 0, 0),
        payment_method="upi",
        customer_ltv_paise=300000,
        notes="Bank timed out, user balance might have been deducted",
        payment_state="possibly_debited",
    )
    decision = strategy_agent_rules(record)

    # Must escalate to human rather than retry_now to prevent double debit
    assert decision.chosen_action == "escalate_to_human"
    assert decision.escalate is True
    assert "Reconcile" in decision.reason or "ambiguous" in decision.reason

    # Also verify that if unguarded retry was attempted, outcome model marks it as violation
    outcome = simulate_outcome(record, "retry_now", seed=0)
    assert outcome.violation is True


def test_simulate_outcome_deterministic_per_seed():
    """simulate_outcome returns identical results for the same (record, action, seed) across repeated calls."""
    record = FailedPayment(
        id="pay_test_04",
        merchant_id="mer_01",
        customer_id="cust_04",
        amount_paise=499900,
        currency="INR",
        failure_reason="insufficient_funds",
        attempt_count=1,
        last_attempt_at=datetime(2026, 9, 1, 10, 0, 0),
        payment_method="card",
        customer_ltv_paise=1200000,
        notes="Month-end salary delay",
        payment_state="confirmed_failed",
    )

    action = "retry_now"
    seed = 42

    result_1 = simulate_outcome(record, action, seed=seed)
    result_2 = simulate_outcome(record, action, seed=seed)
    result_3 = simulate_outcome(record, action, seed=seed)

    assert result_1.recovered_paise == result_2.recovered_paise == result_3.recovered_paise
    assert result_1.cost_paise == result_2.cost_paise == result_3.cost_paise
    assert result_1.violation == result_2.violation == result_3.violation
    assert result_1.penalty_paise == result_2.penalty_paise == result_3.penalty_paise
    assert result_1.effective_probability == result_2.effective_probability == result_3.effective_probability


def test_retry_cap_differs_by_payment_method():
    """Retry cap differs by payment_method per config.yaml (e.g. card=4, upi=3)."""
    upi_cap = get_retry_cap("upi")
    card_cap = get_retry_cap("card")
    default_cap = get_retry_cap("netbanking")

    assert upi_cap == 3
    assert card_cap == 4
    assert upi_cap != card_cap
    assert default_cap == 3
