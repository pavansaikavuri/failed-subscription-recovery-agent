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
import hashlib
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
from outcome_model import simulate_outcome, OutcomeResult, get_effective_probability
from data.sample_batch import BATCH

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


def compute_policy_version() -> str:
    """Computes a SHA256 hash of relevant config.yaml values: retry_caps, hard_decline_reasons, confidence_threshold."""
    policy_data = {
        "retry_caps": RETRY_CAPS,
        "hard_decline_reasons": sorted(list(HARD_DECLINE_REASONS)),
        "confidence_threshold": CONFIDENCE_THRESHOLD,
    }
    encoded = json.dumps(policy_data, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:12]


POLICY_VERSION = compute_policy_version()
_policy_version_printed = False


def print_policy_version_once():
    global _policy_version_printed
    if not _policy_version_printed:
        print(f"Policy Version: {POLICY_VERSION}")
        _policy_version_printed = True

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


def process_batch(
    batch: List[dict],
    strategy: Optional[Callable[[FailedPayment], InterventionDecision]] = None,
    use_llm: bool = True,
    seed: int = 0,
    n_seeds: int = 1,
    verbose: bool = True,
    clear_ledger: bool = True,
    audit_out: Optional[str] = "audit_log.jsonl",
    escalations_out: Optional[str] = "escalations.json",
) -> BatchResult:
    """
    Universal batch execution engine:
    1. Rejects out-of-scope / malformed failure reasons gracefully
    2. Enforces idempotency ledger deduplication
    3. Calls strategy(payment) to obtain decision
    4. Simulates genuine recovery outcome via outcome_model
    5. Returns structured accounting and audit records
    """
    global IDEMPOTENCY_LEDGER
    print_policy_version_once()
    if clear_ledger:
        IDEMPOTENCY_LEDGER = {}

    # Import strategies lazily if not provided
    if strategy is None:
        from strategies import strategy_agent_llm, strategy_agent_rules
        strategy = strategy_agent_llm if use_llm else strategy_agent_rules

    if n_seeds > 1:
        results = [
            process_batch(
                batch,
                strategy=strategy,
                use_llm=use_llm,
                seed=s,
                n_seeds=1,
                verbose=False,
                clear_ledger=True,
                audit_out=audit_out if s == 0 else None,
                escalations_out=escalations_out if s == 0 else None,
            )
            for s in range(n_seeds)
        ]
        mean_net = sum(r.net_recovered_paise for r in results) / n_seeds
        min_net = min(r.net_recovered_paise for r in results)
        max_net = max(r.net_recovered_paise for r in results)
        mean_gross = sum(r.total_gross_recovered_paise for r in results) / n_seeds
        expected = results[0].expected_recoverable_paise
        at_risk = results[0].total_at_risk_paise

        print(f"\n=== MULTI-SEED EVALUATION (n_seeds={n_seeds}) ===")
        print(f"At risk:                  ₹{at_risk / 100:,.2f}")
        print(f"Expected recoverable:     ₹{expected / 100:,.2f} ({(expected / at_risk * 100):.1f}%)")
        print(f"Simulated mean gross:     ₹{mean_gross / 100:,.2f} ({(mean_gross / at_risk * 100):.1f}%)")
        print(f"Mean Net Recovered:       ₹{mean_net / 100:,.2f}")
        print(f"Net Range (Min / Max):    ₹{min_net / 100:,.2f} / ₹{max_net / 100:,.2f}")
        return results[0]

    action_counts = Counter()
    audit_log: List[AuditEntry] = []
    escalations_data: List[dict] = []
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
        record_id = row.get("id") if isinstance(row, dict) else getattr(row, "id", "unknown")
        raw_reason = row.get("failure_reason") if isinstance(row, dict) else getattr(row, "failure_reason", "")
        amount_paise = row.get("amount_paise", 0) if isinstance(row, dict) else getattr(row, "amount_paise", 0)

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
                guard_triggered="out_of_scope",
                model_version="guard-v1",
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
                model_version="guard-v1",
                policy_version=POLICY_VERSION,
                decision_source="guard",
                guard_triggered="out_of_scope",
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

        # 3. Universal Idempotency ledger check (dedupe.ttl_hours window)
        ledger_key = (payment.id, action)
        if ledger_key in IDEMPOTENCY_LEDGER:
            last_executed = IDEMPOTENCY_LEDGER[ledger_key]
            if (now - last_executed) < timedelta(hours=DEDUPE_TTL_HOURS):
                if verbose:
                    print(f"[{payment.id}] DUPLICATE SUPPRESSED – action '{action}' already executed within {DEDUPE_TTL_HOURS}h")
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
                    model_version="guard-v1",
                    policy_version=POLICY_VERSION,
                    decision_source="guard",
                    guard_triggered="idempotency_ledger",
                )
                audit_log.append(entry)
                continue

        # Record into idempotency ledger
        IDEMPOTENCY_LEDGER[ledger_key] = now

        # 4. Universal Outcome Simulation via independent outcome model
        retry_cap = get_retry_cap(payment.payment_method)
        outcome: OutcomeResult = simulate_outcome(
            payment, action, seed=seed, retry_cap=retry_cap
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

        dec_source = getattr(decision, "decision_source", None) or ("guard" if getattr(decision, "guard_triggered", None) else "rules")
        mod_version = getattr(decision, "model_version", None) or ("guard-v1" if dec_source == "guard" else "rules-v1")
        guard_trig = getattr(decision, "guard_triggered", None)

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
            model_version=mod_version,
            policy_version=POLICY_VERSION,
            decision_source=dec_source,
            guard_triggered=guard_trig,
        )
        audit_log.append(entry)

        # Track human escalations for separate export
        if action == "escalate_to_human" or decision.escalate:
            p_state = getattr(payment, "payment_state", "confirmed_failed")
            if p_state != "confirmed_failed":
                esc_trigger = "ambiguous_payment_state"
            elif getattr(decision, "degraded_mode", False) or "degraded" in decision.reason.lower() or "llm unavailable" in decision.reason.lower():
                esc_trigger = "model_unavailable"
            elif decision.confidence < CONFIDENCE_THRESHOLD:
                esc_trigger = "low_confidence"
            else:
                esc_trigger = "rule_escalation"

            escalations_data.append({
                "record_id": payment.id,
                "amount_paise": payment.amount_paise,
                "failure_reason": payment.failure_reason,
                "escalation_trigger": esc_trigger,
                "confidence": round(float(decision.confidence), 4),
                "decision_reason": decision.reason,
                "reason": decision.reason,
                "payment_state": p_state,
            })

        if verbose:
            recovery_str = f" [RECOVERED ₹{outcome.recovered_paise/100:,.2f}]" if outcome.recovered_paise > 0 else ""
            violation_str = " [COMPLIANCE VIOLATION]" if outcome.violation else ""
            print(
                f"[{payment.id}] {payment.failure_reason} → {action} (conf={decision.confidence:.2f}){recovery_str}{violation_str}"
            )

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

    # Write audit log to disk as newline-delimited JSON (overwrite per run)
    if audit_out:
        out_path = Path(audit_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            for entry in audit_log:
                f.write(entry.model_dump_json() + "\n")

    # Export escalations separately to escalations.json (overwrite per run)
    if escalations_out:
        esc_path = Path(escalations_out)
        esc_path.parent.mkdir(parents=True, exist_ok=True)
        with open(esc_path, "w", encoding="utf-8") as f:
            json.dump(escalations_data, f, indent=2)

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


def print_audit_summary(audit_path: str = "audit_log.jsonl"):
    """Reads audit_log.jsonl back from disk and prints counts by decision_source, guard_triggered, and status."""
    path = Path(audit_path)
    if not path.exists():
        print(f"Error: Audit log file not found at: {path}")
        return

    by_decision_source = Counter()
    by_guard_triggered = Counter()
    by_status = Counter()
    total_entries = 0

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            total_entries += 1

            source = record.get("decision_source", "unknown")
            by_decision_source[source] += 1

            guard = record.get("guard_triggered")
            guard_label = str(guard) if guard is not None else "null"
            by_guard_triggered[guard_label] += 1

            status = record.get("status", "unknown")
            by_status[status] += 1

    print(f"\n=== AUDIT SUMMARY ({path.name}) ===")
    print(f"Total entries: {total_entries}")
    print("\nCounts by decision_source:")
    for src, count in sorted(by_decision_source.items()):
        print(f"  • {src}: {count}")
    print("\nCounts by guard_triggered:")
    for guard, count in sorted(by_guard_triggered.items()):
        print(f"  • {guard}: {count}")
    print("\nCounts by status:")
    for st, count in sorted(by_status.items()):
        print(f"  • {st}: {count}")


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
        "--seeds",
        type=int,
        default=1,
        help="Number of evaluation seeds to run (default: 1)",
    )
    parser.add_argument(
        "--audit-out",
        type=str,
        default="audit_log.jsonl",
        help="Path to write the JSONL audit log (default: audit_log.jsonl)",
    )
    parser.add_argument(
        "--escalations-out",
        type=str,
        default="escalations.json",
        help="Path to export human escalations JSON (default: escalations.json)",
    )
    parser.add_argument(
        "--audit-summary",
        action="store_true",
        help="Read audit_log.jsonl back and print counts by decision_source, guard_triggered, and status",
    )

    args = parser.parse_args()

    print_policy_version_once()

    if args.audit_summary and not (
        args.rules_only
        or args.benchmark
        or args.populate_llm_cache
        or args.refresh_llm_cache
        or args.sweep_penalty
        or args.demo_retry_exhaustion
        or args.demo_out_of_scope
        or args.demo_low_confidence
    ):
        print_audit_summary(args.audit_out)
        return

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
    elif args.benchmark:
        from benchmark import run_benchmark
        run_benchmark(BATCH, n_seeds=args.seeds if args.seeds > 1 else 200, refresh_llm_cache=args.refresh_llm_cache)
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
        process_batch(demo_batch, strategy=strategy_agent_rules, audit_out=args.audit_out, escalations_out=args.escalations_out)
    elif args.demo_out_of_scope:
        print("\n=== DEMO MODE: OUT OF SCOPE / MALFORMED ===")
        print("Trigger: failure_reason not in 9 valid Indian reasons\n")
        demo_batch = [
            row for row in BATCH
            if (row.get("failure_reason", "") if isinstance(row, dict) else row.failure_reason) not in VALID_FAILURE_REASONS
        ]
        from strategies import strategy_agent_rules
        process_batch(demo_batch, strategy=strategy_agent_rules, audit_out=args.audit_out, escalations_out=args.escalations_out)
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
        process_batch(demo_batch, strategy=strategy_agent_rules, audit_out=args.audit_out, escalations_out=args.escalations_out)
    else:
        from strategies import strategy_agent_llm, strategy_agent_rules
        strat = strategy_agent_rules if args.rules_only else (
            lambda rec: strategy_agent_llm(rec, refresh_cache=args.refresh_llm_cache)
        )
        process_batch(BATCH, strategy=strat, n_seeds=args.seeds, audit_out=args.audit_out, escalations_out=args.escalations_out)

    if args.audit_summary:
        print_audit_summary(args.audit_out)


if __name__ == "__main__":
    main()
