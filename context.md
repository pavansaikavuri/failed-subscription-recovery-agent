# Project Context - Razorpay AI Buildathon Track 3

## Goal
Build a Failed Subscription / Payment Recovery Agent that:
- Takes a batch of failed payments
- Classifies the real Indian failure reason
- Chooses a bounded intervention
- Evaluates genuine outcomes using an independent, hidden outcome model (probabilities, attempt decay, action costs, compliance penalties)
- Logs every decision in an audit trail
- Tracks ₹ at risk, expected recoverable, gross/net recovered, costs, and compliance violations

## Current Status
- outcome_model.py: Done (RECOVERY_MATRIX, attempt decay, action costs, compliance violation checks with ₹500 penalties, cryptographically stable hashed outcome simulation)
- models.py: Done (FailedPayment with payment_state, InterventionDecision with degraded_mode & resend_pre_debit_notice, AuditEntry with cost, violation, penalty)
- config.yaml: Done (Per-method retry_caps: upi:3, card:4, default:3; hard_decline_reasons; AFA threshold; dedupe TTL 72h)
- pipeline.py: Done (Uses outcome_model, BatchResult model, fail-closed LLM safety, payment_state double-debit pre-check, active 72h idempotency ledger, per-method retry caps, and multi-seed Monte Carlo evaluation)
- data/sample_batch.py: Done (40 realistic rows covering 9 Indian failure reasons, multi-tier pricing ₹199–₹9999, attempt counts 1–5, and failure mode triggers)
- requirements.txt: Done (pydantic, python-dotenv, google-generativeai, pyyaml)

---

## Evaluation Results (Independent Outcome Model)
- **Batch Size**: 40 transactions
- **Amount at Risk**: ₹98,952.00
- **Expected Recoverable**: ₹23,705.58 (~24.0%)
- **Multi-Seed Mean Net Recovered**: ~₹20,353.30
- **Compliance Violations**: 0
