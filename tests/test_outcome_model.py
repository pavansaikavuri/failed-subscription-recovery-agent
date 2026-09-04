import sys
import subprocess
from pathlib import Path
from datetime import datetime

# Ensure recovery_agent root is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from models import FailedPayment
from outcome_model import (
    simulate_outcome,
    get_effective_probability,
    RECOVERY_MATRIX,
)
from pipeline import process_batch
from strategies import STRATEGIES
from data.sample_batch import BATCH


def test_attempt_decay_reduces_probability_monotonically():
    """Attempt decay reduces probability monotonically with attempt_count."""
    probs = []
    for count in range(1, 6):
        record = FailedPayment(
            id=f"pay_decay_{count}",
            merchant_id="mer_01",
            customer_id="cust_01",
            amount_paise=100000,
            currency="INR",
            failure_reason="insufficient_funds",
            attempt_count=count,
            last_attempt_at=datetime(2026, 9, 1, 10, 0, 0),
            payment_method="upi",
            customer_ltv_paise=500000,
            notes="Decay test",
            payment_state="confirmed_failed",
        )
        prob = get_effective_probability(record, "retry_now")
        probs.append(prob)

    # Verify strictly monotonic decrease
    for i in range(len(probs) - 1):
        assert probs[i] > probs[i + 1], f"Probability did not decay strictly from attempt {i+1} to {i+2}: {probs[i]} <= {probs[i+1]}"


def test_retrying_card_expired_has_near_zero_recovery():
    """Retrying card_expired has near-zero recovery probability (1%)."""
    record = FailedPayment(
        id="pay_card_exp_prob",
        merchant_id="mer_01",
        customer_id="cust_01",
        amount_paise=200000,
        currency="INR",
        failure_reason="card_expired",
        attempt_count=1,
        last_attempt_at=datetime(2026, 9, 1, 10, 0, 0),
        payment_method="card",
        customer_ltv_paise=500000,
        notes="Testing expired card retry probability",
        payment_state="confirmed_failed",
    )
    prob = get_effective_probability(record, "retry_now")
    assert prob == 0.01
    assert prob < 0.05, f"Expected near-zero probability for card_expired retry, got {prob}"


def test_retrying_gateway_timeout_has_high_recovery():
    """Retrying gateway_timeout has high recovery probability (78%)."""
    record = FailedPayment(
        id="pay_gw_timeout_prob",
        merchant_id="mer_01",
        customer_id="cust_01",
        amount_paise=200000,
        currency="INR",
        failure_reason="gateway_timeout",
        attempt_count=1,
        last_attempt_at=datetime(2026, 9, 1, 10, 0, 0),
        payment_method="upi",
        customer_ltv_paise=500000,
        notes="Testing gateway timeout retry probability",
        payment_state="confirmed_failed",
    )
    prob = get_effective_probability(record, "retry_now")
    assert prob == 0.78
    assert prob > 0.70, f"Expected high recovery probability for gateway_timeout retry, got {prob}"


from benchmark import run_benchmark


def test_oracle_dominates_on_mean():
    """Oracle net strictly dominates every other strategy on mean net recovery across 200 seeds."""
    stats, _ = run_benchmark(
        BATCH,
        n_seeds=200,
        save_markdown=False,
        verbose=False,
        include_sweep=False,
    )
    mean_nets = {s.strategy_name: s.mean_net_paise for s in stats}
    oracle_net = mean_nets["oracle"]
    for name, net_val in mean_nets.items():
        assert oracle_net >= net_val, (
            f"Oracle mean net (₹{oracle_net/100:,.2f}) failed to match or beat {name} (₹{net_val/100:,.2f}) across 200 seeds"
        )


def test_identical_record_action_seed_yields_identical_outcomes_across_separate_processes():
    """Cryptographic hash stability: identical (record, action, seed) yields identical results across separate process runs."""
    snippet = """
from datetime import datetime
from models import FailedPayment
from outcome_model import simulate_outcome

record = FailedPayment(
    id="pay_cross_proc_test",
    merchant_id="mer_01",
    customer_id="cust_01",
    amount_paise=350000,
    currency="INR",
    failure_reason="insufficient_funds",
    attempt_count=2,
    last_attempt_at=datetime(2026, 9, 1, 10, 0, 0),
    payment_method="upi",
    customer_ltv_paise=500000,
    notes="Testing cross-process outcome stability",
    payment_state="confirmed_failed",
)
outcome = simulate_outcome(record, "retry_now", seed=777)
print(f"{outcome.recovered_paise}:{outcome.cost_paise}:{outcome.violation}:{outcome.penalty_paise}:{outcome.effective_probability:.6f}")
"""
    # Run in first process
    proc1 = subprocess.run(
        [sys.executable, "-c", snippet],
        capture_output=True,
        text=True,
        check=True
    )
    # Run in second separate process
    proc2 = subprocess.run(
        [sys.executable, "-c", snippet],
        capture_output=True,
        text=True,
        check=True
    )

    output1 = proc1.stdout.strip()
    output2 = proc2.stdout.strip()

    assert output1 != "", "Subprocess produced empty output"
    assert output1 == output2, f"Discrepancy across separate process runs: '{output1}' != '{output2}'"
