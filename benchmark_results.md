# Benchmark Results – Recovery Agent Multi-Strategy Evaluation

**Timestamp:** 2026-09-04 16:55:41 | **Batch Size:** 40 records | **Seeds:** 200 | **Total at Risk:** ₹98,952.00 | **Penalty:** ₹500

`agent_llm composition: 31 live LLM / 0 rule fallback (cache miss) / 7 deterministic guard`

| Rank | Strategy | Mean Net (₹) | Paired Diff vs agent_rules (₹) | Net Range (₹) | Gross Recov % | Decision Match % | Regret vs Oracle (₹) | Violations | Retries | Contacts | Escalations |
|:---:|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | **oracle** | ₹27,509.45 | ₹+5,832.16 ± ₹611.09 | ₹5,363.00 – ₹54,238.00 | 29.6% | 100.0% | ₹0.00 | 1 | 8 | 22 | 8 |
| 2 | **naive_rules** | ₹24,154.31 | ₹+2,477.03 ± ₹593.10 | ₹2,912.00 – ₹51,306.00 | 28.7% | 78.9% | ₹3,355.14 | 6 | 14 | 16 | 8 |
| 3 | **agent_rules** | ₹21,677.28 | — (Baseline) | ₹3,174.50 – ₹46,657.50 | 23.3% | 68.4% | ₹5,832.16 | 0 | 8 | 14 | 9 |
| 4 | **agent_llm** | ₹21,259.24 | ₹-418.05 ± ₹587.10 | ₹4,871.00 – ₹47,149.00 | 21.8% | 57.9% | ₹6,250.21 | 0 | 4 | 25 | 2 |
| 5 | **message_only** | ₹16,993.97 | ₹-4,683.31 ± ₹645.06 | ₹2,317.00 – ₹38,301.00 | 17.2% | 52.6% | ₹10,515.48 | 0 | 0 | 38 | 0 |
| 6 | **always_retry** | ₹5,016.53 | ₹-16,660.75 ± ₹598.76 | ₹-8,038.00 – ₹23,652.00 | 13.2% | 21.1% | ₹22,492.92 | 16 | 38 | 0 | 0 |
| 7 | **no_action** | ₹0.00 | ₹-21,677.28 ± ₹554.08 | ₹0.00 – ₹0.00 | 0.0% | 0.0% | ₹27,509.45 | 0 | 0 | 0 | 0 |


## Compliance Penalty Sensitivity

**Exact Break-Even Penalty:** ₹912.84 per violation (agent_rules overtakes naive_rules)

| Penalty (₹) | **no_action** | **always_retry** | **message_only** | **naive_rules** | **agent_rules** | **agent_llm** | **oracle** | Best Deployable Strategy |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| ₹0 | ₹0.00 | ₹13,016.53 | ₹16,993.97 | ₹27,154.31 | ₹21,677.28 | ₹21,259.24 | ₹28,159.94 | **naive_rules** |
| ₹250 | ₹0.00 | ₹9,016.53 | ₹16,993.97 | ₹25,654.31 | ₹21,677.28 | ₹21,259.24 | ₹27,759.45 | **naive_rules** |
| ₹500 | ₹0.00 | ₹5,016.53 | ₹16,993.97 | ₹24,154.31 | ₹21,677.28 | ₹21,259.24 | ₹27,509.45 | **naive_rules** |
| ₹913 | ₹0.00 | ₹-1,591.46 | ₹16,993.97 | ₹21,676.31 | ₹21,677.28 | ₹21,259.24 | ₹27,096.45 | **agent_rules** |
| ₹1,500 | ₹0.00 | ₹-10,983.47 | ₹16,993.97 | ₹18,154.31 | ₹21,677.28 | ₹21,259.24 | ₹26,110.62 | **agent_rules** |
| ₹3,000 | ₹0.00 | ₹-34,983.46 | ₹16,993.97 | ₹9,154.32 | ₹21,677.28 | ₹21,259.24 | ₹26,110.62 | **agent_rules** |
| ₹5,000 | ₹0.00 | ₹-66,983.46 | ₹16,993.97 | ₹-2,845.68 | ₹21,677.28 | ₹21,259.24 | ₹26,110.62 | **agent_rules** |

*Note: Oracle represents the theoretical upper bound reading the hidden recovery matrix directly and is excluded from 'Best Deployable Strategy'.*
