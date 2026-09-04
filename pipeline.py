import os
import sys
import json
import warnings
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter
from typing import Dict, List, Tuple, Optional, Callable
from dotenv import load_dotenv
import yaml
from pydantic import BaseModel

# Suppress SDK deprecation warning for clean console output
warnings.filterwarnings("ignore", category=FutureWarning)

# Ensure utf-8 encoding for console output on Windows
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from models import FailedPayment, InterventionDecision, AuditEntry
from outcome_model import (
    simulate_outcome,
    OutcomeResult,
    get_effective_probability,
    VIOLATION_PENALTY_PAISE,
)
from data.sample_batch import BATCH, HIGH_VALUE_BATCH

load_dotenv()

# Load settings from config.yaml with robust defaults
CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Warning: Failed to parse config.yaml: {e}")
    return {}


CONFIG = load_config()

# Extract config values
RETRY_POLICY = CONFIG.get("retry_policy", {})
RETRY_CAPS: Dict[str, int] = RETRY_POLICY.get("retry_caps", {"upi": 3, "card": 4, "default": 3})
HARD_DECLINE_REASONS = set(RETRY_POLICY.get("hard_decline_reasons", ["issuer_declined", "mandate_lapsed_on_reissue"]))
RETRYABLE_REASONS = set(RETRY_POLICY.get("retryable_reasons", []))
CONFIDENCE_THRESHOLD = float(CONFIG.get("confidence_threshold", 0.60))
AFA_THRESHOLD_INR = float(CONFIG.get("afa_thresholds_inr", {}).get("e_mandate", 15000))
DEDUPE_TTL_HOURS = float(CONFIG.get("dedupe", {}).get("ttl_hours", 72))

ESCALATION_THRESHOLDS = CONFIG.get("escalation_thresholds_paise", {})
HUMAN_APPROVAL_ABOVE_PAISE = int(ESCALATION_THRESHOLDS.get("human_approval_above", 5000000))
CONFIG_VERSION = str(CONFIG.get("version", "1.0.0"))

VALID_FAILURE_REASONS = {
    "mandate_not_registered",
    "afa_required_not_completed",
    "upi_pin_failure",
    "insufficient_funds",
    "card_expired",
    "issuer_declined",
    "gateway_timeout",
    "mandate_lapsed_on_reissue",
    "pre_debit_notice_not_acked",
}

# In-memory idempotency ledger: (record_id, action) -> datetime
IDEMPOTENCY_LEDGER: Dict[Tuple[str, str], datetime] = {}


class BatchResult(BaseModel):
    total_at_risk_paise: int
    total_gross_recovered_paise: int
    total_cost_paise: int
    total_penalty_paise: int
    net_recovered_paise: int
    expected_recoverable_paise: int
    simulated_recovered_paise: int
    contacts_sent: int
    retries_made: int
    violations: int
    escalations: int
    rejected_count: int
    written_off_count: int
    action_counts: Dict[str, int]
    audit_log: List[AuditEntry]


def get_retry_cap(payment_method: str) -> int:
    """Returns the per-method retry cap from config.yaml."""
    return RETRY_CAPS.get(payment_method.lower(), RETRY_CAPS.get("default", 3))


def write_audit_log_jsonl(
    entries: List[AuditEntry],
    file_path: Optional[Path] = None,
    append: bool = False,
) -> None:
    """Writes audit entries to logs/audit_log.jsonl with exactly required fields."""
    if file_path is None:
        file_path = Path(__file__).parent / "logs" / "audit_log.jsonl"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with open(file_path, mode, encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry.to_audit_log_dict()) + "\n")


def process_batch(
    batch: List[FailedPayment],
    strategy: Optional[Callable[[FailedPayment], InterventionDecision]] = None,
    n_seeds: int = 1,
    seed: int = 0,
    penalty_paise: int = VIOLATION_PENALTY_PAISE,
    prob_multiplier: float = 1.0,
    write_audit_log: bool = False,
    append_audit_log: bool = False,
    verbose: bool = True,
    clear_ledger: bool = True,
) -> BatchResult:
    """
    Universal recovery execution pipeline.
    Keeps universal machinery:
      1. Rejection of out-of-scope records
      2. Idempotency ledger
      3. Outcome simulation via independent outcome model
      4. Financial accounting & audit trail
    All intelligence, guards, thresholds, and overrides live in the strategy.
    """
    global IDEMPOTENCY_LEDGER
    if clear_ledger:
        IDEMPOTENCY_LEDGER = {}
    
    if strategy is None:
        from strategies import strategy_agent_rules
        strategy = strategy_agent_rules

    if n_seeds > 1:
        results = [
            process_batch(
                batch,
                strategy=strategy,
                n_seeds=1,
                seed=s,
                penalty_paise=penalty_paise,
                prob_multiplier=prob_multiplier,
                write_audit_log=(write_audit_log and s == 0),
                verbose=False,
            )
            for s in range(n_seeds)
        ]
        mean_net = sum(r.net_recovered_paise for r in results) / n_seeds
        mean_gross = sum(r.total_gross_recovered_paise for r in results) / n_seeds
        min_net = min(r.net_recovered_paise for r in results)
        max_net = max(r.net_recovered_paise for r in results)
        at_risk = results[0].total_at_risk_paise
        expected = results[0].expected_recoverable_paise

        print(f"\n=== MULTI-SEED EVALUATION (n_seeds={n_seeds}) ===")
        print(f"At risk:                  ₹{at_risk / 100:,.2f}")
        print(f"Expected recoverable:     ₹{expected / 100:,.2f} ({(expected / at_risk * 100):.1f}%)")
        print(f"Simulated mean gross:     ₹{mean_gross / 100:,.2f} ({(mean_gross / at_risk * 100):.1f}%)")
        print(f"Mean Net Recovered:       ₹{mean_net / 100:,.2f}")
        print(f"Net Range (Min / Max):    ₹{min_net / 100:,.2f} / ₹{max_net / 100:,.2f}")
        return results[0]

    action_counts = Counter()
    audit_log: List[AuditEntry] = []
    total_at_risk_paise = 0
    total_gross_recovered_paise = 0
    total_cost_paise = 0
    total_penalty_paise = 0
    expected_recoverable_paise = 0
    contacts_sent = 0
    retries_made = 0
    violations_count = 0
    escalations_count = 0
    rejected_count = 0
    written_off_count = 0

    now = datetime.now()

    for row in batch:
        record_id = row.get("id", "unknown") if isinstance(row, dict) else getattr(row, "id", "unknown")
        amount_paise = row.get("amount_paise", 0) if isinstance(row, dict) else getattr(row, "amount_paise", 0)
        raw_reason = row.get("failure_reason", "") if isinstance(row, dict) else getattr(row, "failure_reason", "")

        total_at_risk_paise += amount_paise

        # 1. Universal Out-of-scope / Malformed failure_reason check
        if raw_reason not in VALID_FAILURE_REASONS:
            if verbose:
                print(f"[{record_id}] REJECTED – unknown failure_reason: '{raw_reason}'")
            rejection_decision = InterventionDecision(
                chosen_action="stop_and_writeoff",
                reason=f"Rejected out of scope: '{raw_reason}' is not a supported Indian failure reason.",
                confidence=1.0,
                max_retries_left=0,
                escalate=False,
                decision_source="guard",
                guard_fired="out_of_scope_rejection",
            )
            entry = AuditEntry(
                timestamp=now,
                record_id=record_id,
                failure_reason=raw_reason,
                decision=rejection_decision,
                amount_at_risk_paise=amount_paise,
                recovered_paise=0,
                status="rejected_out_of_scope",
                cost_paise=0,
                violation=False,
                penalty_paise=0,
                case_id=f"case_{record_id}",
                decision_source="guard",
                guard_fired="out_of_scope_rejection",
                seed=seed,
                config_version=CONFIG_VERSION,
            )
            audit_log.append(entry)
            rejected_count += 1
            continue

        payment = FailedPayment(**row) if isinstance(row, dict) else row
        
        # 2. Delegate decision purely to the strategy function
        decision = strategy(payment)
        action = decision.chosen_action
        action_counts[action] += 1

        if decision.escalate or action == "escalate_to_human":
            escalations_count += 1
        if action == "stop_and_writeoff":
            written_off_count += 1

        # 3. Universal Idempotency ledger check
        ledger_key = (payment.id, action)
        if ledger_key in IDEMPOTENCY_LEDGER:
            last_executed = IDEMPOTENCY_LEDGER[ledger_key]
            if (now - last_executed) < timedelta(hours=DEDUPE_TTL_HOURS):
                if verbose:
                    print(f"[{payment.id}] DUPLICATE SUPPRESSED – action '{action}' already executed")
                entry = AuditEntry(
                    timestamp=now,
                    record_id=payment.id,
                    failure_reason=payment.failure_reason,
                    decision=decision,
                    amount_at_risk_paise=payment.amount_paise,
                    recovered_paise=0,
                    status="duplicate_suppressed",
                    cost_paise=0,
                    violation=False,
                    penalty_paise=0,
                    case_id=f"case_{payment.id}",
                    decision_source=decision.decision_source,
                    guard_fired=decision.guard_fired or "idempotency_deduplication",
                    seed=seed,
                    config_version=CONFIG_VERSION,
                )
                audit_log.append(entry)
                continue

        # Record into idempotency ledger
        IDEMPOTENCY_LEDGER[ledger_key] = now

        # 4. Universal Outcome Simulation
        retry_cap = get_retry_cap(payment.payment_method)
        outcome: OutcomeResult = simulate_outcome(
            payment,
            action,
            seed=seed,
            retry_cap=retry_cap,
            penalty_amount_paise=penalty_paise,
            prob_multiplier=prob_multiplier,
        )

        expected_prob = outcome.effective_probability
        expected_recoverable_paise += int(payment.amount_paise * expected_prob)

        total_gross_recovered_paise += outcome.recovered_paise
        total_cost_paise += outcome.cost_paise
        total_penalty_paise += outcome.penalty_paise

        if outcome.contacted:
            contacts_sent += 1
        if outcome.retried:
            retries_made += 1
        if outcome.violation:
            violations_count += 1

        if action == "stop_and_writeoff":
            status = "written_off"
        elif decision.escalate or action == "escalate_to_human":
            status = "escalated"
        elif outcome.recovered_paise > 0:
            status = "recovered"
        else:
            status = "failed"

        entry = AuditEntry(
            timestamp=now,
            record_id=payment.id,
            failure_reason=payment.failure_reason,
            decision=decision,
            amount_at_risk_paise=payment.amount_paise,
            recovered_paise=outcome.recovered_paise,
            status=status,
            cost_paise=outcome.cost_paise,
            violation=outcome.violation,
            penalty_paise=outcome.penalty_paise,
            case_id=f"case_{payment.id}",
            decision_source=decision.decision_source,
            guard_fired=decision.guard_fired,
            seed=seed,
            config_version=CONFIG_VERSION,
        )
        audit_log.append(entry)

        if verbose:
            recovery_str = f" [RECOVERED ₹{outcome.recovered_paise/100:,.2f}]" if outcome.recovered_paise > 0 else ""
            violation_str = " [COMPLIANCE VIOLATION]" if outcome.violation else ""
            guard_str = f" [GUARD: {decision.guard_fired}]" if decision.guard_fired else ""
            print(
                f"[{payment.id}] {payment.failure_reason} (₹{payment.amount_paise/100:,.2f}) → {action} (conf={decision.confidence:.2f}){guard_str}{recovery_str}{violation_str}"
            )

    if write_audit_log and seed == 0:
        write_audit_log_jsonl(audit_log, append=append_audit_log)

    net_recovered_paise = total_gross_recovered_paise - total_cost_paise - total_penalty_paise
    recovery_rate_pct = (total_gross_recovered_paise / total_at_risk_paise * 100) if total_at_risk_paise > 0 else 0.0

    batch_result = BatchResult(
        total_at_risk_paise=total_at_risk_paise,
        total_gross_recovered_paise=total_gross_recovered_paise,
        total_cost_paise=total_cost_paise,
        total_penalty_paise=total_penalty_paise,
        net_recovered_paise=net_recovered_paise,
        expected_recoverable_paise=expected_recoverable_paise,
        simulated_recovered_paise=total_gross_recovered_paise,
        contacts_sent=contacts_sent,
        retries_made=retries_made,
        violations=violations_count,
        escalations=escalations_count,
        rejected_count=rejected_count,
        written_off_count=written_off_count,
        action_counts=dict(action_counts),
        audit_log=audit_log,
    )

    if verbose:
        print("\n=== RECOVERY PIPELINE SUMMARY ===")
        print(f"Processed:                {len(batch)}")
        print(f"At risk:                  ₹{total_at_risk_paise / 100:,.2f}")
        print(f"Expected recoverable:     ₹{expected_recoverable_paise / 100:,.2f}")
        print(f"Simulated gross recovery: ₹{total_gross_recovered_paise / 100:,.2f}")
        print(f"Intervention cost:        ₹{total_cost_paise / 100:,.2f}")
        print(f"Compliance penalties:     ₹{total_penalty_paise / 100:,.2f}")
        print(f"Net Recovered:            ₹{net_recovered_paise / 100:,.2f}")
        print(f"Recovery rate (gross):    {recovery_rate_pct:.1f}%")
        print(f"Contacts sent:            {contacts_sent}")
        print(f"Retries attempted:        {retries_made}")
        print(f"Compliance violations:    {violations_count}")
        print(f"Audit entries:            {len(audit_log)}")
        print("\n--- Action Breakdown ---")
        for act, count in sorted(action_counts.items()):
            print(f"  • {act}: {count}")
        print("\n--- Exception Counts ---")
        print(f"  • Rejected (out-of-scope): {rejected_count}")
        print(f"  • Written off (retry limit): {written_off_count}")
        print(f"  • Escalated to human:      {escalations_count}")

    return batch_result


def main():
    parser = argparse.ArgumentParser(description="Razorpay Subscription Recovery Pipeline")
    parser.add_argument(
        "--rules-only",
        action="store_true",
        help="Run entirely via deterministic rule engine without calling LLM",
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Run full 7-strategy multi-seed benchmark against Oracle upper bound",
    )
    parser.add_argument(
        "--demo-retry-exhaustion",
        action="store_true",
        help="Demo retry exhaustion failure mode (attempt_count >= per-method cap)",
    )
    parser.add_argument(
        "--populate-llm-cache",
        action="store_true",
        help="Call Gemini API with exponential backoff to populate the local LLM decision cache",
    )
    parser.add_argument(
        "--refresh-llm-cache",
        action="store_true",
        help="Force regeneration of cached LLM decisions by calling Gemini API",
    )
    parser.add_argument(
        "--sweep-penalty",
        action="store_true",
        help="Run sensitivity sweep across multiple compliance penalty levels",
    )
    parser.add_argument(
        "--sweep-probabilities",
        action="store_true",
        help="Run sensitivity sweep across multiple recovery probability multipliers (0.8x to 1.2x)",
    )
    parser.add_argument(
        "--demo-out-of-scope",
        action="store_true",
        help="Demo out-of-scope / malformed failure_reason rejection",
    )
    parser.add_argument(
        "--demo-low-confidence",
        action="store_true",
        help=f"Demo low-confidence escalation override (confidence < {CONFIDENCE_THRESHOLD:.2f})",
    )
    parser.add_argument(
        "--demo-high-value",
        action="store_true",
        help="Demo high-value monetary threshold escalation guard (> ₹50,000)",
    )
    parser.add_argument(
        "--seeds",
        type=int,
        default=1,
        help="Number of evaluation seeds to run (default: 1)",
    )
    parser.add_argument(
        "--penalty",
        type=int,
        default=500,
        help="Compliance penalty per violation in INR (default: 500)",
    )

    args = parser.parse_args()
    penalty_paise = args.penalty * 100

    if args.populate_llm_cache:
        from strategies import populate_llm_cache
        valid_records = [
            FailedPayment(**r) if isinstance(r, dict) else r
            for r in BATCH
            if (r.get("failure_reason", "") if isinstance(r, dict) else r.failure_reason) in VALID_FAILURE_REASONS
        ]
        populate_llm_cache(valid_records, refresh=args.refresh_llm_cache)
    elif args.sweep_penalty:
        from benchmark import run_penalty_sweep
        run_penalty_sweep(BATCH, n_seeds=args.seeds if args.seeds > 1 else 200)
    elif args.sweep_probabilities:
        from benchmark import run_probability_sweep
        run_probability_sweep(BATCH, n_seeds=args.seeds if args.seeds > 1 else 200, penalty_paise=penalty_paise)
    elif args.benchmark:
        from benchmark import run_benchmark
        run_benchmark(
            BATCH,
            n_seeds=args.seeds if args.seeds > 1 else 200,
            penalty_paise=penalty_paise,
            refresh_llm_cache=args.refresh_llm_cache,
        )
    elif args.demo_retry_exhaustion:
        print("\n=== DEMO MODE: RETRY EXHAUSTION ===")
        print("Trigger: attempt_count >= per-method retry_caps -> Force stop_and_writeoff\n")
        demo_batch = [
            row for row in BATCH
            if (row.get("attempt_count", 0) if isinstance(row, dict) else row.attempt_count) >= get_retry_cap(
                row.get("payment_method", "default") if isinstance(row, dict) else row.payment_method
            )
        ]
        from strategies import strategy_agent_rules
        process_batch(demo_batch, strategy=strategy_agent_rules)
    elif args.demo_out_of_scope:
        print("\n=== DEMO MODE: OUT OF SCOPE / MALFORMED ===")
        print("Trigger: failure_reason not in 9 valid Indian reasons\n")
        demo_batch = [
            row for row in BATCH
            if (row.get("failure_reason", "") if isinstance(row, dict) else row.failure_reason) not in VALID_FAILURE_REASONS
        ]
        from strategies import strategy_agent_rules
        process_batch(demo_batch, strategy=strategy_agent_rules)
    elif args.demo_low_confidence:
        print("\n=== DEMO MODE: LOW CONFIDENCE ESCALATION ===")
        print(f"Trigger: confidence < {CONFIDENCE_THRESHOLD:.2f} -> Force escalate_to_human\n")
        demo_batch = [
            row for row in BATCH
            if "dispute" in (row.get("notes", "").lower() if isinstance(row, dict) else row.notes.lower())
        ]
        if not demo_batch:
            demo_batch = [BATCH[7]]
        from strategies import strategy_agent_rules
        process_batch(demo_batch, strategy=strategy_agent_rules)
    elif args.demo_high_value:
        print("\n=== DEMO MODE: HIGH-VALUE MONETARY THRESHOLD ESCALATION ===")
        print(f"Trigger: amount_paise > {HUMAN_APPROVAL_ABOVE_PAISE} (₹{HUMAN_APPROVAL_ABOVE_PAISE/100:,.2f}) -> Force escalate_to_human (guard_fired='high_value_escalation') before any model call or retry.\n")
        from strategies import strategy_agent_rules
        process_batch(
            HIGH_VALUE_BATCH,
            strategy=strategy_agent_rules,
            write_audit_log=True,
            append_audit_log=True,
            verbose=True,
        )
    else:
        from strategies import strategy_agent_llm, strategy_agent_rules
        strat = strategy_agent_rules if args.rules_only else (
            lambda rec: strategy_agent_llm(rec, refresh_cache=args.refresh_llm_cache)
        )
        process_batch(BATCH, strategy=strat, n_seeds=args.seeds, write_audit_log=True)


if __name__ == "__main__":
    main()
