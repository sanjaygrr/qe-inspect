"""Terminal, table and JSON output."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from typing import Optional, Union

from . import __version__
from .diagnostics import diagnose, status
from .model import Finding, PhRun, PwRun

STATUS_TEXT = {
    "ok": "OK",
    "warnings": "OK with warnings",
    "failed": "FAILED",
    "stopped": "STOPPED (max_seconds)",
    "crashed": "CRASHED",
    "incomplete": "INCOMPLETE",
}
COLORS = {"error": "31", "warning": "33", "info": "36", "ok": "32", "dim": "2", "bold": "1"}


@dataclass
class Report:
    run: Union[PwRun, PhRun]
    findings: list[Finding]
    status: str

    @classmethod
    def from_run(cls, run: Union[PwRun, PhRun]) -> "Report":
        findings = diagnose(run)
        return cls(run, findings, status(run, findings))

    def to_dict(self) -> dict:
        return {
            "qe_inspect_version": __version__,
            "file": self.run.path,
            "status": self.status,
            "findings": [asdict(f) for f in self.findings],
            "run": self.run.to_dict(),
        }


def use_color(stream=None) -> bool:
    stream = stream or sys.stdout
    return stream.isatty() and "NO_COLOR" not in os.environ


def _c(text: str, color: str, on: bool) -> str:
    return f"\033[{COLORS[color]}m{text}\033[0m" if on else text


def _status_color(st: str) -> str:
    return {"ok": "ok", "warnings": "warning", "stopped": "warning"}.get(st, "error")


def fmt_time(seconds: Optional[float]) -> str:
    if seconds is None:
        return "-"
    if seconds < 60:
        return f"{seconds:.1f} s"
    if seconds < 3600:
        return f"{seconds / 60:.1f} min"
    return f"{seconds / 3600:.2f} h"


def _num(value, fmt: str, unit: str = "") -> Optional[str]:
    if value is None:
        return None
    return f"{value:{fmt}}{(' ' + unit) if unit else ''}"


def summary_rows(run: Union[PwRun, PhRun]) -> list[tuple[str, str]]:
    rows: list[tuple[str, Optional[str]]] = []
    if isinstance(run, PwRun):
        if run.nat is not None:
            rows.append(("atoms / species", f"{run.nat} / {run.ntyp}"))
        if run.n_electrons is not None:
            rows.append(("electrons / bands", f"{run.n_electrons:g} / {run.n_bands}"))
        if run.ecutwfc is not None:
            cut = f"{run.ecutwfc:g} Ry (wfc), {run.ecutrho:g} Ry (rho)" if run.ecutrho else f"{run.ecutwfc:g} Ry"
            rows.append(("cutoffs", cut))
        if run.pseudo_types:
            rows.append(("pseudopotentials", ", ".join(sorted(set(run.pseudo_types)))))
        if run.xc:
            rows.append(("functional", run.xc))
        if run.n_kpoints is not None:
            occ = f" ({run.occupations})" if run.occupations else " (fixed occupations)"
            rows.append(("k-points", f"{run.n_kpoints}{occ}"))
        if run.conv_thr is not None:
            mix = f"mixing_beta {run.mixing_beta:g}" if run.mixing_beta is not None else ""
            if run.mixing_mode:
                mix += f" ({run.mixing_mode}, ndim {run.mixing_ndim})"
            rows.append(("conv_thr / mixing", f"{run.conv_thr:.1e} Ry / {mix}"))
        if run.scf_cycles:
            rows.append(("SCF cycles", f"{len(run.scf_cycles)} ({run.total_scf_iterations} iterations)"))
        if run.calculation in ("relax", "vc-relax", "md", "vc-md"):
            limit = f" of nstep = {run.nstep}" if run.nstep else ""
            rows.append(("ionic steps", f"{run.ionic_steps}{limit}"))
        energy = run.energy_ry
        if energy is not None:
            rows.append(("total energy", f"{energy:.8f} Ry"))
        elif run.final_cycle and run.final_cycle.iterations and run.final_cycle.iterations[-1].energy_ry is not None:
            rows.append(("total energy", f"{run.final_cycle.iterations[-1].energy_ry:.8f} Ry (last iteration, not converged)"))
        if run.final_enthalpy_ry is not None:
            rows.append(("final enthalpy/energy", f"{run.final_enthalpy_ry:.8f} Ry"))
        if run.fermi_energy_ev is not None:
            rows.append(("Fermi energy", f"{run.fermi_energy_ev:.4f} eV"))
        cyc = next((c for c in reversed(run.scf_cycles) if c.homo_ev is not None), None)
        if cyc is not None:
            gap = f", LUMO {cyc.lumo_ev:.4f} eV" if cyc.lumo_ev is not None else ""
            rows.append(("HOMO", f"{cyc.homo_ev:.4f} eV{gap}"))
        cyc = next((c for c in reversed(run.scf_cycles) if c.total_force is not None), None)
        if cyc is not None:
            rows.append(("total force", f"{cyc.total_force:.6f} Ry/bohr (SCF correction {cyc.scf_correction:.6f})"))
        cyc = next((c for c in reversed(run.scf_cycles) if c.pressure_kbar is not None), None)
        if cyc is not None:
            rows.append(("pressure", f"{cyc.pressure_kbar:.2f} kbar"))
    else:
        rows.append(("q points", str(len(run.q_points)) if run.q_points else "-"))
        reps = [r for r in run.representations if r.label != "electric field"]
        conv = sum(1 for r in reps if r.converged)
        rows.append(("representations", f"{len(reps)} ({conv} converged)"))
        if run.alpha_mix is not None:
            rows.append(("alpha_mix", f"{run.alpha_mix:g}"))
    rows.append(("wall time", fmt_time(run.wall_time_s)))
    return [(k, v) for k, v in rows if v is not None]


def render_text(report: Report, color: bool = False, verbose: bool = False) -> str:
    run = report.run
    out = []
    title = f"{run.program} {run.version or '?'}"
    calc = run.calculation or "unknown calculation"
    procs = f", {run.mpi_processes} MPI process{'es' if (run.mpi_processes or 0) > 1 else ''}" if run.mpi_processes else ""
    out.append(_c(run.path, "bold", color))
    out.append(f"{title} | {calc}{procs} | {run.n_lines} lines")
    st = report.status
    out.append("Status: " + _c(STATUS_TEXT[st], _status_color(st), color))
    out.append("")
    rows = summary_rows(run)
    width = max(len(k) for k, _ in rows)
    for k, v in rows:
        out.append(f"  {k.ljust(width)}  {v}")

    if isinstance(run, PwRun) and run.scf_cycles:
        out.append("")
        out.append(_c("SCF convergence", "bold", color))
        cycles = run.scf_cycles
        shown = cycles if verbose or len(cycles) <= 12 else cycles[:5] + [None] + cycles[-5:]
        out.append("  cycle  iters  last accuracy (Ry)  energy (Ry)          status")
        for cyc in shown:
            if cyc is None:
                out.append(f"  ... {len(cycles) - 10} more (use --verbose)")
                continue
            acc = cyc.accuracies[-1] if cyc.accuracies else None
            acc_s = f"{acc:.2e}" if acc is not None else "-"
            e = cyc.energy_ry
            if e is None and cyc.iterations:
                e = cyc.iterations[-1].energy_ry
            e_s = f"{e:.8f}" if e is not None else "-"
            stc = {True: "converged", False: "NOT converged", None: "unfinished"}[cyc.converged]
            if cyc.is_final_scf:
                stc += " (final scf)"
            out.append(f"  {cyc.index:<5}  {len(cyc.iterations):<5}  {acc_s:<18}  {e_s:<19}  {stc}")

    if isinstance(run, PhRun) and run.q_points:
        out.append("")
        out.append(_c("Frequencies (cm-1)", "bold", color))
        for q in run.q_points:
            freqs = " ".join(f"{f:.2f}" for f in q.frequencies_cm1)
            out.append(f"  q = ({q.q[0]:.4f}, {q.q[1]:.4f}, {q.q[2]:.4f}):  {freqs}")

    out.append("")
    hidden_codes = ("input_ignored", "qe_message")
    visible = [f for f in report.findings if verbose or not (f.severity == "info" and f.code in hidden_codes)]
    if not visible:
        out.append(_c("No problems found.", "ok", color))
    else:
        out.append(_c("Findings", "bold", color))
    for f in visible:
        tag = _c(f"[{f.severity.upper()}]", f.severity, color)
        loc = f" (line {f.line})" if f.line else ""
        out.append(f"  {tag} {f.title}{loc}")
        for para in _wrap(f.explanation, 74):
            out.append(f"      {para}")
        if f.evidence:
            out.append(_c(f"      > {f.evidence}", "dim", color))
        for s in f.suggestions:
            wrapped = _wrap(s, 70)
            out.append(f"      - {wrapped[0]}")
            out.extend(f"        {w}" for w in wrapped[1:])
    hidden = len(report.findings) - len(visible)
    if hidden and not verbose:
        out.append(_c(f"  ({hidden} informational message(s) hidden, use --verbose)", "dim", color))
    return "\n".join(out)


def _wrap(text: str, width: int) -> list[str]:
    import textwrap

    return textwrap.wrap(text, width) or [""]


def render_table(reports: list[Report], color: bool = False, base: Optional[str] = None) -> str:
    headers = ["file", "program", "calc", "status", "scf", "ionic", "energy (Ry)", "wall", "main issue"]
    rows = []
    for r in reports:
        run = r.run
        if isinstance(run, PwRun):
            scf = f"{len(run.scf_cycles)}/{run.total_scf_iterations}" if run.scf_cycles else "-"
            ionic = str(run.ionic_steps) if run.calculation in ("relax", "vc-relax", "md", "vc-md") else "-"
            energy = f"{run.energy_ry:.6f}" if run.energy_ry is not None else "-"
        else:
            reps = [x for x in run.representations if x.label != "electric field"]
            scf = f"{len(reps)} irr" if reps else "-"
            ionic = "-"
            energy = "-"
        issue = next((f.title for f in r.findings if f.severity in ("error", "warning")), "")
        name = os.path.relpath(run.path, base) if base else run.path
        rows.append(
            [name, run.program, run.calculation or "?", STATUS_TEXT[r.status], scf, ionic, energy, fmt_time(run.wall_time_s), issue]
        )
    widths = [max(len(h), *(len(row[i]) for row in rows)) if rows else len(h) for i, h in enumerate(headers)]
    widths[-1] = len(headers[-1])
    lines = ["  ".join(h.ljust(w) for h, w in zip(headers, widths)).rstrip()]
    lines.append("  ".join("-" * w for w in widths))
    for row, r in zip(rows, reports):
        cells = [c.ljust(w) for c, w in zip(row, widths)]
        cells[3] = _c(cells[3], _status_color(r.status), color)
        lines.append("  ".join(cells).rstrip())
    counts: dict[str, int] = {}
    for r in reports:
        counts[r.status] = counts.get(r.status, 0) + 1
    lines.append("")
    lines.append(f"{len(reports)} run(s): " + ", ".join(f"{v} {STATUS_TEXT[k]}" for k, v in counts.items()))
    return "\n".join(lines)


def render_json(reports: Union[Report, list[Report]]) -> str:
    if isinstance(reports, Report):
        return json.dumps(reports.to_dict(), indent=2)
    return json.dumps([r.to_dict() for r in reports], indent=2)
