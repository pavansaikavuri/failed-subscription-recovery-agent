import sys
from pathlib import Path
from datetime import datetime

# Ensure root package modules are importable in test runner
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from models import FailedPayment
from pipeline import run_recovery_campaign, BATCH
from strategies import strategy_agent_rules


def test_recovered_record_does_not_reenter_subsequent_cycle():
    """Records successfully recovered in Cycle 1 never re-enter subsequent campaign cycles."""
    result = run_recovery_campaign(
        BATCH,
        strategy=strategy_agent_rules,
        seed=0,
        max_cycles=3,
        audit_out=None,
        escalations_out=None,
        verbose=False,
    )

    # Identify records recovered in Cycle 1
    recovered_in_c1 = {
        e.record_id
        for e in result.all_audit_entries
        if e.cycle_number == 1 and e.status == "recovered"
    }

    assert len(recovered_in_c1) > 0, "Expected at least one record to be recovered in Cycle 1"

    # Verify none of these records re-entered Cycle 2 or Cycle 3
    reentered_records = {
        e.record_id
        for e in result.all_audit_entries
        if e.cycle_number > 1 and e.record_id in recovered_in_c1
    }

    assert len(reentered_records) == 0, (
        f"Recovered records erroneously re-entered subsequent cycles: {reentered_records}"
    )


def test_later_cycles_shift_away_from_retry_now():
    """Policy dynamics: across subsequent cycles, retry_now volume decays as retry caps and escalation kick in."""
    result = run_recovery_campaign(
        BATCH,
        strategy=strategy_agent_rules,
        seed=0,
        max_cycles=4,
        audit_out=None,
        escalations_out=None,
        verbose=False,
    )

    assert len(result.cycle_summaries) >= 2, "Expected at least 2 cycles to run"

    c1_retries = result.cycle_summaries[0].actions.get("retry_now", 0)
    later_retries = result.cycle_summaries[-1].actions.get("retry_now", 0)

    # Retries must drop significantly due to attempt decay, retry caps, and successful recoveries
    assert later_retries < c1_retries, (
        f"Expected retries to drop across cycles, got C1={c1_retries} vs last={later_retries}"
    )

    # Final cycle must show non-retry actions (writeoffs, escalations, or completions)
    last_cycle = result.cycle_summaries[-1]
    assert (
        last_cycle.written_off_count > 0
        or last_cycle.escalated_count > 0
        or last_cycle.unrecovered_active_count == 0
    ), "Later cycles should resolve toward terminal actions (writeoff/escalation/completion)"
