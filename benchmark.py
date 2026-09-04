import math
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Tuple
from pydantic import BaseModel

from models import FailedPayment, InterventionDecision
from outcome_model import (
    simulate_outcome,
    OutcomeResult,
    VIOLATION_PENALTY_PAISE,
)
from strategies import (
    STRATEGIES,
    strategy_oracle,
    LLM_CACHE,
    populate_llm_cache,
)
from data.sample_batch import BATCH
from pipeline import get_retry_cap, VALID_FAILURE_REASONS, DEDUPE_TTL_HOURS, POLICY_VERSION
from report_generator import generate_benchmark_html


class StrategyBenchmarkStats(BaseModel):
    strategy_name: str
    mean_gross_paise: float
    mean_cost_paise: float
    mean_penalty_paise: float
    mean_net_paise: float
    min_net_paise: float
    max_net_paise: float
    paired_diff_mean_paise: float
    paired_diff_se_paise: float
    gross_recovery_rate_pct: float
    contacts_sent: int
    retries_made: int
    violations: int
    escalations: int
    duplicates_suppressed: int
    decision_match_rate_pct: float
    regret_paise: float


def run_benchmark(
    batch: List[dict] = BATCH,
    n_seeds: int = 200,
    penalty_paise: int = VIOLATION_PENALTY_PAISE,
    save_markdown: bool = True,
    refresh_llm_cache: bool = False,
    verbose: bool = True,
    include_sweep: bool = True,
    html_report_path: Optional[str] = "benchmark_report.html",
) -> Tuple[List[StrategyBenchmarkStats], str]:
    """
    Executes multi-strategy benchmark across 7 strategies over n_seeds (default 200)
    with paired statistics against agent_rules. Strictly cache-only for agent_llm.
    """
    valid_records: List[FailedPayment] = []
    out_of_scope_records: List[Tuple[str, int, str]] = []

    for row in batch:
        record_id = row.get("id") if isinstance(row, dict) else getattr(row, "id", "unknown")
        raw_reason = row.get("failure_reason") if isinstance(row, dict) else getattr(row, "failure_reason", "")
        amount_paise = row.get("amount_paise", 0) if isinstance(row, dict) else getattr(row, "amount_paise", 0)

        if raw_reason not in VALID_FAILURE_REASONS:
            out_of_scope_records.append((record_id, amount_paise, raw_reason))
        else:
            payment = FailedPayment(**row) if isinstance(row, dict) else row
            valid_records.append(payment)

    total_at_risk_paise = sum(
        (r.get("amount_paise", 0) if isinstance(r, dict) else r.amount_paise) for r in batch
    )

    # Step 1: Pre-compute decisions ONCE per strategy (Strictly cache-only for LLM)
    strategy_decisions: Dict[str, Dict[str, InterventionDecision]] = {}

    for strat_name, strat_fn in STRATEGIES.items():
        decisions: Dict[str, InterventionDecision] = {}
        for rec in valid_records:
            if strat_name == "oracle":
                decisions[rec.id] = strategy_oracle(rec, penalty_paise=penalty_paise)
            else:
                decisions[rec.id] = strat_fn(rec)
        strategy_decisions[strat_name] = decisions

    # Compute agent_llm composition breakdown
    z_guard = 0
    x_live = 0
    y_fallback = 0

    for rec in valid_records:
        retry_cap = get_retry_cap(rec.payment_method)
        is_guard = (getattr(rec, "payment_state", "confirmed_failed") != "confirmed_failed" or
                    rec.attempt_count >= retry_cap)
        if is_guard:
            z_guard += 1
        elif rec.id in LLM_CACHE and not strategy_decisions["agent_llm"][rec.id].degraded_mode:
            x_live += 1
        else:
            y_fallback += 1

    composition_line = f"agent_llm composition: {x_live} live LLM / {y_fallback} rule fallback (cache miss) / {z_guard} deterministic guard"
    if verbose:
        print("\n" + composition_line)

    oracle_decisions = strategy_decisions["oracle"]

    # Step 2: Simulate outcomes across all seeds
    net_per_seed_by_strat: Dict[str, List[float]] = {name: [] for name in STRATEGIES}
    runs_by_strategy: Dict[str, List[Dict[str, Any]]] = {name: [] for name in STRATEGIES}

    for seed in range(n_seeds):
        for strat_name, decisions in strategy_decisions.items():
            gross_paise = 0
            cost_paise = 0
            penalty_total_paise = 0
            contacts = 0
            retries = 0
            violations = 0
            escalations = 0

            for rec in valid_records:
                dec = decisions[rec.id]
                action = dec.chosen_action

                if dec.escalate or action == "escalate_to_human":
                    escalations += 1

                retry_cap = get_retry_cap(rec.payment_method)
                outcome: OutcomeResult = simulate_outcome(
                    rec,
                    action,
                    seed=seed,
                    retry_cap=retry_cap,
                    penalty_amount_paise=penalty_paise,
                )

                gross_paise += outcome.recovered_paise
                cost_paise += outcome.cost_paise
                penalty_total_paise += outcome.penalty_paise

                if outcome.contacted:
                    contacts += 1
                if outcome.retried:
                    retries += 1
                if outcome.violation:
                    violations += 1

            net_paise = gross_paise - cost_paise - penalty_total_paise
            net_per_seed_by_strat[strat_name].append(net_paise)
            runs_by_strategy[strat_name].append({
                "gross_paise": gross_paise,
                "cost_paise": cost_paise,
                "penalty_paise": penalty_total_paise,
                "net_paise": net_paise,
                "contacts": contacts,
                "retries": retries,
                "violations": violations,
                "escalations": escalations,
            })

    # Step 3: Compute Paired Differences vs agent_rules
    agent_rules_nets = net_per_seed_by_strat["agent_rules"]
    oracle_mean_net = sum(net_per_seed_by_strat["oracle"]) / n_seeds

    benchmark_stats: List[StrategyBenchmarkStats] = []

    for strat_name, run_list in runs_by_strategy.items():
        strat_nets = net_per_seed_by_strat[strat_name]
        mean_gross = sum(r["gross_paise"] for r in run_list) / n_seeds
        mean_cost = sum(r["cost_paise"] for r in run_list) / n_seeds
        mean_penalty = sum(r["penalty_paise"] for r in run_list) / n_seeds
        mean_net = sum(strat_nets) / n_seeds
        min_net = min(strat_nets)
        max_net = max(strat_nets)

        # Paired difference vs agent_rules
        diffs = [s - a for s, a in zip(strat_nets, agent_rules_nets)]
        mean_diff = sum(diffs) / n_seeds
        variance_diff = sum((d - mean_diff) ** 2 for d in diffs) / max(1, (n_seeds - 1))
        std_diff = math.sqrt(variance_diff)
        se_diff = std_diff / math.sqrt(n_seeds)

        gross_rate_pct = (mean_gross / total_at_risk_paise * 100) if total_at_risk_paise > 0 else 0.0

        decisions = strategy_decisions[strat_name]
        contacts_sent = sum(1 for rec in valid_records if decisions[rec.id].chosen_action in [
            "send_upi_pin_nudge", "send_card_update_link", "request_mandate_reissue", "resend_pre_debit_notice"
        ])
        retries_made = sum(1 for rec in valid_records if decisions[rec.id].chosen_action == "retry_now")
        escalations_count = sum(1 for rec in valid_records if decisions[rec.id].escalate or decisions[rec.id].chosen_action == "escalate_to_human")
        
        violations_count = sum(1 for rec in valid_records if simulate_outcome(
            rec, decisions[rec.id].chosen_action, seed=0, retry_cap=get_retry_cap(rec.payment_method)
        ).violation)

        matches = sum(1 for rec in valid_records if decisions[rec.id].chosen_action == oracle_decisions[rec.id].chosen_action)
        decision_match_rate_pct = (matches / len(valid_records) * 100) if valid_records else 0.0
        regret_paise = max(0.0, oracle_mean_net - mean_net)

        stat = StrategyBenchmarkStats(
            strategy_name=strat_name,
            mean_gross_paise=mean_gross,
            mean_cost_paise=mean_cost,
            mean_penalty_paise=mean_penalty,
            mean_net_paise=mean_net,
            min_net_paise=min_net,
            max_net_paise=max_net,
            paired_diff_mean_paise=mean_diff,
            paired_diff_se_paise=se_diff,
            gross_recovery_rate_pct=gross_rate_pct,
            contacts_sent=contacts_sent,
            retries_made=retries_made,
            violations=violations_count,
            escalations=escalations_count,
            duplicates_suppressed=0,
            decision_match_rate_pct=decision_match_rate_pct,
            regret_paise=regret_paise,
        )
        benchmark_stats.append(stat)

    # Sort by Mean Net Paise descending
    benchmark_stats.sort(key=lambda s: s.mean_net_paise, reverse=True)

    # Step 4: Render Markdown Table
    timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    md_lines = [
        f"# Benchmark Results – Recovery Agent Multi-Strategy Evaluation",
        f"\n**Timestamp:** {timestamp_str} | **Batch Size:** {len(batch)} records | **Seeds:** {n_seeds} | **Total at Risk:** ₹{total_at_risk_paise/100:,.2f} | **Penalty:** ₹{penalty_paise/100:,.0f}",
        f"\n`{composition_line}`\n",
        "| Rank | Strategy | Mean Net (₹) | Paired Diff vs agent_rules (₹) | Net Range (₹) | Gross Recov % | Decision Match % | Regret vs Oracle (₹) | Violations | Retries | Contacts | Escalations |",
        "|:---:|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|",
    ]

    for rank, s in enumerate(benchmark_stats, 1):
        diff_str = f"₹{s.paired_diff_mean_paise/100:+,.2f} ± ₹{s.paired_diff_se_paise/100:,.2f}" if s.strategy_name != "agent_rules" else "— (Baseline)"
        md_lines.append(
            f"| {rank} | **{s.strategy_name}** | ₹{s.mean_net_paise/100:,.2f} | {diff_str} | ₹{s.min_net_paise/100:,.2f} – ₹{s.max_net_paise/100:,.2f} | {s.gross_recovery_rate_pct:.1f}% | {s.decision_match_rate_pct:.1f}% | ₹{s.regret_paise/100:,.2f} | {s.violations} | {s.retries_made} | {s.contacts_sent} | {s.escalations} |"
        )

    md_table = "\n".join(md_lines)
    if verbose:
        print("\n" + md_table + "\n")

    full_output = md_table

    if save_markdown:
        out_path = Path(__file__).parent / "benchmark_results.md"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md_table + "\n")

        if include_sweep:
            sweep_md, sweep_results, breakeven_penalty_inr = run_penalty_sweep(
                batch=batch, n_seeds=n_seeds, save_to_file=True, verbose=verbose, return_details=True
            )
            full_output += "\n\n" + sweep_md

            if html_report_path:
                metadata = {
                    "batch_size": len(batch),
                    "seeds": n_seeds,
                    "total_at_risk_paise": total_at_risk_paise,
                    "penalty_paise": penalty_paise,
                    "composition_line": composition_line,
                    "policy_version": POLICY_VERSION,
                    "timestamp": timestamp_str,
                }
                html_content = generate_benchmark_html(
                    benchmark_stats=benchmark_stats,
                    sweep_results=sweep_results,
                    breakeven_penalty_inr=breakeven_penalty_inr,
                    metadata=metadata,
                )
                html_path = Path(html_report_path)
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                if verbose:
                    print(f"Benchmark HTML report successfully saved to: {html_path}")

        if verbose:
            print(f"Benchmark results successfully saved to: {out_path}")

    return benchmark_stats, full_output


def run_penalty_sweep(
    batch: List[dict] = BATCH,
    n_seeds: int = 200,
    penalties_inr: List[int] = [0, 250, 500, 913, 1500, 3000, 5000],
    save_to_file: bool = True,
    verbose: bool = True,
    return_details: bool = False,
) -> Any:
    """
    Evaluates all 7 strategies across varying regulatory violation penalty levels
    and dynamically derives the break-even penalty where agent_rules overtakes naive_rules.
    """
    if verbose:
        print(f"\n==================================================================")
        print(f"      COMPLIANCE PENALTY SENSITIVITY SWEEP (Seeds={n_seeds})")
        print(f"==================================================================\n")

    sweep_results: Dict[int, Dict[str, float]] = {}
    strategy_names = list(STRATEGIES.keys())

    for p_inr in penalties_inr:
        penalty_paise = p_inr * 100
        stats, _ = run_benchmark(
            batch=batch,
            n_seeds=n_seeds,
            penalty_paise=penalty_paise,
            save_markdown=False,
            verbose=False,
            include_sweep=False,
        )
        sweep_results[p_inr] = {s.strategy_name: s.mean_net_paise / 100 for s in stats}

    # Derive Break-Even Penalty analytically
    stats_zero, _ = run_benchmark(
        batch=batch, n_seeds=n_seeds, penalty_paise=0, save_markdown=False, verbose=False, include_sweep=False
    )
    stat_dict = {s.strategy_name: s for s in stats_zero}
    agent_stat = stat_dict["agent_rules"]
    naive_stat = stat_dict["naive_rules"]

    gross_cost_agent = (agent_stat.mean_gross_paise - agent_stat.mean_cost_paise) / 100
    gross_cost_naive = (naive_stat.mean_gross_paise - naive_stat.mean_cost_paise) / 100
    v_agent = agent_stat.violations
    v_naive = naive_stat.violations

    delta_v = v_naive - v_agent
    if delta_v > 0:
        breakeven_penalty_inr = (gross_cost_naive - gross_cost_agent) / delta_v
    else:
        breakeven_penalty_inr = 0.0

    if verbose:
        print(f"Exact Break-Even Penalty: ₹{breakeven_penalty_inr:,.2f}")
        print(f"(At penalties >= ₹{breakeven_penalty_inr:,.2f}, agent_rules outperforms naive_rules net of compliance risk)\n")

    # Render Markdown Table for Penalty Sweep (Oracle is reference only, not a deployable strategy)
    deployable_names = [name for name in strategy_names if name != "oracle"]
    header_cols = ["Penalty (₹)"] + [f"**{name}**" for name in strategy_names] + ["Best Deployable Strategy"]
    sweep_lines = [
        "## Compliance Penalty Sensitivity\n",
        f"**Exact Break-Even Penalty:** ₹{breakeven_penalty_inr:,.2f} per violation (agent_rules overtakes naive_rules)\n",
        "| " + " | ".join(header_cols) + " |",
        "| " + " | ".join([":---:"] * len(header_cols)) + " |",
    ]

    for p_inr in penalties_inr:
        row_vals = [f"₹{p_inr:,}"]
        best_deployable = ""
        best_val = -float("inf")
        for name in strategy_names:
            val = sweep_results[p_inr].get(name, 0.0)
            row_vals.append(f"₹{val:,.2f}")
            if name in deployable_names and val > best_val:
                best_val = val
                best_deployable = name
        row_vals.append(f"**{best_deployable}**")
        sweep_lines.append("| " + " | ".join(row_vals) + " |")

    sweep_lines.append("\n*Note: Oracle represents the theoretical upper bound reading the hidden recovery matrix directly and is excluded from 'Best Deployable Strategy'.*")

    sweep_table = "\n".join(sweep_lines)
    if verbose:
        print(sweep_table + "\n")

    # Append to benchmark_results.md if requested
    if save_to_file:
        out_path = Path(__file__).parent / "benchmark_results.md"
        if out_path.exists():
            with open(out_path, "a", encoding="utf-8") as f:
                f.write("\n\n" + sweep_table + "\n")

    if return_details:
        return sweep_table, sweep_results, breakeven_penalty_inr
    return sweep_table


if __name__ == "__main__":
    run_benchmark(BATCH, n_seeds=200)
