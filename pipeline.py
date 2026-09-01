import os
import sys
import json
import warnings
import argparse
from datetime import datetime
from collections import Counter
from dotenv import load_dotenv

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
from data.sample_batch import BATCH

load_dotenv()

total_at_risk_paise = 0
total_recovered_paise = 0
audit_log = []

_gemini_configured = False

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

ACTION_RECOVERY_RATES = {
    "retry_now": 0.70,
    "send_upi_pin_nudge": 0.65,
    "request_mandate_reissue": 0.50,
    "send_card_update_link": 0.60,
    "escalate_to_human": 0.0,
    "stop_and_writeoff": 0.0,
}


def setup_gemini():
    global _gemini_configured
    if not _gemini_configured:
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set in environment or .env")
        genai.configure(api_key=api_key)
        _gemini_configured = True


def _rule_based_fallback(record: FailedPayment) -> InterventionDecision:
    # 1. Retry Exhaustion check
    if record.attempt_count >= 4:
        return InterventionDecision(
            chosen_action="stop_and_writeoff",
            reason="Retry limit reached (attempt_count >= 4)",
            confidence=1.0,
            max_retries_left=0,
            escalate=False,
        )

    # Low confidence / dispute detection
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
            max_retries_left=2,
            escalate=False,
        )
    elif reason == "insufficient_funds":
        return InterventionDecision(
            chosen_action="retry_now",
            reason="Insufficient funds; retry scheduled for auto-debit.",
            confidence=0.75,
            max_retries_left=1,
            escalate=False,
        )
    elif reason == "card_expired":
        return InterventionDecision(
            chosen_action="send_card_update_link",
            reason="Card expired; secure update link dispatched to customer.",
            confidence=0.90,
            max_retries_left=2,
            escalate=False,
        )
    elif reason in ["mandate_not_registered", "mandate_lapsed_on_reissue"]:
        return InterventionDecision(
            chosen_action="request_mandate_reissue",
            reason="Mandate invalid or lapsed; mandate reissue requested.",
            confidence=0.80,
            max_retries_left=1,
            escalate=False,
        )
    elif reason in ["gateway_timeout", "pre_debit_notice_not_acked"]:
        return InterventionDecision(
            chosen_action="retry_now",
            reason="Transient timeout or pre-debit notice re-queued; retry scheduled.",
            confidence=0.85,
            max_retries_left=2,
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
    # 1. Retry Exhaustion: If attempt_count >= 4, force stop_and_writeoff
    if record.attempt_count >= 4:
        return InterventionDecision(
            chosen_action="stop_and_writeoff",
            reason="Retry limit reached (attempt_count >= 4)",
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
            "If the failure cause is ambiguous, disputed as fraud, or requires manual human discretion, return confidence < 0.60. "
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
        return _rule_based_fallback(record)


def process_batch(batch, use_llm: bool = True):
    global total_at_risk_paise, total_recovered_paise, audit_log

    action_counts = Counter()
    rejected_count = 0
    written_off_count = 0

    for row in batch:
        record_id = row.get("id") if isinstance(row, dict) else getattr(row, "id", "unknown")
        raw_reason = row.get("failure_reason") if isinstance(row, dict) else getattr(row, "failure_reason", "")
        amount_paise = row.get("amount_paise", 0) if isinstance(row, dict) else getattr(row, "amount_paise", 0)

        # 2. Out-of-scope / Malformed failure_reason check
        if raw_reason not in VALID_FAILURE_REASONS:
            print(f"[{record_id}] REJECTED – unknown failure_reason: '{raw_reason}'")
            rejection_decision = InterventionDecision(
                chosen_action="stop_and_writeoff",
                reason=f"Rejected out of scope: '{raw_reason}' is not a supported Indian failure reason.",
                confidence=1.0,
                max_retries_left=0,
                escalate=False,
            )
            entry = AuditEntry(
                timestamp=datetime.now(),
                record_id=record_id,
                failure_reason=raw_reason,
                decision=rejection_decision,
                amount_at_risk_paise=amount_paise,
                recovered_paise=0,
                status="rejected_out_of_scope",
            )
            audit_log.append(entry)
            total_at_risk_paise += amount_paise
            rejected_count += 1
            continue

        payment = FailedPayment(**row) if isinstance(row, dict) else row
        decision = classify_and_decide(payment, use_llm=use_llm)

        # 3. Low Confidence check (< 0.60)
        if decision.confidence < 0.60:
            print(f"[{payment.id}] Overridden due to low confidence (conf={decision.confidence:.2f}) → escalate_to_human")
            decision.chosen_action = "escalate_to_human"
            decision.escalate = True
            decision.reason = f"Low confidence override ({decision.confidence:.2f}): {decision.reason}"

        action_counts[decision.chosen_action] += 1

        # Action-based recovery calculation
        recovery_rate = ACTION_RECOVERY_RATES.get(decision.chosen_action, 0.0)
        recovered = int(payment.amount_paise * recovery_rate)

        if decision.chosen_action == "stop_and_writeoff":
            status = "written_off"
            written_off_count += 1
        elif decision.chosen_action == "escalate_to_human" or decision.escalate:
            status = "escalated"
        elif recovered > 0:
            status = "recovered"
        else:
            status = "failed"

        total_at_risk_paise += payment.amount_paise
        total_recovered_paise += recovered

        entry = AuditEntry(
            timestamp=datetime.now(),
            record_id=payment.id,
            failure_reason=payment.failure_reason,
            decision=decision,
            amount_at_risk_paise=payment.amount_paise,
            recovered_paise=recovered,
            status=status,
        )
        audit_log.append(entry)

        print(
            f"[{payment.id}] {payment.failure_reason} → {decision.chosen_action} (conf={decision.confidence:.2f})"
        )

    recovery_rate_pct = (total_recovered_paise / total_at_risk_paise * 100) if total_at_risk_paise > 0 else 0.0

    print("\n=== SUMMARY ===")
    print(f"Processed: {len(batch)}")
    print(f"At risk: ₹{total_at_risk_paise / 100:,.2f}")
    print(f"Recovered (sim): ₹{total_recovered_paise / 100:,.2f}")
    print(f"Recovery rate: {recovery_rate_pct:.1f}%")
    print(f"Audit entries: {len(audit_log)}")
    print("\n--- Action Breakdown ---")
    for action, count in sorted(action_counts.items()):
        print(f"  • {action}: {count}")
    print("\n--- Exception Counts ---")
    print(f"  • Rejected (out-of-scope): {rejected_count}")
    print(f"  • Written off (retry limit): {written_off_count}")


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
        help="Demo retry exhaustion failure mode (attempt_count >= 4)",
    )
    parser.add_argument(
        "--demo-out-of-scope",
        action="store_true",
        help="Demo out-of-scope / malformed failure_reason rejection",
    )
    parser.add_argument(
        "--demo-low-confidence",
        action="store_true",
        help="Demo low-confidence escalation override",
    )

    args = parser.parse_args()

    if args.demo_retry_exhaustion:
        print("\n=== DEMO MODE: RETRY EXHAUSTION ===")
        print("Trigger: attempt_count >= 4 -> Force stop_and_writeoff\n")
        demo_batch = [
            row for row in BATCH
            if (row.get("attempt_count", 0) if isinstance(row, dict) else row.attempt_count) >= 4
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
        print("Trigger: confidence < 0.60 -> Force escalate_to_human\n")
        demo_batch = [
            row for row in BATCH
            if "dispute" in (row.get("notes", "").lower() if isinstance(row, dict) else row.notes.lower())
        ]
        if not demo_batch:
            demo_batch = [BATCH[7]]
        process_batch(demo_batch, use_llm=False)
    else:
        use_llm = not args.rules_only
        process_batch(BATCH, use_llm=use_llm)


if __name__ == "__main__":
    main()
