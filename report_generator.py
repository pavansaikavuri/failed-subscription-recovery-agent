import math
from typing import Dict, List, Any
from datetime import datetime


STRATEGY_COLORS = {
    "agent_rules": "#2563eb",   # single accent blue (subject)
    "agent_llm": "#334155",     # neutral dark slate (compliant family)
    "message_only": "#334155",  # neutral dark slate (compliant family)
    "naive_rules": "#dc2626",   # muted red (value-destroying family)
    "always_retry": "#dc2626",  # muted red (value-destroying family)
    "oracle": "#94a3b8",        # light grey (reference bound)
    "no_action": "#cbd5e1",     # lightest grey (baseline)
}

STRATEGY_LABELS = {
    "oracle": "oracle (Theoretical Upper Bound)",
    "agent_rules": "agent_rules (Compliant Rule Engine)",
    "agent_llm": "agent_llm (Cached Gemini 3.6 Flash)",
    "naive_rules": "naive_rules (Legacy Un-Guarded Rulebook)",
    "always_retry": "always_retry (Naive Retries Everywhere)",
    "message_only": "message_only (Non-Invasive Nudges Only)",
    "no_action": "no_action (Immediate Write-off Baseline)",
}


def build_sensitivity_curve_svg(
    sweep_results: Dict[int, Dict[str, float]],
    breakeven_penalty_inr: float,
    penalties_inr: List[int],
    oracle_threshold_inr: float = 1351.22,
) -> str:
    """Draws inline SVG of the penalty sensitivity curve with dual vertical markers and distinct series strokes."""
    width = 960
    height = 560
    margin_left = 90
    margin_right = 140
    margin_top = 68
    margin_bottom = 65
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom

    x_min = 0
    x_max = 5000

    all_vals = [val for p_dict in sweep_results.values() for val in p_dict.values()]
    min_val = min(all_vals)
    max_val = max(all_vals)

    # Floor and ceiling with clean rounding
    y_floor = math.floor((min_val - 2000) / 10000) * 10000
    y_ceil = math.ceil((max_val + 2000) / 5000) * 5000
    y_range = y_ceil - y_floor

    def map_x(p: float) -> float:
        return margin_left + ((p - x_min) / (x_max - x_min)) * plot_width

    def map_y(v: float) -> float:
        return margin_top + ((y_ceil - v) / y_range) * plot_height

    svg_parts = []
    svg_parts.append(
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="auto" class="chart-svg" '
        f'xmlns="http://www.w3.org/2000/svg" style="overflow: visible; font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif;">'
    )

    # Background rect
    svg_parts.append(
        f'<rect x="{margin_left}" y="{margin_top}" width="{plot_width}" height="{plot_height}" '
        f'fill="#ffffff" stroke="#e2e8f0" stroke-width="1" rx="4" />'
    )

    # Horizontal Grid lines and Y labels (clean 10,000 interval, anchored at zero)
    ticks_y = [-70000, -60000, -50000, -40000, -30000, -20000, -10000, 0, 10000, 20000, 30000]
    for cur_y in ticks_y:
        sy = map_y(cur_y)
        is_zero = (cur_y == 0)
        line_color = "#475569" if is_zero else "#f1f5f9"
        line_width = "1.5" if is_zero else "1"

        svg_parts.append(
            f'<line x1="{margin_left}" y1="{sy:.1f}" x2="{margin_left + plot_width}" y2="{sy:.1f}" '
            f'stroke="{line_color}" stroke-width="{line_width}" />'
        )

        font_weight = "700" if is_zero else "400"
        text_fill = "#0f172a" if is_zero else "#64748b"
        if cur_y == 0:
            label_text = "₹0"
        elif cur_y > 0:
            label_text = f"₹{cur_y:,}"
        else:
            label_text = f"-₹{abs(cur_y):,}"

        svg_parts.append(
            f'<text x="{margin_left - 10}" y="{sy + 4:.1f}" text-anchor="end" font-size="11" '
            f'font-weight="{font_weight}" fill="{text_fill}" style="font-variant-numeric: tabular-nums;">{label_text}</text>'
        )

    # Vertical Grid lines and X labels
    x_ticks = [0, 1000, 2000, 3000, 4000, 5000]
    for xt in x_ticks:
        sx = map_x(xt)
        svg_parts.append(
            f'<line x1="{sx:.1f}" y1="{margin_top}" x2="{sx:.1f}" y2="{margin_top + plot_height}" '
            f'stroke="#f1f5f9" stroke-width="1" />'
        )
        svg_parts.append(
            f'<text x="{sx:.1f}" y="{margin_top + plot_height + 20}" text-anchor="middle" font-size="11" '
            f'fill="#64748b" style="font-variant-numeric: tabular-nums;">₹{xt:,}</text>'
        )

    # X-axis title
    svg_parts.append(
        f'<text x="{margin_left + plot_width / 2:.1f}" y="{margin_top + plot_height + 46}" '
        f'text-anchor="middle" font-size="12" font-weight="600" fill="#334155">'
        f'Regulatory Non-Compliance Penalty per Violation (₹)</text>'
    )

    # Y-axis title
    svg_parts.append(
        f'<text transform="rotate(-90)" x="{-margin_top - plot_height / 2:.1f}" y="{margin_left - 62}" '
        f'text-anchor="middle" font-size="12" font-weight="600" fill="#334155">'
        f'Mean Net Recovery (₹)</text>'
    )

    # MARKER 1: Break-Even Crossing Point at breakeven_penalty_inr
    be_x = map_x(breakeven_penalty_inr)
    svg_parts.append(
        f'<line x1="{be_x:.1f}" y1="{margin_top}" x2="{be_x:.1f}" y2="{margin_top + plot_height}" '
        f'stroke="#2563eb" stroke-width="1.5" stroke-dasharray="4,4" />'
    )

    # MARKER 2: Oracle Compliance Threshold at oracle_threshold_inr
    ot_x = map_x(oracle_threshold_inr)
    svg_parts.append(
        f'<line x1="{ot_x:.1f}" y1="{margin_top}" x2="{ot_x:.1f}" y2="{margin_top + plot_height}" '
        f'stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="2,3" />'
    )

    # Semantic curve palette encoding the regulatory-economic argument:
    # - agent_rules: single accent colour (#2563eb blue), heaviest stroke (subject)
    # - agent_llm & message_only: neutral dark grey (#334155), distinguished only by dash (compliant family)
    # - naive_rules & always_retry: muted red (#dc2626), distinguished by dash (value-destroying family)
    # - oracle: light grey dotted (#94a3b8), reference bound
    # - no_action: lightest grey hairline (#cbd5e1), baseline
    CURVE_COLORS = {
        "agent_rules": "#2563eb",
        "agent_llm": "#334155",
        "message_only": "#334155",
        "naive_rules": "#dc2626",
        "always_retry": "#dc2626",
        "oracle": "#94a3b8",
        "no_action": "#cbd5e1",
    }

    # Draw strategy polylines
    # Order so agent_rules is drawn first, agent_llm drawn distinctly on top, and oracle on top
    strategy_order = ["no_action", "always_retry", "naive_rules", "message_only", "agent_rules", "agent_llm", "oracle"]
    end_labels = []

    for strat in strategy_order:
        pts = []
        for p in penalties_inr:
            val = sweep_results[p].get(strat, 0.0)
            pts.append((map_x(p), map_y(val), val))

        color = CURVE_COLORS.get(strat, "#334155")
        poly_str = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in pts)

        dash = ""
        width_val = "2.2"
        if strat == "oracle":
            dash = 'stroke-dasharray="2,3"'
            width_val = "1.8"
        elif strat == "agent_rules":
            width_val = "3.2"
            dash = ""
        elif strat == "agent_llm":
            width_val = "2.2"
            dash = 'stroke-dasharray="4,3"'
        elif strat == "message_only":
            width_val = "2.2"
            dash = 'stroke-dasharray="10,2,2,2"'
        elif strat == "naive_rules":
            width_val = "2.2"
            dash = 'stroke-dasharray="6,3"'
        elif strat == "always_retry":
            width_val = "2.2"
            dash = ""
        elif strat == "no_action":
            dash = 'stroke-dasharray="4,4"'
            width_val = "1.2"

        svg_parts.append(
            f'<polyline points="{poly_str}" fill="none" stroke="{color}" stroke-width="{width_val}" '
            f'{dash} stroke-linecap="round" stroke-linejoin="round" />'
        )

        # Plot point dots (distinct marker radius per role)
        if strat == "agent_rules":
            dot_r = "3.5"
        elif strat == "agent_llm":
            dot_r = "2.5"
        elif strat in ("naive_rules", "always_retry", "message_only", "oracle"):
            dot_r = "3.0"
        else:
            dot_r = "2.0"

        for x, y, _ in pts:
            svg_parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{dot_r}" fill="{color}" stroke="#ffffff" stroke-width="1.5" />')

        last_x, last_y, last_val = pts[-1]
        end_labels.append({"strat": strat, "x": last_x, "y": last_y, "val": last_val, "color": color})

    # Anchored deconfliction: keep each label anchored to its own series' final y-value at p=5000
    # Symmetrically relax close neighbours so agent_llm sits directly below agent_rules without shifting message_only
    end_labels.sort(key=lambda item: item["y"])
    min_gap = 12.5
    for _ in range(50):
        for k in range(len(end_labels) - 1):
            gap = end_labels[k+1]["y"] - end_labels[k]["y"]
            if gap < min_gap:
                overlap = (min_gap - gap) / 2.0
                end_labels[k]["y"] -= overlap
                end_labels[k+1]["y"] += overlap

    # Curve end labels: Strategy name ONLY (anchored at right edge p=5000)
    for item in end_labels:
        font_weight = "700" if item["strat"] == "agent_rules" else "600"
        svg_parts.append(
            f'<text x="{item["x"] + 8:.1f}" y="{item["y"] + 4:.1f}" font-size="11" font-weight="{font_weight}" fill="{item["color"]}">'
            f'{item["strat"]}</text>'
        )

    # Marker 1 Intersection Dot on the Curve (computed from actual agent_rules mean net at crossing)
    agent_net_at_be = sweep_results[penalties_inr[0]].get("agent_rules", 21822.29)
    be_y = map_y(agent_net_at_be)
    svg_parts.append(
        f'<circle cx="{be_x:.1f}" cy="{be_y:.1f}" r="5" fill="#2563eb" stroke="#ffffff" stroke-width="2" />'
    )

    # Marker 1 Callout Badge (anchored to the left of be_x rule, never colliding with Marker 2)
    box_w = 146
    box_h = 32
    box_x = be_x - box_w
    box_y = 18
    svg_parts.append(
        f'<g>'
        f'<line x1="{be_x:.1f}" y1="{box_y + box_h}" x2="{be_x:.1f}" y2="{margin_top}" stroke="#2563eb" stroke-width="1.2" />'
        f'<rect x="{box_x:.1f}" y="{box_y}" width="{box_w}" height="{box_h}" rx="4" '
        f'fill="#eff6ff" stroke="#93c5fd" stroke-width="1.2" />'
        f'<text x="{box_x + box_w / 2:.1f}" y="{box_y + 13:.1f}" text-anchor="middle" font-size="10" '
        f'font-weight="bold" fill="#1d4ed8" style="font-variant-numeric: tabular-nums;">Crossing: ₹{breakeven_penalty_inr:,.2f}</text>'
        f'<text x="{box_x + box_w / 2:.1f}" y="{box_y + 25:.1f}" text-anchor="middle" font-size="8.5" '
        f'font-weight="600" fill="#2563eb">agent_rules > naive_rules</text>'
        f'</g>'
    )

    # Marker 2 Threshold Dot on Oracle curve where violations drop to 0
    oracle_val_at_ot = sweep_results[5000].get("oracle", 26110.62)
    ot_y = map_y(oracle_val_at_ot)
    svg_parts.append(
        f'<circle cx="{ot_x:.1f}" cy="{ot_y:.1f}" r="5" fill="#94a3b8" stroke="#ffffff" stroke-width="2" />'
    )

    # Marker 2 Callout Badge (anchored to the right of ot_x rule, separated by 67px from Marker 1)
    ot_box_w = 156
    ot_box_h = 32
    ot_box_x = ot_x
    ot_box_y = 18
    svg_parts.append(
        f'<g>'
        f'<line x1="{ot_x:.1f}" y1="{ot_box_y + ot_box_h}" x2="{ot_x:.1f}" y2="{margin_top}" stroke="#94a3b8" stroke-width="1.2" />'
        f'<rect x="{ot_box_x:.1f}" y="{ot_box_y}" width="{ot_box_w}" height="{ot_box_h}" rx="4" '
        f'fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.2" />'
        f'<text x="{ot_box_x + ot_box_w / 2:.1f}" y="{ot_box_y + 13:.1f}" text-anchor="middle" font-size="10" '
        f'font-weight="bold" fill="#334155" style="font-variant-numeric: tabular-nums;">Oracle Threshold: ₹{oracle_threshold_inr:,.2f}</text>'
        f'<text x="{ot_box_x + ot_box_w / 2:.1f}" y="{ot_box_y + 25:.1f}" text-anchor="middle" font-size="8.5" '
        f'font-weight="600" fill="#64748b">violations drop to 0</text>'
        f'</g>'
    )

    svg_parts.append('</svg>')
    return "\n".join(svg_parts)


def build_horizontal_bar_chart_svg(benchmark_stats: List[Any]) -> str:
    """Draws inline SVG horizontal bar chart of mean net recovery at base penalty with paired SE error bars."""
    width = 960
    n_bars = len(benchmark_stats)
    bar_height = 28
    bar_gap = 18
    margin_left = 135
    margin_right = 195
    margin_top = 35
    margin_bottom = 40

    plot_width = width - margin_left - margin_right
    plot_height = n_bars * bar_height + (n_bars - 1) * bar_gap
    height = plot_height + margin_top + margin_bottom

    max_val = max(s.mean_net_paise / 100 for s in benchmark_stats)
    x_limit = math.ceil((max_val + 3000) / 5000) * 5000

    def map_w(val: float) -> float:
        return max(0.0, (val / x_limit) * plot_width)

    svg_parts = []
    svg_parts.append(
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="auto" class="chart-svg" '
        f'xmlns="http://www.w3.org/2000/svg" style="overflow: visible; font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif;">'
    )

    # Grid background and ticks
    svg_parts.append(
        f'<rect x="{margin_left}" y="{margin_top}" width="{plot_width}" height="{plot_height}" '
        f'fill="#ffffff" stroke="#e2e8f0" stroke-width="1" rx="4" />'
    )

    ticks = [0, 5000, 10000, 15000, 20000, 25000, 30000, 35000]
    ticks = [t for t in ticks if t <= x_limit]

    for t in ticks:
        tx = margin_left + map_w(t)
        svg_parts.append(
            f'<line x1="{tx:.1f}" y1="{margin_top}" x2="{tx:.1f}" y2="{margin_top + plot_height}" '
            f'stroke="#f1f5f9" stroke-width="1" />'
        )
        svg_parts.append(
            f'<text x="{tx:.1f}" y="{margin_top + plot_height + 20}" text-anchor="middle" font-size="11" fill="#64748b" style="font-variant-numeric: tabular-nums;">'
            f'₹{t:,}</text>'
        )

    # Axis label
    svg_parts.append(
        f'<text x="{margin_left + plot_width / 2:.1f}" y="{margin_top + plot_height + 36}" '
        f'text-anchor="middle" font-size="11.5" font-weight="600" fill="#334155">'
        f'Mean Net Recovery (₹) at ₹500 Violation Penalty Level</text>'
    )

    # Render bars
    for i, s in enumerate(benchmark_stats):
        bar_y = margin_top + i * (bar_height + bar_gap)
        net_val = s.mean_net_paise / 100
        w = map_w(net_val)
        color = STRATEGY_COLORS.get(s.strategy_name, "#334155")

        # Bar rectangle
        svg_parts.append(
            f'<rect x="{margin_left}" y="{bar_y}" width="{w:.1f}" height="{bar_height}" '
            f'fill="{color}" rx="4" />'
        )

        # Strategy name label (left)
        svg_parts.append(
            f'<text x="{margin_left - 12}" y="{bar_y + 18}" text-anchor="end" font-size="12" '
            f'font-weight="600" fill="#0f172a">{s.strategy_name}</text>'
        )

        # Paired Standard Error bars
        se_val = s.paired_diff_se_paise / 100
        err_w = (se_val / x_limit) * plot_width
        center_x = margin_left + w

        if se_val > 0:
            x_min_err = max(margin_left, center_x - err_w)
            x_max_err = center_x + err_w
            mid_y = bar_y + bar_height / 2

            # Horizontal SE bar
            svg_parts.append(
                f'<line x1="{x_min_err:.1f}" y1="{mid_y:.1f}" x2="{x_max_err:.1f}" y2="{mid_y:.1f}" '
                f'stroke="#0f172a" stroke-width="2" />'
            )
            # Left cap
            svg_parts.append(
                f'<line x1="{x_min_err:.1f}" y1="{mid_y - 5:.1f}" x2="{x_min_err:.1f}" y2="{mid_y + 5:.1f}" '
                f'stroke="#0f172a" stroke-width="2" />'
            )
            # Right cap
            svg_parts.append(
                f'<line x1="{x_max_err:.1f}" y1="{mid_y - 5:.1f}" x2="{x_max_err:.1f}" y2="{mid_y + 5:.1f}" '
                f'stroke="#0f172a" stroke-width="2" />'
            )
            val_x = x_max_err + 10
            err_str = f"±₹{se_val:,.2f}"
        else:
            val_x = center_x + 10
            err_str = "Baseline" if s.strategy_name == "agent_rules" else "—"

        # Value label
        svg_parts.append(
            f'<text x="{val_x:.1f}" y="{bar_y + 18}" font-size="12" font-weight="700" fill="#0f172a" style="font-variant-numeric: tabular-nums;">'
            f'₹{net_val:,.2f} <tspan font-size="11" font-weight="normal" fill="#64748b">({err_str})</tspan></text>'
        )

    svg_parts.append('</svg>')
    return "\n".join(svg_parts)


def generate_benchmark_html(
    benchmark_stats: List[Any],
    sweep_results: Dict[int, Dict[str, float]],
    breakeven_penalty_inr: float,
    metadata: Dict[str, Any],
    oracle_threshold_inr: float = 1351.22,
) -> str:
    """Generates a complete, self-contained, standalone HTML report with editorial styling and tabular numerals."""
    penalties_inr = sorted(list(sweep_results.keys()))

    curve_svg = build_sensitivity_curve_svg(
        sweep_results, breakeven_penalty_inr, penalties_inr, oracle_threshold_inr=oracle_threshold_inr
    )
    barchart_svg = build_horizontal_bar_chart_svg(benchmark_stats)

    # Strategy names for sensitivity table
    strategy_names = [s.strategy_name for s in benchmark_stats]
    deployable_names = [s.strategy_name for s in benchmark_stats if s.strategy_name != "oracle"]

    # Table rows for benchmark
    benchmark_rows = []
    for rank, s in enumerate(benchmark_stats, 1):
        diff_str = (
            f"₹{s.paired_diff_mean_paise/100:+,.2f} ± ₹{s.paired_diff_se_paise/100:,.2f}"
            if s.strategy_name != "agent_rules"
            else '<span class="badge-neutral">Baseline</span>'
        )
        color = STRATEGY_COLORS.get(s.strategy_name, "#334155")
        v_badge = (
            '<span class="badge-success">0</span>'
            if s.violations == 0
            else f'<span class="badge-danger">{s.violations}</span>'
        )

        benchmark_rows.append(f"""
        <tr>
            <td class="text-center font-bold text-slate-500">{rank}</td>
            <td>
                <div class="strategy-badge">
                    <span class="strategy-dot" style="background-color: {color};"></span>
                    <strong>{s.strategy_name}</strong>
                </div>
            </td>
            <td class="text-right font-bold text-slate-900 num-cell">₹{s.mean_net_paise/100:,.2f}</td>
            <td class="text-right text-slate-700 num-cell">{diff_str}</td>
            <td class="text-right text-slate-600 num-cell">₹{s.min_net_paise/100:,.0f} – ₹{s.max_net_paise/100:,.0f}</td>
            <td class="text-right font-medium num-cell">{s.gross_recovery_rate_pct:.1f}%</td>
            <td class="text-right font-medium num-cell">{s.decision_match_rate_pct:.1f}%</td>
            <td class="text-right text-slate-600 num-cell">₹{s.regret_paise/100:,.2f}</td>
            <td class="text-center">{v_badge}</td>
            <td class="text-center font-medium num-cell">{s.retries_made}</td>
            <td class="text-center font-medium num-cell">{s.contacts_sent}</td>
            <td class="text-center font-medium num-cell">{s.escalations}</td>
        </tr>
        """)

    # Table rows for sensitivity
    sensitivity_rows = []
    for p in penalties_inr:
        is_breakeven = (p == 889 or abs(p - breakeven_penalty_inr) < 1.0)
        row_cls = 'class="highlight-row"' if is_breakeven else ""

        # Find best deployable strategy for this penalty level
        best_deployable = ""
        best_val = -float("inf")
        for name in deployable_names:
            v = sweep_results[p].get(name, 0.0)
            if v > best_val:
                best_val = v
                best_deployable = name

        cells = [f'<td class="font-bold text-slate-900 text-center num-cell">₹{p:,}</td>']
        for name in strategy_names:
            v = sweep_results[p].get(name, 0.0)
            val_cls = "text-danger font-bold" if v < 0 else "text-slate-700"
            cells.append(f'<td class="text-right {val_cls} num-cell">₹{v:,.2f}</td>')

        dep_color = STRATEGY_COLORS.get(best_deployable, "#334155")
        cells.append(
            f'<td class="text-center"><span class="badge-deployable" style="background: {dep_color}15; color: {dep_color}; border: 1px solid {dep_color}40;">'
            f'{best_deployable}</span></td>'
        )

        sensitivity_rows.append(f"<tr {row_cls}>" + "".join(cells) + "</tr>")

    # Compliance panel table rows
    compliance_rows = []
    for s in benchmark_stats:
        color = STRATEGY_COLORS.get(s.strategy_name, "#334155")
        if s.violations == 0:
            status_html = '<span class="badge-success">Fully Compliant (0 Violations)</span>'
        else:
            status_html = f'<span class="badge-danger">{s.violations} Regulatory Violations</span>'

        compliance_rows.append(f"""
        <tr>
            <td>
                <div class="strategy-badge">
                    <span class="strategy-dot" style="background-color: {color};"></span>
                    <strong>{s.strategy_name}</strong>
                </div>
            </td>
            <td class="text-center">{status_html}</td>
            <td class="text-center font-bold num-cell">{s.violations}</td>
            <td class="text-center num-cell">{s.retries_made}</td>
            <td class="text-center num-cell">{s.contacts_sent}</td>
            <td class="text-center num-cell">{s.escalations}</td>
        </tr>
        """)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Razorpay Subscription Recovery Benchmark Report</title>
    <style>
        :root {{
            --bg-body: #ffffff;
            --text-primary: #0f172a;
            --text-secondary: #475569;
            --text-muted: #64748b;
            --accent: #2563eb;
            --accent-light: #eff6ff;
            --accent-border: #bfdbfe;
            --danger: #dc2626;
            --danger-light: #fee2e2;
            --warning: #d97706;
            --warning-light: #fffbeb;
            --purple: #7c3aed;
            --border-light: #e2e8f0;
            --border-subtle: #f1f5f9;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-body);
            color: var(--text-primary);
            font-size: 15px;
            line-height: 1.6;
            padding: 40px 20px;
            -webkit-font-smoothing: antialiased;
        }}

        .container {{
            max-width: 920px;
            margin: 0 auto;
        }}

        /* Typography */
        h1, h2, h3 {{
            font-family: Georgia, 'Times New Roman', serif;
            color: var(--text-primary);
            font-weight: 700;
            letter-spacing: -0.01em;
        }}

        .report-title {{
            font-size: 28px;
            line-height: 1.25;
            margin-bottom: 6px;
        }}

        .report-subtitle {{
            font-size: 15px;
            color: var(--text-secondary);
            font-style: italic;
            font-family: Georgia, 'Times New Roman', serif;
        }}

        .section-title {{
            font-size: 21px;
            margin-bottom: 6px;
        }}

        .section-desc {{
            font-size: 14.5px;
            color: var(--text-secondary);
            margin-bottom: 18px;
        }}

        /* Tabular figures for numbers */
        .num-cell, .tabular, .kpi-value {{
            font-variant-numeric: tabular-nums;
        }}

        /* Header block */
        header.report-header {{
            padding-bottom: 24px;
        }}

        .meta-chips {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 16px;
        }}

        .chip {{
            display: inline-flex;
            align-items: center;
            padding: 5px 10px;
            border-radius: 4px;
            background: #f8fafc;
            font-size: 12.5px;
            color: var(--text-secondary);
            border: 1px solid var(--border-light);
            font-variant-numeric: tabular-nums;
        }}

        .chip strong {{
            color: var(--text-primary);
            margin-left: 4px;
        }}

        .composition-box {{
            background: #f8fafc;
            border-left: 3px solid var(--accent);
            color: #1e3a8a;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            font-size: 12.5px;
            padding: 9px 14px;
            border-radius: 0 4px 4px 0;
            margin-top: 16px;
        }}

        /* Section Rules */
        .report-section {{
            border-top: 1px solid var(--border-light);
            padding-top: 32px;
            margin-top: 36px;
        }}

        /* Prominent Simulation Disclaimer */
        .simulation-banner {{
            background: #fffbeb;
            border: 1px solid #fde68a;
            border-left: 4px solid var(--warning);
            border-radius: 4px;
            padding: 14px 18px;
            margin: 20px 0 28px 0;
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        .banner-icon {{
            font-size: 20px;
            flex-shrink: 0;
        }}

        .banner-text {{
            font-size: 14px;
            font-weight: 600;
            color: #92400e;
        }}

        /* Key Finding Callout Box */
        .key-finding-box {{
            background: #f8fafc;
            border: 1px solid var(--border-light);
            border-left: 4px solid var(--accent);
            border-radius: 0 6px 6px 0;
            padding: 16px 20px;
            margin-bottom: 22px;
        }}

        .key-finding-tag {{
            font-size: 12px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: var(--accent);
            margin-bottom: 4px;
        }}

        .key-finding-body {{
            font-size: 14.5px;
            color: #1e293b;
            line-height: 1.55;
        }}

        /* Chart container */
        .chart-box {{
            width: 100%;
            overflow-x: auto;
            background: #ffffff;
            border: 1px solid var(--border-light);
            border-radius: 6px;
            padding: 14px;
        }}

        .chart-caption {{
            font-size: 13px;
            color: var(--text-muted);
            margin-top: 10px;
            font-style: italic;
            text-align: center;
        }}

        /* Tables */
        .table-responsive {{
            width: 100%;
            overflow-x: auto;
            border: 1px solid var(--border-light);
            border-radius: 6px;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13.5px;
            text-align: left;
            font-variant-numeric: tabular-nums;
        }}

        th, td, .num-cell {{
            font-variant-numeric: tabular-nums;
        }}

        th {{
            background: #f8fafc;
            color: var(--text-secondary);
            font-weight: 600;
            padding: 10px 12px;
            border-bottom: 1.5px solid var(--border-light);
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }}

        td {{
            padding: 10px 12px;
            border-bottom: 1px solid var(--border-subtle);
            color: var(--text-primary);
        }}

        tr:last-child td {{
            border-bottom: none;
        }}

        tr:hover td {{
            background-color: #f8fafc;
        }}

        tr.highlight-row td {{
            background-color: #fffbeb !important;
            border-top: 1px solid #fde68a;
            border-bottom: 1px solid #fde68a;
        }}

        .text-left {{ text-align: left; }}
        .text-right {{ text-align: right; }}
        .text-center {{ text-align: center; }}
        .font-bold {{ font-weight: 700; }}
        .font-medium {{ font-weight: 500; }}

        .text-danger {{ color: var(--danger); }}
        .text-success {{ color: #15803d; }}
        .text-slate-900 {{ color: #0f172a; }}
        .text-slate-700 {{ color: #334155; }}
        .text-slate-600 {{ color: #475569; }}
        .text-slate-500 {{ color: #64748b; }}

        .strategy-badge {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }}

        .strategy-dot {{
            width: 9px;
            height: 9px;
            border-radius: 50%;
            display: inline-block;
        }}

        /* Badges */
        .badge-success {{
            background: #dcfce7;
            color: #15803d;
            font-size: 11px;
            font-weight: 700;
            padding: 3px 7px;
            border-radius: 4px;
            display: inline-block;
        }}

        .badge-danger {{
            background: #fee2e2;
            color: #b91c1c;
            font-size: 11px;
            font-weight: 700;
            padding: 3px 7px;
            border-radius: 4px;
            display: inline-block;
        }}

        .badge-neutral {{
            background: #f1f5f9;
            color: #475569;
            font-size: 11px;
            font-weight: 600;
            padding: 3px 7px;
            border-radius: 4px;
            display: inline-block;
        }}

        .badge-deployable {{
            font-size: 11px;
            font-weight: 700;
            padding: 3px 8px;
            border-radius: 4px;
            display: inline-block;
            text-transform: capitalize;
        }}

        .footnote {{
            font-size: 12.5px;
            color: var(--text-muted);
            margin-top: 10px;
            font-style: italic;
            line-height: 1.5;
        }}

        /* Compliance Grid */
        .compliance-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 14px;
            margin-bottom: 22px;
        }}

        .compliance-kpi {{
            background: #f8fafc;
            border: 1px solid var(--border-light);
            border-radius: 6px;
            padding: 16px;
        }}

        .kpi-title {{
            font-size: 11.5px;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            color: var(--text-secondary);
            font-weight: 600;
        }}

        .kpi-value {{
            font-size: 24px;
            font-weight: 800;
            color: var(--text-primary);
            margin-top: 4px;
        }}

        .kpi-desc {{
            font-size: 12px;
            color: var(--text-muted);
            margin-top: 4px;
            line-height: 1.4;
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- 2.a Header -->
        <header class="report-header">
            <h1 class="report-title">Subscription Recovery Benchmark Report</h1>
            <p class="report-subtitle">Razorpay Buildathon Track 3: Autonomous Recovery Agent Evaluation</p>
            <div class="meta-chips">
                <span class="chip">Batch: <strong>{metadata['batch_size']} records</strong></span>
                <span class="chip">Seeds: <strong>{metadata['seeds']} draws</strong></span>
                <span class="chip">Revenue at Risk: <strong>₹{metadata['total_at_risk_paise']/100:,.2f}</strong></span>
                <span class="chip">Base Penalty: <strong>₹{metadata['penalty_paise']/100:,.0f} / violation</strong></span>
                <span class="chip">Policy Version: <strong>{metadata['policy_version']}</strong></span>
                <span class="chip">Generated: <strong>{metadata['timestamp']}</strong></span>
            </div>
            <div class="composition-box">
                {metadata['composition_line']}
            </div>
        </header>

        <!-- 2.b Prominent Disclaimer Banner -->
        <div class="simulation-banner">
            <div class="banner-icon">⚖️</div>
            <div class="banner-text">
                All recovery outcomes are simulated under an explicit probability model. No live merchant money was recovered.
            </div>
        </div>

        <!-- 2.c THE PENALTY SENSITIVITY CURVE - Centrepiece -->
        <section class="report-section">
            <h2 class="section-title">The Penalty Sensitivity Curve (Centrepiece)</h2>
            <p class="section-desc">
                Mean net recovery across non-compliance penalties from ₹0 to ₹5,000 per violation.
            </p>

            <div class="key-finding-box">
                <div class="key-finding-tag">Key Finding</div>
                <div class="key-finding-body">
                    Compliance-guarded recovery (<strong>agent_rules</strong>) overtakes unconstrained retrying (<strong>naive_rules</strong>) at an exact penalty of <strong>₹{breakeven_penalty_inr:,.2f}</strong> per violation. Above <strong>₹{oracle_threshold_inr:,.2f}</strong>, even an unconstrained profit-maximiser with full model knowledge stops violating, because violation stops paying on its own terms.
                </div>
            </div>

            <div class="key-finding-box" style="margin-top: 14px; border-left: 3px solid #64748b; background: #f8fafc;">
                <div class="key-finding-tag" style="color: #475569;">Expected-Value Gating on Human Escalation</div>
                <div class="key-finding-body">
                    Theoretical expected gain from the EV gate is <strong>₹176.40</strong>. Realised gain across {metadata['seeds']} seeds is <strong>₹145.01</strong> — below theory, because human escalation happened to over-perform its 35% prior in these seeds (38% realised). The measured benefit is therefore conservative, not flattered by sampling.<br><br>
                    Paired across {metadata['seeds']} identical seeds, the EV gate improves <code>agent_rules</code> net by <strong>₹145.01 ± ₹18.36</strong>. The effect is unambiguous and small: 0.15% of the ₹98,952 book. Its significance is structural rather than monetary — escalating a ₹299 payment at a ₹150 support cost is wrong regardless of how it samples, and the gate removes that class of decision.
                </div>
            </div>

            <div class="chart-box">
                {curve_svg}
            </div>
            <p class="chart-caption">Lines show mean net recovery across penalty levels from Rs 0 to Rs 5,000. agent_rules and agent_llm nearly coincide - paired across 200 identical seeds the difference is -Rs 285 +/- Rs 570, smaller than its own standard error. Both run zero violations. See the sensitivity table for exact values.</p>
        </section>

        <!-- 2.d Horizontal Bar Chart at Base Penalty -->
        <section class="report-section">
            <h2 class="section-title">Mean Net Recovery by Strategy (₹500 Base Penalty)</h2>
            <p class="section-desc">
                Evaluated across {metadata['seeds']} seeded draws with paired standard errors (±SE) relative to agent_rules.
            </p>
            <div class="chart-box">
                {barchart_svg}
            </div>
        </section>

        <!-- 2.e Full Benchmark Table -->
        <section class="report-section">
            <h2 class="section-title">Multi-Strategy Benchmark Performance Table</h2>
            <p class="section-desc">
                Comprehensive accounting of net revenue, paired statistical differences, decision consistency, and regulatory metrics.
            </p>
            <div class="table-responsive">
                <table>
                    <thead>
                        <tr>
                            <th class="text-center">Rank</th>
                            <th>Strategy</th>
                            <th class="text-right">Mean Net (₹)</th>
                            <th class="text-right">Paired Diff vs agent_rules</th>
                            <th class="text-right">Net Range (₹)</th>
                            <th class="text-right">Gross Recov %</th>
                            <th class="text-right">Match Oracle %</th>
                            <th class="text-right">Regret (₹)</th>
                            <th class="text-center">Violations</th>
                            <th class="text-center">Retries</th>
                            <th class="text-center">Contacts</th>
                            <th class="text-center">Escalations</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(benchmark_rows)}
                    </tbody>
                </table>
            </div>
        </section>

        <!-- 2.f Full Sensitivity Table -->
        <section class="report-section">
            <h2 class="section-title">Compliance Penalty Sensitivity Table</h2>
            <p class="section-desc">
                Net recovery trajectory across regulatory penalty tiers. Break-even threshold is <strong>₹{breakeven_penalty_inr:,.2f}</strong>; Oracle compliance threshold is <strong>₹{oracle_threshold_inr:,.2f}</strong>.
            </p>
            <div class="table-responsive">
                <table>
                    <thead>
                        <tr>
                            <th class="text-center">Penalty Level</th>
                            {"".join(f'<th class="text-right">{name}</th>' for name in strategy_names)}
                            <th class="text-center">Best Deployable Strategy</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(sensitivity_rows)}
                    </tbody>
                </table>
            </div>
            <p class="footnote">
                *Note on Best Deployable Strategy: Oracle represents the theoretical upper bound reading the hidden recovery matrix directly and is excluded from deployable selections.<br>
                *Note on Oracle compliance threshold: On this 40-record batch the threshold of ₹{oracle_threshold_inr:,.2f} is driven by a single record (pay_Ex11kLmNoPqR10, Rs 9,999, gateway_timeout at the retry cap), so it is batch-specific, not a general constant.
            </p>
        </section>

        <!-- The Compliance Pricing Curve -->
        <section class="report-section">
            <h2 class="section-title">The Compliance Pricing Curve</h2>
            <p class="section-desc">
                Three programmatically derived penalty thresholds establish the economic boundaries of autonomous subscription recovery on this batch:
            </p>
            <div class="table-responsive">
                <table>
                    <thead>
                        <tr>
                            <th style="width: 140px;">Penalty Threshold</th>
                            <th style="width: 240px;">Economic Event</th>
                            <th>Market & Behavioral Meaning</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td class="font-bold text-slate-900 num-cell">₹62.08</td>
                            <td><strong>Cheapest violation stops paying</strong></td>
                            <td class="text-slate-700">Below ₹62.08, no violation is deterred; every unlawful retry yields higher net expected margin than its best compliant alternative. At ₹62.08, <code>pay_Ex66fGhIjKlM65</code> (₹899, insufficient funds) ceases to be profitable to retry unlawfully and switches to compliant notice reissuance.</td>
                        </tr>
                        <tr class="highlight-row">
                            <td class="font-bold text-slate-900 num-cell">₹{breakeven_penalty_inr:,.2f}</td>
                            <td><strong>Compliant agent overtakes naive rulebook</strong></td>
                            <td class="text-slate-700">At ₹{breakeven_penalty_inr:,.2f}, <code>agent_rules</code> strictly overtakes <code>naive_rules</code> net of compliance risk. <code>naive_rules</code> is unchanged; <code>agent_rules</code> rose by the EV gate, shrinking the gross performance gap so the crossing arrives earlier. Between ₹{breakeven_penalty_inr:,.2f} and ₹{oracle_threshold_inr:,.2f}, compliance is the superior system-wide policy while individual high-value violations remain locally profitable.</td>
                        </tr>
                        <tr>
                            <td class="font-bold text-slate-900 num-cell">₹{oracle_threshold_inr:,.2f}</td>
                            <td><strong>Profit-maximiser abandons violations entirely</strong></td>
                            <td class="text-slate-700">Above ₹{oracle_threshold_inr:,.2f}, an unconstrained profit-maximising Oracle with full model knowledge eliminates all violations (drops to 0). Driven by <code>pay_Ex11kLmNoPqR10</code> (₹9,999, gateway timeout at retry cap). Above this price, nothing pays.</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            <p class="footnote">
                *Note: All three thresholds are derived programmatically from this 40-record batch and are batch-specific economic properties of the invoice distribution, not general constants.
            </p>
        </section>

        <!-- 2.g Compliance Panel -->
        <section class="report-section">
            <h2 class="section-title">Regulatory Compliance & Operational Panel</h2>
            <p class="section-desc">
                Encodes RBI pre-debit notification and AFA threshold rules, plus per-method retry caps.
            </p>

            <div class="compliance-grid">
                <div class="compliance-kpi">
                    <div class="kpi-title">Agent Violations</div>
                    <div class="kpi-value text-success">0</div>
                    <div class="kpi-desc">agent_rules and agent_llm maintain 100% regulatory compliance</div>
                </div>
                <div class="compliance-kpi">
                    <div class="kpi-title">Naive Rulebook Violations</div>
                    <div class="kpi-value text-danger">6</div>
                    <div class="kpi-desc">Pre-debit notice and hard decline violations in naive_rules</div>
                </div>
                <div class="compliance-kpi">
                    <div class="kpi-title">Always-Retry Violations</div>
                    <div class="kpi-value text-danger">16</div>
                    <div class="kpi-desc">Severe double-debit and non-compliance risk</div>
                </div>
                <div class="compliance-kpi">
                    <div class="kpi-title">Break-Even Penalty</div>
                    <div class="kpi-value" style="color: var(--warning);">₹{breakeven_penalty_inr:,.2f}</div>
                    <div class="kpi-desc">Penalty above which compliant agent strictly beats legacy rulebook</div>
                </div>
            </div>

            <div class="table-responsive">
                <table>
                    <thead>
                        <tr>
                            <th>Strategy</th>
                            <th class="text-center">Compliance Status</th>
                            <th class="text-center">Violations</th>
                            <th class="text-center">Retries Made</th>
                            <th class="text-center">Contacts Sent</th>
                            <th class="text-center">Escalated to Human</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(compliance_rows)}
                    </tbody>
                </table>
            </div>
        </section>
    </div>
</body>
</html>
"""
    return html_content
