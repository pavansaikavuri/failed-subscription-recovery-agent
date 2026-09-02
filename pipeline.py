import os
import sys
import json
import warnings
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter
from typing import Dict, List, Tuple, Optional
from dotenv import load_dotenv
import yaml
from pydantic import BaseModel

# Suppress SDK deprecation warning for clean console output
warnings.filterwarnings("ignore", category=FutureWarning)
import google.generativeai as genai

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
_gemini_configured = False


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


def setup_gemini():
    global _gemini_configured
    if not _gemini_configured:
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set in environment or .env")
        genai.configure(api_key=api_key)
        _gemini_configured = True


def _rule_based_fallback(record: FailedPayment) -> InterventionDecision:
    retry_cap = get_retry_cap(record.payment_method)

    # 1. Retry Exhaustion check (attempt_count >= per-method cap)
    if record.attempt_count >= retry_cap:
        return InterventionDecision(
            chosen_action="stop_and_writeoff",
            reason=f"Retry limit reached for {record.payment_method} (attempt_count >= {retry_cap})",
            confidence=1.0,
            max_retries_left=0,
            escalate=False,
        )

    # 2. Hard decline reasons (never retry)
    if record.failure_reason in HARD_DECLINE_REASONS:
        return InterventionDecision(
            chosen_action="escalate_to_human",
            reason=f"Hard decline reason '{record.failure_reason}'; non-retryable per policy.",
            confidence=0.80,
            max_retries_left=0,
            escalate=True,
        )

    # 3. Customer dispute / fraud detection
    if "dispute" in record.notes.lower() or "fraud" in record.notes.lower():
        return InterventionDecision(
            chosen_action="escalate_to_human",
            reason="Customer dispute or potential fraud suspected; requires manual review.",
            confidence=0.55,
            max_retries_left=0,
            escalate=True,
        )

    reason = record.failure_reason

    if reason == "upi_pin_failure":
        return InterventionDecision(
            chosen_action="send_upi_pin_nudge",
            reason="Customer failed UPI PIN entry; nudge sent to re-enter PIN.",
            confidence=0.85,
            max_retries_left=max(0, retry_cap - record.attempt_count),
            escalate=False,
        )
    elif reason == "insufficient_funds":
        return InterventionDecision(
            chosen_action="retry_now",
            reason="Insufficient funds; auto-debit retry scheduled.",
            confidence=0.75,
            max_retries_left=max(0, retry_cap - record.attempt_count),
            escalate=False,
        )
    elif reason == "card_expired":
        return InterventionDecision(
            chosen_action="send_card_update_link",
            reason="Card expired; secure update link dispatched to customer.",
            confidence=0.90,
            max_retries_left=max(0, retry_cap - record.attempt_count),
            escalate=False,
        )
    elif reason == "mandate_not_registered":
        return InterventionDecision(
            chosen_action="request_mandate_reissue",
            reason="Mandate not registered; mandate reissue requested.",
            confidence=0.80,
            max_retries_left=max(0, retry_cap - record.attempt_count),
            escalate=False,
        )
    elif reason == "pre_debit_notice_not_acked":
        return InterventionDecision(
            chosen_action="resend_pre_debit_notice",
            reason="Pre-debit notice unacknowledged; 24h pre-debit notice re-queued per RBI rules.",
            confidence=0.85,
            max_retries_left=max(0, retry_cap - record.attempt_count),
            escalate=False,
        )
    elif reason == "afa_required_not_completed":
        return InterventionDecision(
            chosen_action="escalate_to_human",
            reason=f"AFA challenge abandoned; requires customer authentication under RBI threshold (₹{AFA_THRESHOLD_INR:,.0f}).",
            confidence=0.65,
            max_retries_left=0,
            escalate=True,
        )
    elif reason == "gateway_timeout":
        return InterventionDecision(
            chosen_action="retry_now",
            reason="Transient gateway timeout; network retry scheduled.",
            confidence=0.85,
            max_retries_left=max(0, retry_cap - record.attempt_count),
            escalate=False,
        )
    else:
        return InterventionDecision(
            chosen_action="escalate_to_human",
            reason="Complex or unclassified failure reason; escalated to manual review.",
            confidence=0.50,
            max_retries_left=0,
            escalate=True,
        )


def classify_and_decide(record: FailedPayment, use_llm: bool = True) -> InterventionDecision:
    # 0. Payment State Reconciliation Check (BEFORE LLM and before rules)
    payment_state = getattr(record, "payment_state", "confirmed_failed")
    if payment_state != "confirmed_failed":
        return InterventionDecision(
            chosen_action="escalate_to_human",
            reason="Reconcile before acting: payment state ambiguous, retry risks double debit.",
            confidence=0.50,
            max_retries_left=0,
            escalate=True,
        )

    # 1. Retry Exhaustion check
    retry_cap = get_retry_cap(record.payment_method)
    if record.attempt_count >= retry_cap:
        return InterventionDecision(
            chosen_action="stop_and_writeoff",
            reason=f"Retry limit reached for {record.payment_method} (attempt_count >= {retry_cap})",
            confidence=1.0,
            max_retries_left=0,
            escalate=False,
        )

    if not use_llm:
        return _rule_based_fallback(record)

    try:
        setup_gemini()
        system_prompt = (
            "You are a Razorpay revenue recovery specialist for Indian payments. "
            "Choose the single best bounded intervention. "
            f"If the failure cause is ambiguous, disputed as fraud, or requires manual human discretion, return confidence < {CONFIDENCE_THRESHOLD:.2f}. "
            "Reply with ONLY valid JSON strictly matching the requested schema."
        )
        user_message = (
            f"failure_reason: {record.failure_reason}\n"
            f"amount_paise: {record.amount_paise}\n"
            f"attempt_count: {record.attempt_count}\n"
            f"payment_method: {record.payment_method}\n"
            f"customer_ltv_paise: {record.customer_ltv_paise}\n"
            f"notes: {record.notes}"
        )

        model = genai.GenerativeModel(
            model_name="gemini-3.6-flash",
            system_instruction=system_prompt,
            generation_config={
                "response_mime_type": "application/json",
                "response_schema": InterventionDecision,
                "temperature": 0.2,
            },
        )
        response = model.generate_content(user_message)
        data = json.loads(response.text)
        return InterventionDecision(**data)

    except Exception as e:
        print(f"LLM failed, using rule fallback. Real error: {type(e).__name__}: {e}")
        fallback_decision = _rule_based_fallback(record)

        # Fail-closed principle: An LLM outage must never be able to trigger an autonomous money-moving debit attempt.
        if fallback_decision.chosen_action == "retry_now":
            print("DEGRADED: model unavailable, refusing autonomous retry")
            fallback_decision.chosen_action = "escalate_to_human"
            fallback_decision.escalate = True
            fallback_decision.degraded_mode = True
            fallback_decision.reason = "Degraded mode: LLM unavailable, autonomous retry refused."

        return fallback_decision


def process_batch(
    batch: List[dict],
    use_llm: bool = True,
    seed: int = 0,
    n_seeds: int = 1,
    verbose: bool = True,
    clear_ledger: bool = True,
) -> BatchResult:
    """
    Processes a batch of failed payments, executing decisions and scoring outcomes
    against the independent outcome model.
    """
    global IDEMPOTENCY_LEDGER
    if clear_ledger:
        IDEMPOTENCY_LEDGER = {}

    if n_seeds > 1:
        results = [
            process_batch(batch, use_llm=use_llm, seed=s, n_seeds=1, verbose=False, clear_ledger=True)
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

        # 1. Out-of-scope / Malformed failure_reason check
        if raw_reason not in VALID_FAILURE_REASONS:
            if verbose:
                print(f"[{record_id}] REJECTED – unknown failure_reason: '{raw_reason}'")
            rejection_decision = InterventionDecision(
                chosen_action="stop_and_writeoff",
                reason=f"Rejected out of scope: '{raw_reason}' is not a supported Indian failure reason.",
                confidence=1.0,
                max_retries_left=0,
                escalate=False,
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
            )
            audit_log.append(entry)
            rejected_count += 1
            continue

        payment = FailedPayment(**row) if isinstance(row, dict) else row
        decision = classify_and_decide(payment, use_llm=use_llm)

        # 2. Low Confidence check (< CONFIDENCE_THRESHOLD from config)
        if decision.confidence < CONFIDENCE_THRESHOLD and not decision.escalate:
            if verbose:
                print(f"[{payment.id}] Overridden due to low confidence (conf={decision.confidence:.2f}) → escalate_to_human")
            decision.chosen_action = "escalate_to_human"
            decision.escalate = True
            decision.reason = f"Low confidence override ({decision.confidence:.2f}): {decision.reason}"

        action = decision.chosen_action
        action_counts[action] += 1

        if decision.escalate or action == "escalate_to_human":
            escalations_count += 1
        if action == "stop_and_writeoff":
            written_off_count += 1

        # 3. Idempotency ledger check (dedupe.ttl_hours window)
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
                )
                audit_log.append(entry)
                continue

        # Record into idempotency ledger
        IDEMPOTENCY_LEDGER[ledger_key] = now

        # 4. Simulate genuine outcome via independent outcome model
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
        )
        audit_log.append(entry)

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
        "--demo-retry-exhaustion",
        action="store_true",
        help="Demo retry exhaustion failure mode (attempt_count > per-method cap)",
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

    args = parser.parse_args()

    if args.demo_retry_exhaustion:
        print("\n=== DEMO MODE: RETRY EXHAUSTION ===")
        print("Trigger: attempt_count >= per-method retry_caps -> Force stop_and_writeoff\n")
        demo_batch = [
            row for row in BATCH
            if (row.get("attempt_count", 0) if isinstance(row, dict) else row.attempt_count) >= get_retry_cap(
                row.get("payment_method", "default") if isinstance(row, dict) else row.payment_method
            )
        ]
        process_batch(demo_batch, use_llm=False)
    elif args.demo_out_of_scope:
        print("\n=== DEMO MODE: OUT OF SCOPE / MALFORMED ===")
        print("Trigger: failure_reason not in 9 valid Indian reasons\n")
        demo_batch = [
            row for row in BATCH
            if (row.get("failure_reason", "") if isinstance(row, dict) else row.failure_reason) not in VALID_FAILURE_REASONS
        ]
        process_batch(demo_batch, use_llm=False)
    elif args.demo_low_confidence:
        print("\n=== DEMO MODE: LOW CONFIDENCE ESCALATION ===")
        print(f"Trigger: confidence < {CONFIDENCE_THRESHOLD:.2f} -> Force escalate_to_human\n")
        demo_batch = [
            row for row in BATCH
            if "dispute" in (row.get("notes", "").lower() if isinstance(row, dict) else row.notes.lower())
        ]
        if not demo_batch:
            demo_batch = [BATCH[7]]
        process_batch(demo_batch, use_llm=False)
    else:
        use_llm = not args.rules_only
        process_batch(BATCH, use_llm=use_llm, n_seeds=args.seeds)


if __name__ == "__main__":
    main()
