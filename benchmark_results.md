# Benchmark Results – Recovery Agent Multi-Strategy Evaluation

**Timestamp:** 2026-09-04 21:32:45 | **Batch Size:** 40 records | **Seeds:** 200 | **Total at Risk:** ₹98,952.00 | **Penalty:** ₹500

`agent_llm composition: 31 live LLM / 0 rule fallback (cache miss) / 7 deterministic guard`

| Rank | Strategy | Mean Net (₹) | Paired Diff vs agent_rules (₹) | Net Range (₹) | Gross Recov % | Decision Match % | Regret vs Oracle (₹) | Violations | Retries | Contacts | Escalations |
|:---:|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | **oracle** | ₹27,509.45 | ₹+5,687.16 ± ₹610.51 | ₹5,363.00 – ₹54,238.00 | 29.6% | 100.0% | ₹0.00 | 1 | 8 | 22 | 8 |
| 2 | **naive_rules** | ₹24,154.31 | ₹+2,332.03 ± ₹591.84 | ₹2,912.00 – ₹51,306.00 | 28.7% | 78.9% | ₹3,355.14 | 6 | 14 | 16 | 8 |
| 3 | **agent_rules** | ₹21,822.29 | — (Baseline) | ₹2,872.50 – ₹46,654.50 | 23.1% | 73.7% | ₹5,687.16 | 0 | 8 | 16 | 7 |
| 4 | **agent_llm** | ₹21,537.24 | ₹-285.05 ± ₹570.06 | ₹4,721.50 – ₹46,999.50 | 22.2% | 60.5% | ₹5,972.21 | 0 | 4 | 24 | 3 |
| 5 | **message_only** | ₹16,993.97 | ₹-4,828.32 ± ₹646.30 | ₹2,317.00 – ₹38,301.00 | 17.2% | 52.6% | ₹10,515.48 | 0 | 0 | 38 | 0 |
| 6 | **always_retry** | ₹5,016.53 | ₹-16,805.76 ± ₹599.05 | ₹-8,038.00 – ₹23,652.00 | 13.2% | 21.1% | ₹22,492.92 | 16 | 38 | 0 | 0 |
| 7 | **no_action** | ₹0.00 | ₹-21,822.29 ± ₹556.47 | ₹0.00 – ₹0.00 | 0.0% | 0.0% | ₹27,509.45 | 0 | 0 | 0 | 0 |


## Compliance Penalty Sensitivity

### The Compliance Pricing Curve

- **₹62.08** — The cheapest violation stops paying (`pay_Ex66fGhIjKlM65`, ₹899, insufficient_funds). Below this, no violation is deterred.
- **₹888.67** — The compliant agent (`agent_rules`) overtakes the non-compliant rulebook (`naive_rules`). Efficiency shrinks the performance gap so the crossing arrives earlier.
- **₹1,351.22** — An unconstrained profit-maximiser abandons violation entirely (`pay_Ex11kLmNoPqR10`, ₹9,999, gateway_timeout at retry cap). Above this, nothing pays.

*Note: All three thresholds are derived programmatically from this 40-record batch and are batch-specific, not general constants.*

| Penalty (₹) | **no_action** | **always_retry** | **message_only** | **naive_rules** | **agent_rules** | **agent_llm** | **oracle** | Best Deployable Strategy |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| ₹0 | ₹0.00 | ₹13,016.53 | ₹16,993.97 | ₹27,154.31 | ₹21,822.29 | ₹21,537.24 | ₹28,159.94 | **naive_rules** |
| ₹250 | ₹0.00 | ₹9,016.53 | ₹16,993.97 | ₹25,654.31 | ₹21,822.29 | ₹21,537.24 | ₹27,759.45 | **naive_rules** |
| ₹500 | ₹0.00 | ₹5,016.53 | ₹16,993.97 | ₹24,154.31 | ₹21,822.29 | ₹21,537.24 | ₹27,509.45 | **naive_rules** |
| ₹889 | ₹0.00 | ₹-1,207.46 | ₹16,993.97 | ₹21,820.31 | ₹21,822.29 | ₹21,537.24 | ₹27,120.45 | **agent_rules** |
| ₹1,500 | ₹0.00 | ₹-10,983.47 | ₹16,993.97 | ₹18,154.31 | ₹21,822.29 | ₹21,537.24 | ₹26,110.62 | **agent_rules** |
| ₹3,000 | ₹0.00 | ₹-34,983.46 | ₹16,993.97 | ₹9,154.32 | ₹21,822.29 | ₹21,537.24 | ₹26,110.62 | **agent_rules** |
| ₹5,000 | ₹0.00 | ₹-66,983.46 | ₹16,993.97 | ₹-2,845.68 | ₹21,822.29 | ₹21,537.24 | ₹26,110.62 | **agent_rules** |

*Note: Oracle represents the theoretical upper bound reading the hidden recovery matrix directly and is excluded from 'Best Deployable Strategy'.*
