"""Self-contained HTML report with inline SVG charts (no external assets)."""

from __future__ import annotations

import math
from html import escape
from typing import Optional

from . import __version__
from .model import PhRun, PwRun
from .report import STATUS_TEXT, Report, summary_rows

CSS = """
:root { --bg:#f6f5f2; --card:#ffffff; --ink:#1d2329; --muted:#5d6b78; --line:#d9dde1;
  --accent:#1f5f8b; --err:#b42318; --warn:#a15c07; --info:#2f6f8f; --ok:#1e7a46; --grid:#e8eaed; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#14181c; --card:#1c2228; --ink:#e6e9ec; --muted:#9aa7b3; --line:#2e3740;
    --accent:#6fb3e0; --err:#f07a6e; --warn:#e5a54b; --info:#7cc0de; --ok:#5cc08a; --grid:#262e36; }
}
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
  font: 16px/1.5 -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
main { max-width: 980px; margin: 0 auto; padding: 28px 16px 64px; }
header { margin-bottom: 20px; }
h1 { font-size: 1.15rem; margin: 0 0 4px; word-break: break-all; font-family: ui-monospace, Menlo, Consolas, monospace; }
.sub { color: var(--muted); }
.badge { display:inline-block; padding: 3px 10px; border-radius: 4px; font-weight: 600; font-size: .9rem;
  color: #fff; margin-top: 10px; letter-spacing: .02em; }
.s-ok { background: var(--ok); } .s-warnings, .s-stopped { background: var(--warn); }
.s-failed, .s-crashed, .s-incomplete { background: var(--err); }
section { background: var(--card); border: 1px solid var(--line); border-radius: 6px; padding: 18px 20px; margin: 16px 0; }
h2 { font-size: 1rem; margin: 0 0 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
table { border-collapse: collapse; width: 100%; font-size: .95rem; }
td, th { text-align: left; padding: 5px 8px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { color: var(--muted); font-weight: 600; }
td.k { color: var(--muted); width: 34%; }
.num { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: .9rem; }
.finding { border-left: 4px solid var(--info); padding: 8px 0 8px 14px; margin: 12px 0; }
.finding.error { border-color: var(--err); } .finding.warning { border-color: var(--warn); }
.finding h3 { margin: 0 0 4px; font-size: 1rem; }
.sev { font-size: .75rem; font-weight: 700; letter-spacing: .06em; margin-right: 8px; }
.error .sev { color: var(--err); } .warning .sev { color: var(--warn); } .info .sev { color: var(--info); }
.finding p { margin: 4px 0; }
.evidence { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: .85rem; color: var(--muted);
  background: var(--bg); padding: 4px 8px; border-radius: 4px; overflow-x: auto; white-space: pre-wrap; }
.finding ul { margin: 6px 0 0; padding-left: 20px; }
.chart { width: 100%; height: auto; display: block; }
.chart text { fill: var(--muted); font-size: 12px; font-family: inherit; }
.chart .axis { stroke: var(--line); }
.chart .gridl { stroke: var(--grid); }
.chart .thr { stroke: var(--ok); stroke-dasharray: 5 4; }
.chart .sep { stroke: var(--line); stroke-dasharray: 2 3; }
.legend { color: var(--muted); font-size: .85rem; margin-top: 6px; }
.scroll { overflow-x: auto; }
footer { color: var(--muted); font-size: .85rem; margin-top: 24px; }
"""

PALETTE = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf", "#8c564b", "#e377c2"]


def _fmt_log_tick(v: float) -> str:
    return f"1e{int(round(v))}"


def svg_chart(
    series: list[tuple[str, list[tuple[float, float]], str]],
    *,
    log_y: bool = False,
    hline: Optional[float] = None,
    vlines: Optional[list[float]] = None,
    xlabel: str = "",
    ylabel: str = "",
    width: int = 900,
    height: int = 320,
) -> str:
    """Minimal line chart. ``series`` items are (label, points, color)."""
    pts_all = [(x, y) for _, pts, _ in series for x, y in pts if y is not None and (not log_y or y > 0)]
    if not pts_all:
        return ""

    def ty(y: float) -> float:
        return math.log10(y) if log_y else y

    xs = [p[0] for p in pts_all]
    ys = [ty(p[1]) for p in pts_all]
    if hline is not None and (not log_y or hline > 0):
        ys.append(ty(hline))
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    if x1 == x0:
        x0, x1 = x0 - 1, x1 + 1
    if y1 == y0:
        y0, y1 = y0 - 1, y1 + 1
    if log_y:
        y0, y1 = math.floor(y0), math.ceil(y1)
    else:
        pad = 0.06 * (y1 - y0)
        y0, y1 = y0 - pad, y1 + pad
    ml, mr, mt, mb = 70, 16, 12, 44
    pw, ph = width - ml - mr, height - mt - mb

    def sx(x: float) -> float:
        return ml + (x - x0) / (x1 - x0) * pw

    def sy(y: float) -> float:
        return mt + (1 - (y - y0) / (y1 - y0)) * ph

    parts = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" xmlns="http://www.w3.org/2000/svg">']
    # y grid and ticks
    if log_y:
        span = int(y1 - y0)
        step = max(1, math.ceil(span / 8))
        ticks = [y0 + k for k in range(0, span + 1, step)]
        labels = [_fmt_log_tick(t) for t in ticks]
    else:
        ticks = [y0 + k * (y1 - y0) / 5 for k in range(6)]
        labels = [f"{t:.4g}" for t in ticks]
    for t, lab in zip(ticks, labels):
        yy = sy(t)
        parts.append(f'<line class="gridl" x1="{ml}" x2="{ml + pw}" y1="{yy:.1f}" y2="{yy:.1f}"/>')
        parts.append(f'<text x="{ml - 8}" y="{yy + 4:.1f}" text-anchor="end">{escape(lab)}</text>')
    # x ticks
    nx = min(10, int(x1 - x0) or 1)
    for k in range(nx + 1):
        xv = x0 + k * (x1 - x0) / nx
        xx = sx(xv)
        parts.append(f'<text x="{xx:.1f}" y="{mt + ph + 18}" text-anchor="middle">{xv:.0f}</text>')
    parts.append(f'<line class="axis" x1="{ml}" x2="{ml + pw}" y1="{mt + ph}" y2="{mt + ph}"/>')
    parts.append(f'<line class="axis" x1="{ml}" x2="{ml}" y1="{mt}" y2="{mt + ph}"/>')
    for v in vlines or []:
        xx = sx(v)
        parts.append(f'<line class="sep" x1="{xx:.1f}" x2="{xx:.1f}" y1="{mt}" y2="{mt + ph}"/>')
    if hline is not None and (not log_y or hline > 0):
        yy = sy(ty(hline))
        parts.append(f'<line class="thr" x1="{ml}" x2="{ml + pw}" y1="{yy:.1f}" y2="{yy:.1f}"/>')
    for label, pts, color in series:
        good = [(x, ty(y)) for x, y in pts if y is not None and (not log_y or y > 0)]
        if not good:
            continue
        path = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in good)
        parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="1.8" points="{path}"><title>{escape(label)}</title></polyline>')
        if len(good) <= 400:
            for x, y in good:
                parts.append(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="2.6" fill="{color}"/>')
    parts.append(f'<text x="{ml + pw / 2:.0f}" y="{height - 6}" text-anchor="middle">{escape(xlabel)}</text>')
    parts.append(
        f'<text x="14" y="{mt + ph / 2:.0f}" text-anchor="middle" transform="rotate(-90 14 {mt + ph / 2:.0f})">{escape(ylabel)}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def _pw_charts(run: PwRun) -> str:
    out = []
    series, vlines = [], []
    offset = 0
    for k, cyc in enumerate(run.scf_cycles):
        pts = []
        for j, it in enumerate(cyc.iterations):
            if it.accuracy_ry is not None:
                pts.append((offset + j + 1, it.accuracy_ry))
        if pts:
            label = f"SCF cycle {cyc.index}" + (" (final scf)" if cyc.is_final_scf else "")
            series.append((label, pts, PALETTE[k % 2]))
        if k > 0:
            vlines.append(offset + 0.5)
        offset += len(cyc.iterations)
    chart = svg_chart(
        series,
        log_y=True,
        hline=run.conv_thr,
        vlines=vlines,
        xlabel="SCF iteration (cumulative over ionic steps)" if len(run.scf_cycles) > 1 else "SCF iteration",
        ylabel="estimated scf accuracy (Ry)",
    )
    if chart:
        legend = "Dashed green line: conv_thr."
        if len(run.scf_cycles) > 1:
            legend += " Dotted vertical lines separate SCF cycles (ionic steps)."
        out.append(f"<section><h2>SCF convergence</h2>{chart}<div class='legend'>{legend}</div></section>")

    steps = [c for c in run.scf_cycles if not c.is_final_scf and c.energy_ry is not None]
    if len(steps) >= 2:
        e_last = steps[-1].energy_ry
        pts = [(c.index, (c.energy_ry - e_last) * 1000) for c in steps]
        chart = svg_chart(
            [("energy", pts, PALETTE[0])],
            xlabel="ionic step",
            ylabel="E - E(last step) (mRy)",
            height=260,
        )
        out.append(f"<section><h2>Energy along the ionic steps</h2>{chart}</section>")
        gpts = [(c.index, c.bfgs_gradient_error) for c in steps if c.bfgs_gradient_error]
        fpts = [(c.index, c.total_force) for c in steps if c.total_force]
        if len(gpts) >= 2:
            chart = svg_chart(
                [("BFGS gradient error", gpts, PALETTE[1])],
                log_y=True,
                hline=run.forc_conv_thr,
                xlabel="ionic step",
                ylabel="gradient error (Ry/bohr)",
                height=260,
            )
            out.append(
                f"<section><h2>BFGS gradient error along the ionic steps</h2>{chart}"
                "<div class='legend'>Largest force component as checked by BFGS. Dashed green line: forc_conv_thr.</div></section>"
            )
        elif len(fpts) >= 2:
            chart = svg_chart(
                [("total force", fpts, PALETTE[1])],
                log_y=True,
                xlabel="ionic step",
                ylabel="total force (Ry/bohr)",
                height=260,
            )
            out.append(f"<section><h2>Total force along the ionic steps</h2>{chart}</section>")
    return "".join(out)


def _ph_charts(run: PhRun) -> str:
    series, vlines = [], []
    offset = 0
    for k, rep in enumerate(run.representations):
        pts = [(offset + j + 1, it.dvscf) for j, it in enumerate(rep.iterations) if it.dvscf is not None]
        if pts:
            series.append((f"q{rep.q_index} {rep.label}", pts, PALETTE[k % 2]))
        if k > 0 and rep.iterations:
            vlines.append(offset + 0.5)
        offset += len(rep.iterations)
    chart = svg_chart(
        series,
        log_y=True,
        vlines=vlines,
        xlabel="linear-response iteration (cumulative over representations)",
        ylabel="|ddv_scf|^2",
    )
    out = ""
    if chart:
        out += f"<section><h2>Linear-response convergence (experimental)</h2>{chart}</section>"
    if run.q_points:
        rows = "".join(
            f"<tr><td class='num'>({q.q[0]:.4f}, {q.q[1]:.4f}, {q.q[2]:.4f})</td>"
            f"<td class='num'>{' '.join(f'{f:.2f}' for f in q.frequencies_cm1)}</td></tr>"
            for q in run.q_points
        )
        out += (
            "<section><h2>Frequencies (cm<sup>-1</sup>)</h2><div class='scroll'><table>"
            f"<tr><th>q (2&pi;/a)</th><th>frequencies</th></tr>{rows}</table></div></section>"
        )
    return out


def _scf_table(run: PwRun) -> str:
    if not run.scf_cycles:
        return ""
    rows = []
    for cyc in run.scf_cycles:
        acc = cyc.accuracies[-1] if cyc.accuracies else None
        e = cyc.energy_ry
        st = {True: "converged", False: "NOT converged", None: "unfinished"}[cyc.converged]
        if cyc.is_final_scf:
            st += " (final scf)"
        cells = [
            str(cyc.index),
            str(len(cyc.iterations)),
            f"{acc:.2e}" if acc is not None else "-",
            f"{e:.8f}" if e is not None else "-",
            f"{cyc.total_force:.6f}" if cyc.total_force is not None else "-",
            f"{cyc.pressure_kbar:.2f}" if cyc.pressure_kbar is not None else "-",
            st,
        ]
        rows.append("<tr>" + "".join(f"<td class='num'>{escape(c)}</td>" for c in cells) + "</tr>")
    head = "".join(
        f"<th>{h}</th>" for h in ["cycle", "iters", "last accuracy (Ry)", "energy (Ry)", "total force", "P (kbar)", "status"]
    )
    return f"<section><h2>SCF cycles</h2><div class='scroll'><table><tr>{head}</tr>{''.join(rows)}</table></div></section>"


def render_html(report: Report) -> str:
    run = report.run
    st = report.status
    calc = run.calculation or "unknown calculation"
    procs = f" &middot; {run.mpi_processes} MPI process(es)" if run.mpi_processes else ""
    summary = "".join(
        f"<tr><td class='k'>{escape(k)}</td><td>{escape(v)}</td></tr>" for k, v in summary_rows(run)
    )
    findings = []
    for f in report.findings:
        sugg = "".join(f"<li>{escape(s)}</li>" for s in f.suggestions)
        loc = f" <span class='sub'>(line {f.line})</span>" if f.line else ""
        ev = f"<div class='evidence'>{escape(f.evidence)}</div>" if f.evidence else ""
        findings.append(
            f"<div class='finding {f.severity}'><h3><span class='sev'>{f.severity.upper()}</span>"
            f"{escape(f.title)}{loc}</h3><p>{escape(f.explanation)}</p>{ev}"
            + (f"<ul>{sugg}</ul>" if sugg else "")
            + "</div>"
        )
    findings_html = "".join(findings) or "<p>No problems found.</p>"
    charts = _pw_charts(run) if isinstance(run, PwRun) else _ph_charts(run)
    table = _scf_table(run) if isinstance(run, PwRun) else ""
    note = " (ph.x support is experimental)" if isinstance(run, PhRun) else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>qe-inspect: {escape(run.path.split('/')[-1])}</title>
<style>{CSS}</style></head>
<body><main>
<header>
<h1>{escape(run.path)}</h1>
<div class="sub">{escape(run.program)} {escape(run.version or '?')} &middot; {escape(calc)}{procs} &middot; {run.n_lines} lines{note}</div>
<span class="badge s-{st}">{escape(STATUS_TEXT[st])}</span>
</header>
<section><h2>Findings</h2>{findings_html}</section>
{charts}
<section><h2>Summary</h2><table>{summary}</table></section>
{table}
<footer>qe-inspect {__version__}</footer>
</main></body></html>
"""
