# Razorpay Webhook Fixtures

This directory contains realistic sample Razorpay webhook payloads used to test and verify the FastAPI webhook ingestion endpoint (`POST /webhooks/razorpay`) and replay harness (`python pipeline.py --replay-webhooks`).

## Test Webhook Secret
```text
test_webhook_secret_razorpay_2026
```
To run tests or local replay with these fixtures, ensure `RAZORPAY_WEBHOOK_SECRET` in `.env` is set to this value (configured by default).

## Fixture Index

1. **`01_payment_failed_insufficient_funds.json`**:
   Standard `payment.failed` event for insufficient funds (`error_reason: "insufficient_funds"`). Routes to `retry_now`.
2. **`02_payment_failed_upi_pin_failure.json`**:
   UPI recurring debit failed due to invalid PIN (`error_reason: "upi_pin_failure"`). Routes to `send_upi_pin_nudge`.
3. **`03_payment_failed_card_expired.json`**:
   Recurring card auto-debit failed due to card expiration (`error_reason: "card_expired"`). Routes to `send_card_update_link`.
4. **`04_payment_failed_pre_debit_not_acked.json`**:
   Auto-debit triggered before customer pre-debit notice was acknowledged (`error_reason: "pre_debit_notice_not_acked"`). Intercepted and routed to `resend_pre_debit_notice` per RBI regulations.
5. **`05_payment_failed_issuer_declined.json`**:
   Hard decline by issuing bank (`error_reason: "issuer_declined"`). Intercepted by Hard Decline Guard (`guard_triggered: "hard_decline"`) and routed to `escalate_to_human`.
6. **`06_payment_failed_retry_exhausted.json`**:
   Payment attempt exceeded per-method retry cap (`attempt_count: 4` for UPI, where cap is 3). Intercepted by Retry Cap Guard (`guard_triggered: "retry_cap"`) and routed to `stop_and_writeoff`.
7. **`07_payment_failed_possibly_debited.json`**:
   Payment state is ambiguous (`payment_state: "possibly_debited"`). Intercepted by Reconciliation Guard (`guard_triggered: "reconciliation"`) to prevent duplicate customer charge.
8. **`08_payment_failed_dispute.json`**:
   Notes indicate customer dispute / chargeback threat (`notes: "Customer flagged potential fraud / unauthorized charge"`). Intercepted by Dispute Override Guard (`guard_triggered: "dispute_override"`) and escalated to human.
9. **`09_subscription_halted_mandate_lapsed.json`**:
   `subscription.halted` event where e-mandate lapsed upon card reissue (`error_reason: "mandate_lapsed_on_reissue"`). Intercepted as non-retryable and escalated to human.
10. **`10_bad_signature.json`**:
   Payload with intentionally invalid signature header to verify HTTP 401 unauthorized rejection.
