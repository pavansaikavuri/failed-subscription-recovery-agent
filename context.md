# Project Context - Razorpay AI Buildathon Track 3

## Goal
Build a Failed Subscription / Payment Recovery Agent that:
- Takes a batch of failed payments
- Classifies the real Indian failure reason
- Chooses a bounded intervention
- Evaluates genuine outcomes using an independent, hidden outcome model (probabilities, attempt decay, action costs, compliance penalties)
- Evaluates across a 7-strategy benchmark against the theoretical Oracle upper bound
- Logs every decision in an audit trail
- Tracks ₹ at risk, expected recoverable, gross/net recovered, costs, and compliance violations

## Current Status
- **strategies.py**: Done (Decoupled 7 strategies: `no_action`, `always_retry`, `message_only`, `naive_rules`, `agent_rules`, `agent_llm`, `oracle`)
- **benchmark.py**: Done (Runs 7 strategies across 200 Monte Carlo seeds, caches decisions, reports net recovery, regret vs oracle, match rate, contacts, retries, violations, and outputs `benchmark_results.md`)
- **outcome_model.py**: Done (RECOVERY_MATRIX, attempt decay, action costs, compliance violation checks with ₹500 penalties, cryptographically stable hashed outcome simulation)
- **models.py**: Done (FailedPayment with payment_state, InterventionDecision with degraded_mode & resend_pre_debit_notice, AuditEntry with cost, violation, penalty)
- **config.yaml**: Done (Per-method retry_caps: upi:3, card:4, default:3; hard_decline_reasons; AFA threshold; dedupe TTL 72h)
- **pipeline.py**: Done (Universal engine + `--benchmark` + `--rules-only` + `--demo-*` CLI flags)
- **data/sample_batch.py**: Done (40 realistic rows covering 9 Indian failure reasons, multi-tier pricing ₹199–₹9999, attempt counts 1–5, and failure mode triggers)

---

## Benchmark Results (200 Seeds, 40 Records, ₹98,952 at Risk)
1. **oracle**: Mean Net ₹27,509.45 | 29.6% Gross | Regret ₹0.00 | Violations: 1 (Due to unavoidable test state)
2. **naive_rules**: Mean Net ₹24,154.31 | 28.7% Gross | Regret ₹3,355.14 | **Violations: 6**
3. **agent_rules**: Mean Net ₹21,677.28 | 23.3% Gross | Regret ₹5,832.16 | **Violations: 0 (100% compliant)**
4. **agent_llm**: Mean Net ₹17,950.51 | 20.7% Gross | Regret ₹9,558.94 | **Violations: 0 (Fail-closed resilient)**
5. **message_only**: Mean Net ₹16,993.97 | 17.2% Gross | Regret ₹10,515.48 | Violations: 0
6. **always_retry**: Mean Net ₹5,016.53 | 13.2% Gross | Regret ₹22,492.92 | **Violations: 16 (Heavy penalty impact)**
7. **no_action**: Mean Net ₹0.00 | 0.0% Gross | Regret ₹27,509.45 | Violations: 0
