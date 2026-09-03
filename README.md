# Failed Subscription Recovery Agent — Razorpay Buildathon Track 3

Measured net recovery on a 40-record batch of failed Indian recurring
payments, evaluated against 6 baselines and a hidden oracle across 200
seeded draws.

## Headline results

| | |
|---|---|
| Revenue at risk | ₹98,952 |
| Agent net recovered (mean, 200 seeds) | **₹21,677** |
| Gross recovery rate | 23.3% |
| Compliance violations | **0** |
| Oracle upper bound | ₹27,509 |
| Naive always-retry | ₹5,017 |

All recovery outcomes are **simulated** under an explicit probability
model (`outcome_model.py`). No live merchant money was recovered. The
model is calibrated so that naive retry strategies land in the 13–17%
band reported for basic retry rules in industry sources.

## The finding: compliance has a price, and I derived it

The non-compliant legacy rulebook (`naive_rules`) recovers **more** money
than the compliant agent when an RBI violation is priced at ₹500 —
₹24,154 versus ₹21,677 — because it pays 6 violations and still comes out
ahead.

The exact break-even is **₹912.84 per violation.** Below that price,
non-compliance is economically rational. At or above it, the agent wins.

| Penalty | Best deployable strategy |
|---|---|
| ₹0 – ₹500 | naive_rules |
| ₹913+ | **agent_rules** |

Two consequences worth stating plainly:

1. **The compliant strategies are penalty-invariant.** `agent_rules`
   returns ₹21,677.28 whether a violation costs ₹0 or ₹5,000, because it
   never incurs one. Regulatory risk exposure is zero, not small.
2. **Always-retry is value-destroying, not merely weak.** It falls from
   ₹13,017 to **negative ₹66,983** across the same range — destroying
   two-thirds of the merchant's book on a ₹98,952 exposure.

I do not claim ₹500 is the right price. I claim that a merchant must
decide what an unauthorised debit attempt costs them, and that ₹913 is
where that decision flips.

## Full benchmark — 7 strategies, 200 paired seeds

See `benchmark_results.md`. Reproduce with `python pipeline.py --benchmark`
— **no API key required**, decisions replay from `llm_decision_cache.json`.

## Does the LLM earn its place? Measured, not assumed

`agent_llm` composition: 31 live Gemini decisions / 0 cache misses /
7 resolved by deterministic guard before any model call.

Paired difference versus `agent_rules`: **-₹418.05 ± ₹587.10** across 200 seeds.

The model is statistically indistinguishable from the rule engine on net recovery (-₹418.05 on ₹21,677, p > 0.05). It does not produce magic lift; it produces behavioral change — shifting actions from aggressive automatic retries (4 vs 8) to customer communications (25 vs 14), preserving zero compliance violations with a gentler customer touchpoint.

22% of records never reach the model at all: retry-exhaustion and
reconciliation guards resolve them deterministically at zero inference
cost. The model is consulted where failure context is genuinely
ambiguous, not as a router for cases an `if` statement decides.

## How it works

Batch → Pydantic validation → four deterministic guards → decision
(Gemini structured output, or rules) → independent outcome model →
audit ledger + financial counters.

**The outcome model cannot see the decision engine, and vice versa.**
Recovery probability is a property of `(failure_reason, action, seed)`,
never of the action label alone. This is what makes the agent's choice
scoreable rather than self-fulfilling — an earlier version derived
payout from the chosen action, which meant "always retry" would have
scored highest by construction.

## Four safety guards

1. **Retry exhaustion** — per-method caps (`upi: 3`, `card: 4`), not a
   flat number, reflecting differing network retry limits.
2. **Reconciliation** — `payment_state` of `unknown` or
   `possibly_debited` forces escalation. Retrying a payment that may
   already have debited risks a double charge; this runs *before* the
   model.
3. **Fail-closed** — if the model is unavailable, the fallback may never
   emit a money-moving action. An outage cannot trigger a debit.
4. **Low-confidence escalation** — below threshold, route to a human.

## The 9 India-specific failure reasons

`upi_pin_failure` · `insufficient_funds` · `card_expired` ·
`mandate_not_registered` · `mandate_lapsed_on_reissue` ·
`afa_required_not_completed` (RBI AFA above ₹15,000) ·
`pre_debit_notice_not_acked` (RBI 24-hour notice) · `gateway_timeout` ·
`issuer_declined`

Retrying an unacknowledged pre-debit notice is a regulatory violation,
not merely an ineffective action. The outcome model prices it as one.

## Run it

```bash
pip install -r requirements.txt
python pipeline.py --benchmark              # full evaluation, no API key
python pipeline.py --sweep-penalty          # sensitivity analysis
pytest tests/                               # 6 guard + determinism tests
python pipeline.py --demo-retry-exhaustion
python pipeline.py --demo-out-of-scope
python pipeline.py --demo-low-confidence
```

## What broke and how I fixed it

**The metric was circular.** The first version computed recovery as
`amount × rate[chosen_action]`. Since the agent picked the action, it
could not be wrong, and "always return retry_now" would have scored
highest. The reported 35.5% recovery rate measured nothing. Rebuilt as
an independent outcome model keyed on `(failure_reason, action, seed)`.
The honest number came out at 23.3%.

**The LLM path was measuring its own fallback.** Free-tier quota
exhausted mid-batch; 11 of 31 records silently fell through to rules,
and the "LLM" benchmark row was 53% not-the-LLM. Fixed with a persistent
decision cache, exponential backoff, and a composition line printed on
every run. The cache is committed so the benchmark is reproducible
without a key.

**Rules were labelled as model calls.** Seven records intercepted by the
retry-exhaustion guard printed "Calling Gemini API" before the guard ran.
No call was made. Moved the log after the guards.

**Retrying an unacknowledged pre-debit notice.** The original rulebook
mapped `pre_debit_notice_not_acked` to `retry_now`, bundled with
`gateway_timeout`. That is an RBI violation. Split out and routed to
`resend_pre_debit_notice`.

## Limitations

- All outcomes simulated; probabilities are stated assumptions in
  `outcome_model.py`, calibrated against published industry retry
  recovery rates, not fitted to merchant history.
- 40 records. Wide per-seed variance (₹3,175–₹46,658) — comparisons use
  paired per-seed differences with standard errors, not raw ranges.
- Batch, not a live webhook listener. Deliberate: measurement and safety
  first. Production step is a FastAPI receiver for `payment.failed` and
  `subscription.halted`.
- No live dispatch to WhatsApp/SMS.
- Audit ledger is in-memory.
