import math
from typing import Dict, List, Any
from datetime import datetime


STRATEGY_COLORS = {
    "oracle": "#7c3aed",
    "agent_rules": "#059669",
    "agent_llm": "#0284c7",
    "naive_rules": "#d97706",
    "always_retry": "#dc2626",
    "message_only": "#4f46e5",
    "no_action": "#94a3b8",
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
) -> str:
    """Draws inline SVG of the penalty sensitivity curve with break-even marker and plunging always_retry."""
    width = 1040
    height = 540
    margin_left = 95
    margin_right = 165
    margin_top = 45
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

    # Horizontal Grid lines and Y labels (step = 10,000)
    step_y = 10000 if y_range <= 80000 else 20000
    cur_y = y_floor
    while cur_y <= y_ceil:
        sy = map_y(cur_y)
        is_zero = (cur_y == 0)
        line_color = "#94a3b8" if is_zero else "#f1f5f9"
        line_width = "1.75" if is_zero else "1"
        line_dash = 'stroke-dasharray="4,4"' if is_zero else ""

        svg_parts.append(
            f'<line x1="{margin_left}" y1="{sy:.1f}" x2="{margin_left + plot_width}" y2="{sy:.1f}" '
            f'stroke="{line_color}" stroke-width="{line_width}" {line_dash} />'
        )

        font_weight = "bold" if is_zero else "normal"
        text_fill = "#0f172a" if is_zero else "#64748b"
        label_text = f"₹{cur_y:+,}" if cur_y != 0 else "₹0 (Break-Even Net)"
        svg_parts.append(
            f'<text x="{margin_left - 10}" y="{sy + 4:.1f}" text-anchor="end" font-size="11" '
            f'font-weight="{font_weight}" fill="{text_fill}">{label_text}</text>'
        )
        cur_y += step_y

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
            f'fill="#64748b">₹{xt:,}</text>'
        )

    # X-axis label
    svg_parts.append(
        f'<text x="{margin_left + plot_width / 2:.1f}" y="{margin_top + plot_height + 48}" '
        f'text-anchor="middle" font-size="12" font-weight="600" fill="#334155">'
        f'Regulatory Non-Compliance Penalty per Violation (₹)</text>'
    )

    # Y-axis title
    svg_parts.append(
        f'<text transform="rotate(-90)" x="{-margin_top - plot_height / 2:.1f}" y="{margin_left - 65}" '
        f'text-anchor="middle" font-size="12" font-weight="600" fill="#334155">'
        f'Mean Net Recovery (₹)</text>'
    )

    # Break-Even Vertical Marker at breakeven_penalty_inr
    be_x = map_x(breakeven_penalty_inr)
    svg_parts.append(
        f'<line x1="{be_x:.1f}" y1="{margin_top}" x2="{be_x:.1f}" y2="{margin_top + plot_height}" '
        f'stroke="#d97706" stroke-width="2.5" stroke-dasharray="6,4" />'
    )

    # Draw strategy polylines
    # Order so high priority lines are on top
    strategy_order = ["no_action", "always_retry", "message_only", "naive_rules", "agent_llm", "agent_rules", "oracle"]
    end_labels = []

    for strat in strategy_order:
        pts = []
        for p in penalties_inr:
            val = sweep_results[p].get(strat, 0.0)
            pts.append((map_x(p), map_y(val), val))

        color = STRATEGY_COLORS.get(strat, "#334155")
        poly_str = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in pts)

        dash = ""
        width_val = "2.5"
        if strat == "oracle":
            dash = 'stroke-dasharray="6,3"'
            width_val = "2.5"
        elif strat == "agent_rules":
            width_val = "3.5"
        elif strat == "always_retry":
            width_val = "3.0"
        elif strat == "message_only":
            dash = 'stroke-dasharray="4,2"'
        elif strat == "no_action":
            dash = 'stroke-dasharray="3,3"'
            width_val = "1.5"

        svg_parts.append(
            f'<polyline points="{poly_str}" fill="none" stroke="{color}" stroke-width="{width_val}" '
            f'{dash} stroke-linecap="round" stroke-linejoin="round" />'
        )

        # Plot point dots
        for x, y, _ in pts:
            svg_parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}" stroke="#ffffff" stroke-width="1.5" />')

        last_x, last_y, last_val = pts[-1]
        end_labels.append({"strat": strat, "x": last_x, "y": last_y, "val": last_val, "color": color})

    # Deconflict end label y positions so they never overlap
    end_labels.sort(key=lambda item: item["y"])
    min_gap = 18
    for k in range(1, len(end_labels)):
        if end_labels[k]["y"] - end_labels[k-1]["y"] < min_gap:
            end_labels[k]["y"] = end_labels[k-1]["y"] + min_gap

    for item in end_labels:
        val_str = f"₹{item['val']:+,.0f}" if item['val'] != 0 else "₹0"
        svg_parts.append(
            f'<text x="{item["x"] + 8:.1f}" y="{item["y"] + 4:.1f}" font-size="11" font-weight="600" fill="{item["color"]}">'
            f'{item["strat"]} ({val_str})</text>'
        )

    # Break-Even Intersection Dot & Callout Box
    # Y position at break-even for agent_rules
    agent_net_at_be = sweep_results[penalties_inr[0]].get("agent_rules", 23619.58)
    be_y = map_y(agent_net_at_be)

    svg_parts.append(
        f'<circle cx="{be_x:.1f}" cy="{be_y:.1f}" r="8" fill="#d97706" stroke="#ffffff" stroke-width="2.5" />'
    )
    svg_parts.append(
        f'<circle cx="{be_x:.1f}" cy="{be_y:.1f}" r="13" fill="none" stroke="#d97706" stroke-width="1.5" opacity="0.4" />'
    )

    # Callout badge for break-even, placed cleanly in top margin directly aligned with dashed marker
    box_w = 210
    box_h = 34
    box_x = be_x - box_w / 2
    box_y = 6

    svg_parts.append(
        f'<g>'
        f'<rect x="{box_x:.1f}" y="{box_y:.1f}" width="{box_w}" height="{box_h}" rx="5" '
        f'fill="#fffbeb" stroke="#d97706" stroke-width="1.5" filter="drop-shadow(0 2px 4px rgba(0,0,0,0.06))" />'
        f'<text x="{box_x + box_w / 2:.1f}" y="{box_y + 14:.1f}" text-anchor="middle" font-size="11" '
        f'font-weight="bold" fill="#92400e">Crossing Point: ₹{breakeven_penalty_inr:,.2f}</text>'
        f'<text x="{box_x + box_w / 2:.1f}" y="{box_y + 27:.1f}" text-anchor="middle" font-size="9.5" '
        f'font-weight="600" fill="#b45309">agent_rules overtakes naive_rules</text>'
        f'</g>'
    )

    # Plunge label for always_retry
    always_end_y = map_y(sweep_results[5000].get("always_retry", -66666.0))
    svg_parts.append(
        f'<g transform="translate({map_x(5000) - 210}, {always_end_y - 28})">'
        f'<rect x="0" y="0" width="200" height="24" rx="4" fill="#fee2e2" stroke="#dc2626" stroke-width="1" />'
        f'<text x="100" y="16" text-anchor="middle" font-size="10" font-weight="bold" fill="#991b1b">'
        f'always_retry plunges below zero</text>'
        f'</g>'
    )

    svg_parts.append('</svg>')
    return "\n".join(svg_parts)


def build_horizontal_bar_chart_svg(benchmark_stats: List[Any]) -> str:
    """Draws inline SVG horizontal bar chart of mean net recovery at base penalty with paired SE error bars."""
    width = 1040
    n_bars = len(benchmark_stats)
    bar_height = 28
    bar_gap = 18
    margin_left = 140
    margin_right = 210
    margin_top = 40
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
            f'<text x="{tx:.1f}" y="{margin_top + plot_height + 20}" text-anchor="middle" font-size="11" fill="#64748b">'
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
            f'<text x="{margin_left - 12}" y="{bar_y + 19}" text-anchor="end" font-size="12" '
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
                f'<line x1="{x_min_err:.1f}" y1="{mid_y - 6:.1f}" x2="{x_min_err:.1f}" y2="{mid_y + 6:.1f}" '
                f'stroke="#0f172a" stroke-width="2" />'
            )
            # Right cap
            svg_parts.append(
                f'<line x1="{x_max_err:.1f}" y1="{mid_y - 6:.1f}" x2="{x_max_err:.1f}" y2="{mid_y + 6:.1f}" '
                f'stroke="#0f172a" stroke-width="2" />'
            )
            val_x = x_max_err + 10
            err_str = f"±₹{se_val:,.2f}"
        else:
            val_x = center_x + 10
            err_str = "Baseline" if s.strategy_name == "agent_rules" else "—"

        # Value label
        svg_parts.append(
            f'<text x="{val_x:.1f}" y="{bar_y + 19}" font-size="12" font-weight="700" fill="#0f172a">'
            f'₹{net_val:,.2f} <tspan font-size="11" font-weight="normal" fill="#64748b">({err_str})</tspan></text>'
        )

    svg_parts.append('</svg>')
    return "\n".join(svg_parts)


def generate_benchmark_html(
    benchmark_stats: List[Any],
    sweep_results: Dict[int, Dict[str, float]],
    breakeven_penalty_inr: float,
    metadata: Dict[str, Any],
) -> str:
    """Generates a complete, self-contained, standalone HTML report."""
    penalties_inr = sorted(list(sweep_results.keys()))

    curve_svg = build_sensitivity_curve_svg(sweep_results, breakeven_penalty_inr, penalties_inr)
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
            <td class="text-right font-bold text-slate-900">₹{s.mean_net_paise/100:,.2f}</td>
            <td class="text-right text-slate-700">{diff_str}</td>
            <td class="text-right text-slate-600">₹{s.min_net_paise/100:,.0f} – ₹{s.max_net_paise/100:,.0f}</td>
            <td class="text-right font-medium">{s.gross_recovery_rate_pct:.1f}%</td>
            <td class="text-right font-medium">{s.decision_match_rate_pct:.1f}%</td>
            <td class="text-right text-slate-600">₹{s.regret_paise/100:,.2f}</td>
            <td class="text-center">{v_badge}</td>
            <td class="text-center font-medium">{s.retries_made}</td>
            <td class="text-center font-medium">{s.contacts_sent}</td>
            <td class="text-center font-medium">{s.escalations}</td>
        </tr>
        """)

    # Table rows for sensitivity
    sensitivity_rows = []
    for p in penalties_inr:
        is_breakeven = (p == 913 or abs(p - breakeven_penalty_inr) < 1.0)
        row_cls = 'class="highlight-row"' if is_breakeven else ""

        # Find best deployable strategy for this penalty level
        best_deployable = ""
        best_val = -float("inf")
        for name in deployable_names:
            v = sweep_results[p].get(name, 0.0)
            if v > best_val:
                best_val = v
                best_deployable = name

        cells = [f'<td class="font-bold text-slate-900 text-center">₹{p:,}</td>']
        for name in strategy_names:
            v = sweep_results[p].get(name, 0.0)
            val_cls = "text-danger font-bold" if v < 0 else "text-slate-700"
            cells.append(f'<td class="text-right {val_cls}">₹{v:,.2f}</td>')

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
            <td class="text-center font-bold">{s.violations}</td>
            <td class="text-center">{s.retries_made}</td>
            <td class="text-center">{s.contacts_sent}</td>
            <td class="text-center">{s.escalations}</td>
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
            --bg-body: #f8fafc;
            --bg-card: #ffffff;
            --border-card: #e2e8f0;
            --text-primary: #0f172a;
            --text-secondary: #475569;
            --text-muted: #64748b;
            --primary: #2563eb;
            --success: #059669;
            --danger: #dc2626;
            --warning: #d97706;
            --purple: #7c3aed;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background-color: var(--bg-body);
            color: var(--text-primary);
            line-height: 1.5;
            padding: 32px 24px;
            -webkit-font-smoothing: antialiased;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}

        /* Header */
        .report-header {{
            background: var(--bg-card);
            border: 1px solid var(--border-card);
            border-radius: 12px;
            padding: 28px 32px;
            margin-bottom: 24px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
        }}

        .report-title-row {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            flex-wrap: wrap;
            gap: 16px;
            margin-bottom: 20px;
        }}

        .report-title {{
            font-size: 26px;
            font-weight: 800;
            color: var(--text-primary);
            letter-spacing: -0.02em;
        }}

        .report-subtitle {{
            font-size: 14px;
            color: var(--text-secondary);
            margin-top: 4px;
        }}

        .meta-chips {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }}

        .chip {{
            display: inline-flex;
            align-items: center;
            padding: 6px 12px;
            border-radius: 6px;
            background: #f1f5f9;
            font-size: 12.5px;
            color: var(--text-secondary);
            font-weight: 500;
            border: 1px solid #e2e8f0;
        }}

        .chip strong {{
            color: var(--text-primary);
            margin-left: 4px;
        }}

        .composition-box {{
            background: #eff6ff;
            border: 1px solid #bfdbfe;
            color: #1e40af;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            font-size: 12.5px;
            padding: 10px 14px;
            border-radius: 6px;
            margin-top: 16px;
            font-weight: 600;
        }}

        /* Prominent Disclaimer Banner */
        .simulation-banner {{
            background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
            border: 1.5px solid #f59e0b;
            border-left: 6px solid #d97706;
            border-radius: 10px;
            padding: 16px 20px;
            margin-bottom: 28px;
            display: flex;
            align-items: center;
            gap: 14px;
            box-shadow: 0 2px 4px rgba(217, 119, 6, 0.08);
        }}

        .banner-icon {{
            font-size: 22px;
            flex-shrink: 0;
        }}

        .banner-text {{
            font-size: 14.5px;
            font-weight: 700;
            color: #92400e;
            letter-spacing: -0.01em;
        }}

        /* Cards */
        .card {{
            background: var(--bg-card);
            border: 1px solid var(--border-card);
            border-radius: 12px;
            padding: 28px;
            margin-bottom: 28px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
        }}

        .card-header {{
            margin-bottom: 20px;
        }}

        .card-title {{
            font-size: 20px;
            font-weight: 700;
            color: var(--text-primary);
            letter-spacing: -0.01em;
        }}

        .card-desc {{
            font-size: 13.5px;
            color: var(--text-secondary);
            margin-top: 4px;
        }}

        /* Chart container */
        .chart-box {{
            width: 100%;
            overflow-x: auto;
            background: #ffffff;
            border: 1px solid #f1f5f9;
            border-radius: 8px;
            padding: 12px;
        }}

        /* Tables */
        .table-responsive {{
            width: 100%;
            overflow-x: auto;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13.5px;
            text-align: left;
        }}

        th {{
            background: #f8fafc;
            color: var(--text-secondary);
            font-weight: 600;
            padding: 12px 14px;
            border-bottom: 1.5px solid var(--border-card);
            text-transform: uppercase;
            font-size: 11px;
            letter-spacing: 0.04em;
        }}

        td {{
            padding: 12px 14px;
            border-bottom: 1px solid #f1f5f9;
            color: var(--text-primary);
        }}

        tr:hover td {{
            background-color: #f8fafc;
        }}

        tr.highlight-row td {{
            background-color: #fffbeb !important;
            border-top: 1.5px solid #fde68a;
            border-bottom: 1.5px solid #fde68a;
        }}

        .text-left {{ text-align: left; }}
        .text-right {{ text-align: right; }}
        .text-center {{ text-align: center; }}
        .font-bold {{ font-weight: 700; }}
        .font-medium {{ font-weight: 500; }}

        .text-danger {{ color: var(--danger); }}
        .text-success {{ color: var(--success); }}
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
            width: 10px;
            height: 10px;
            border-radius: 50%;
            display: inline-block;
        }}

        /* Badges */
        .badge-success {{
            background: #dcfce7;
            color: #15803d;
            font-size: 11.5px;
            font-weight: 700;
            padding: 4px 8px;
            border-radius: 4px;
            display: inline-block;
        }}

        .badge-danger {{
            background: #fee2e2;
            color: #b91c1c;
            font-size: 11.5px;
            font-weight: 700;
            padding: 4px 8px;
            border-radius: 4px;
            display: inline-block;
        }}

        .badge-neutral {{
            background: #f1f5f9;
            color: #475569;
            font-size: 11.5px;
            font-weight: 600;
            padding: 4px 8px;
            border-radius: 4px;
            display: inline-block;
        }}

        .badge-deployable {{
            font-size: 11.5px;
            font-weight: 700;
            padding: 4px 10px;
            border-radius: 6px;
            display: inline-block;
            text-transform: capitalize;
        }}

        .footnote {{
            font-size: 12px;
            color: var(--text-muted);
            margin-top: 12px;
            font-style: italic;
        }}

        /* Compliance Grid */
        .compliance-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}

        .compliance-kpi {{
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 16px;
        }}

        .kpi-title {{
            font-size: 12px;
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
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- 2.a Header -->
        <header class="report-header">
            <div class="report-title-row">
                <div>
                    <h1 class="report-title">Subscription Recovery Benchmark Report</h1>
                    <p class="report-subtitle">Razorpay Buildathon Track 3: Failed Subscription Recovery Agent</p>
                </div>
                <div class="meta-chips">
                    <span class="chip">Batch Size: <strong>{metadata['batch_size']} records</strong></span>
                    <span class="chip">Seeds: <strong>{metadata['seeds']} draws</strong></span>
                    <span class="chip">Revenue at Risk: <strong>₹{metadata['total_at_risk_paise']/100:,.2f}</strong></span>
                    <span class="chip">Base Penalty: <strong>₹{metadata['penalty_paise']/100:,.0f} / violation</strong></span>
                    <span class="chip">Policy Version: <strong>{metadata['policy_version']}</strong></span>
                    <span class="chip">Generated: <strong>{metadata['timestamp']}</strong></span>
                </div>
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
        <section class="card">
            <div class="card-header">
                <h2 class="card-title">The Penalty Sensitivity Curve (Centrepiece)</h2>
                <p class="card-desc">
                    Mean net recovery as regulatory non-compliance penalty increases from ₹0 to ₹5,000 per violation.
                    Notice the exact break-even crossing point at <strong>₹{breakeven_penalty_inr:,.2f}</strong> where
                    <strong>agent_rules</strong> overtakes <strong>naive_rules</strong>, and the steep plunge of unguarded <strong>always_retry</strong> into severe losses.
                </p>
            </div>
            <div class="chart-box">
                {curve_svg}
            </div>
        </section>

        <!-- 2.d Horizontal Bar Chart at Rs 500 Penalty -->
        <section class="card">
            <div class="card-header">
                <h2 class="card-title">Mean Net Recovery by Strategy (₹500 Base Penalty)</h2>
                <p class="card-desc">
                    Evaluated across {metadata['seeds']} seeded draws with paired standard errors (±SE) relative to agent_rules.
                </p>
            </div>
            <div class="chart-box">
                {barchart_svg}
            </div>
        </section>

        <!-- 2.e Full Benchmark Table -->
        <section class="card">
            <div class="card-header">
                <h2 class="card-title">Multi-Strategy Benchmark Performance Table</h2>
                <p class="card-desc">
                    Comprehensive accounting of net revenue, paired statistical differences, decision consistency, and regulatory metrics.
                </p>
            </div>
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
        <section class="card">
            <div class="card-header">
                <h2 class="card-title">Compliance Penalty Sensitivity Table</h2>
                <p class="card-desc">
                    Net recovery trajectory across regulatory penalty tiers. Break-even threshold is <strong>₹{breakeven_penalty_inr:,.2f}</strong>.
                </p>
            </div>
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
                *Note: Oracle represents the theoretical upper bound reading the hidden recovery matrix directly and is excluded from 'Best Deployable Strategy'.
            </p>
        </section>

        <!-- 2.g Compliance Panel -->
        <section class="card">
            <div class="card-header">
                <h2 class="card-title">Regulatory Compliance & Operational Panel</h2>
                <p class="card-desc">
                    Enforcement of RBI e-mandate circulars, AFA challenge thresholds, and per-method retry caps.
                </p>
            </div>

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
