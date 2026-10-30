"""Turn a parsed run into findings: what went wrong, why, and what to try.

Explanations are deliberately short. Thresholds quoted from QE refer to
QE 7.x source (PW/src/electrons.f90, PW/src/c_bands.f90, PW/src/forces.f90).
Anything that is a rule of thumb rather than a QE check is labelled as such.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Union

from .model import Finding, Message, PhRun, PwRun, ScfCycle

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


# --------------------------------------------------------------------------
# SCF trend analysis
# --------------------------------------------------------------------------


@dataclass
class ScfTrend:
    kind: str  # converging, oscillating, stagnating, too_short
    n: int
    rise_fraction: float
    decades_per_iteration: float


def scf_trend(accuracies: list[float], window: int = 15) -> ScfTrend:
    """Classify the behaviour of the estimated SCF accuracy.

    ``oscillating``: the accuracy goes up in at least 35 % of the recent
    iterations. ``stagnating``: less than one decade of improvement over
    eight or more iterations. Both thresholds are heuristics.
    """
    values = [a for a in accuracies if a is not None and a > 0][-window:]
    n = len(values)
    if n < 4:
        rate = 0.0
        if n >= 2:
            rate = (math.log10(values[0]) - math.log10(values[-1])) / (n - 1)
        return ScfTrend("too_short", n, 0.0, rate)
    logs = [math.log10(v) for v in values]
    rises = sum(1 for a, b in zip(logs, logs[1:]) if b > a + 0.05)
    rise_fraction = rises / (n - 1)
    gain = logs[0] - logs[-1]
    rate = gain / (n - 1)
    if rise_fraction >= 0.35:
        kind = "oscillating"
    elif n >= 8 and gain < 1.0:
        kind = "stagnating"
    else:
        kind = "converging"
    return ScfTrend(kind, n, rise_fraction, rate)


# --------------------------------------------------------------------------
# Known fatal errors
# --------------------------------------------------------------------------

_KNOWN_ERRORS = [
    (
        ("s matrix not positive definite", "problems computing cholesky"),
        "Diagonalization failed: overlap matrix not positive definite",
        "The iterative diagonalization solves H psi = e S psi and needs a Cholesky "
        "factorization of the overlap matrix S in the subspace of trial vectors. "
        "It failed, which means that subspace became (nearly) linearly dependent. "
        "The most common cause is atoms that are too close, often a units mistake in "
        "ATOMIC_POSITIONS or CELL_PARAMETERS. Other causes are numerical problems in "
        "the Davidson solver and, with ultrasoft/PAW pseudopotentials, an overlap "
        "operator S that is badly conditioned (problematic pseudopotential or low ecutrho).",
        [
            "Check the structure: minimum interatomic distances and the units of the positions and cell.",
            "Switch the solver to diagonalization = 'cg' (slower but more robust).",
            "With the Davidson solver, try a smaller diago_david_ndim (e.g. 2).",
            "With ultrasoft/PAW pseudopotentials, try another pseudopotential or a higher ecutrho.",
            "If it only happens in parallel runs, test with fewer MPI processes or another linear-algebra library.",
        ],
    ),
    (
        ("charge is wrong: smearing is needed",),
        "Wrong number of electrons with fixed occupations",
        "After the SCF the integrated charge differed from the number of electrons "
        "by more than 1e-3 (relative), and occupations are fixed. With fixed occupations "
        "the electrons must fill an integer number of bands, so this usually means a metal "
        "run as an insulator, or an open-shell system (e.g. an odd number of electrons "
        "without spin polarization).",
        [
            "For a metal: occupations = 'smearing', e.g. smearing = 'mv' and degauss = 0.01-0.02 Ry as a starting value to test.",
            "For an open-shell system: nspin = 2 with starting_magnetization (or tot_magnetization if the moment is known).",
            "Check tot_charge and the number of valence electrons of each pseudopotential.",
        ],
    ),
    (
        ("charge is wrong",),
        "Integrated charge does not match the number of electrons",
        "The charge integrated on the FFT grid differed from the number of electrons "
        "by more than 1e-3 (relative). Typical causes are an ecutrho that is too low "
        "for ultrasoft/PAW pseudopotentials, a large negative charge density, an "
        "unstable SCF, or inconsistent tot_charge or pseudopotentials.",
        [
            "Raise ecutrho (ultrasoft/PAW pseudopotentials usually need 8-12 x ecutwfc).",
            "Check tot_charge, starting_magnetization and the pseudopotentials.",
            "If the SCF was unstable, reduce mixing_beta.",
        ],
    ),
    (
        ("too many bands are not converged",),
        "Too many bands did not converge in the diagonalization",
        "In one SCF step the iterative solver left more than max(5, nbnd/4) "
        "eigenvalues unconverged, and pw.x stops. This often points to a bad "
        "geometry, a difficult starting point, or a solver problem.",
        [
            "Try diagonalization = 'cg' or a different diago_david_ndim.",
            "Check the structure for overlapping or badly placed atoms.",
            "Start from a better guess (startingwfc = 'atomic+random') or from a converged run.",
        ],
    ),
    (
        ("too few bands",),
        "nbnd is smaller than the number of occupied bands",
        "The number of Kohn-Sham states (nbnd) cannot hold all the electrons. "
        "Without spin polarization each band holds two electrons, so at least nelec/2 "
        "bands are needed (with spin, enough for the larger spin channel); with "
        "smearing, pw.x also needs some empty bands above the Fermi level.",
        [
            "Remove nbnd from the input to use the pw.x default, or increase it.",
        ],
    ),
]


def _explain_error(err: Message, program: str) -> Finding:
    text = err.text.lower()
    evidence = f"Error in routine {err.routine} ({err.code}): {err.text}"
    for keys, title, explanation, suggestions in _KNOWN_ERRORS:
        if any(k in text for k in keys):
            return Finding("error", "crash", title, explanation, list(suggestions), evidence, err.line)
    return Finding(
        "error",
        "crash",
        f"{program} stopped with an error in routine {err.routine}",
        f"{program} raised a fatal error: \"{err.text}\". The routine name and "
        "message usually point to the input variable or file involved.",
        [
            f"Search the message in the {program} input documentation and the QE users mailing list.",
        ],
        evidence,
        err.line,
    )


def _incomplete(run: Union[PwRun, PhRun], where: str) -> Finding:
    explanation = (
        f"The output ends {where} without 'JOB DONE.' and without a QE error "
        "message. The job was most likely killed from outside (batch wall-time "
        "limit, out of memory, node failure) or it is still running."
    )
    suggestions = [
        "Check the scheduler log and the job's stderr for the reason it stopped.",
        "Set max_seconds a bit below the wall-time limit so pw.x stops cleanly and can be restarted.",
    ]
    evidence = f"last line: {run.last_line[:120]}" if run.last_line else None
    if run.abort_marker:
        explanation = (
            "The output ends without 'JOB DONE.' and the MPI runtime or batch "
            f"system reported an abort ({run.abort_marker!r}). QE did not print "
            f"an error block to standard output; the stop happened {where}."
        )
        suggestions = [
            "Look for a file named CRASH in the directory the job ran in; QE writes fatal errors there.",
            "Check the job's stderr and the scheduler log.",
            "If it fails inside the diagonalization, try diagonalization = 'cg'.",
        ]
        evidence = run.abort_marker
    return Finding("error", "incomplete", "Run did not finish", explanation, suggestions, evidence)


def _where_pw(run: PwRun) -> str:
    cyc = run.final_cycle
    if cyc is None:
        return "before the first SCF iteration"
    it = cyc.iterations[-1].number if cyc.iterations else 0
    if run.calculation in ("relax", "vc-relax", "md", "vc-md") and len(run.scf_cycles) > 1:
        return f"during SCF iteration {it} of ionic step {cyc.index}"
    return f"during SCF iteration {it}"


def _multi_run(run: Union[PwRun, PhRun]) -> Optional[Finding]:
    if run.runs_in_file <= 1:
        return None
    return Finding(
        "info",
        "several_runs",
        f"The file contains {run.runs_in_file} runs",
        "Several runs were written to the same file (e.g. a restart appended with >>). "
        "Only the last one is analysed.",
    )


# --------------------------------------------------------------------------
# pw.x
# --------------------------------------------------------------------------


def _scf_not_converged(run: PwRun, cyc: ScfCycle) -> Finding:
    trend = scf_trend(cyc.accuracies)
    acc = cyc.accuracies[-1] if cyc.accuracies else None
    n_it = cyc.reported_iterations or len(cyc.iterations)
    where = f" (ionic step {cyc.index})" if len(run.scf_cycles) > 1 else ""
    evidence = f"convergence NOT achieved after {n_it} iterations"
    if acc is not None and run.conv_thr:
        evidence += f"; last estimated accuracy {acc:.1e} Ry vs conv_thr {run.conv_thr:.1e}"
    beta = f" (now {run.mixing_beta:g})" if run.mixing_beta else ""
    smearing = run.occupations and "smearing" in run.occupations.lower()

    if trend.kind == "too_short" or (n_it < 10 and trend.kind == "converging"):
        explanation = (
            f"The SCF{where} stopped after only {n_it} iteration(s), which is the "
            "electron_maxstep limit. The accuracy was still decreasing, so the "
            "limit is probably just too small."
        )
        if trend.kind == "too_short" and trend.n < 2:
            explanation = (
                f"The SCF{where} stopped after {n_it} iteration(s), the electron_maxstep "
                "limit. Too few iterations to judge the trend; this can be intentional "
                "(e.g. one-shot runs), otherwise raise the limit."
            )
        suggestions = ["Increase electron_maxstep (default 100)."]
    elif trend.kind == "oscillating":
        explanation = (
            f"The SCF{where} did not converge in {n_it} iterations and the estimated "
            f"accuracy goes up and down ({trend.rise_fraction:.0%} of recent steps "
            "increase). This usually means the density mixing is too aggressive (charge "
            "sloshing), but level crossings near the Fermi level or a magnetic or DFT+U "
            "density that keeps switching produce the same pattern."
        )
        suggestions = [
            f"Reduce mixing_beta{beta}, e.g. to 0.3 or 0.1.",
            "Increase mixing_ndim (e.g. 12-16).",
            "For slabs, surfaces or inhomogeneous systems use mixing_mode = 'local-TF'.",
        ]
        if smearing:
            suggestions.insert(
                0,
                "For a metal, check the setup first: a k-point mesh dense enough for the "
                "smearing width, a degauss that is not too small, and enough empty bands.",
            )
        else:
            suggestions.append(
                "If the system may be metallic, use occupations = 'smearing' and a few extra bands."
            )
        suggestions.append("Check the geometry; strongly distorted structures are hard to converge.")
    elif trend.kind == "stagnating":
        explanation = (
            f"The SCF{where} did not converge in {n_it} iterations and the accuracy "
            "has stalled (less than one decade of improvement over the last "
            f"{trend.n} iterations)."
        )
        suggestions = [
            f"Reduce mixing_beta{beta} and increase mixing_ndim.",
            "Restart from a different starting density or wavefunctions (startingwfc = 'atomic+random').",
            "If the accuracy sits at a floor (often around 1e-8 to 1e-10 Ry for large ultrasoft/PAW cells), "
            "that is numerical noise: set conv_thr just above it.",
        ]
        if smearing:
            suggestions.append("For a metal, check that the k-point mesh and degauss are adequate.")
        else:
            suggestions.append("If the system may be metallic, use occupations = 'smearing'.")
    else:
        need = ""
        if acc and run.conv_thr and trend.decades_per_iteration > 0:
            remaining = (math.log10(acc) - math.log10(run.conv_thr)) / trend.decades_per_iteration
            if remaining > 0:
                need = f" At the recent rate it needs roughly {math.ceil(remaining)} more iterations."
        explanation = (
            f"The SCF{where} did not converge in {n_it} iterations, but the accuracy "
            f"was still improving steadily.{need}"
        )
        suggestions = [
            "Increase electron_maxstep.",
            "A larger mixing_ndim can speed up slow but steady convergence.",
        ]
    return Finding("error", "scf_not_converged", "SCF did not converge", explanation, suggestions, evidence, cyc.line)


def _scf_noisy(run: PwRun) -> Optional[Finding]:
    worst = None
    for cyc in run.scf_cycles:
        if cyc.converged and len(cyc.iterations) >= 30:
            trend = scf_trend(cyc.accuracies)
            if trend.kind == "oscillating" and (worst is None or len(cyc.iterations) > len(worst.iterations)):
                worst = cyc
    if worst is None:
        return None
    beta = f" (now {run.mixing_beta:g})" if run.mixing_beta else ""
    return Finding(
        "warning",
        "scf_oscillating",
        "SCF converged, but slowly and with oscillations",
        f"SCF cycle {worst.index} needed {len(worst.iterations)} iterations and its "
        "accuracy oscillated. It converged, but the mixing is probably too aggressive.",
        [f"Reduce mixing_beta{beta} or use mixing_mode = 'local-TF' for inhomogeneous systems."],
        None,
        worst.line,
    )


def _relax(run: PwRun) -> list[Finding]:
    out = []
    steps = [c for c in run.scf_cycles if not c.is_final_scf]
    last = steps[-1] if steps else None
    detail = ""
    if last is not None and last.bfgs_gradient_error is not None:
        detail = f" Last BFGS gradient error: {last.bfgs_gradient_error:.1e} Ry/bohr"
        if run.forc_conv_thr:
            detail += f" (forc_conv_thr = {run.forc_conv_thr:g})"
        detail += "."
        if last.bfgs_energy_error is not None:
            detail += f" Last energy error: {last.bfgs_energy_error:.1e} Ry"
            if run.etot_conv_thr:
                detail += f" (etot_conv_thr = {run.etot_conv_thr:g})"
            detail += "."
    elif last is not None and last.total_force is not None:
        detail = f" Last total force: {last.total_force:.6f} Ry/bohr"
        if run.forc_conv_thr:
            detail += (
                f" (forc_conv_thr = {run.forc_conv_thr:g} applies to the largest force "
                "component, the total force is the norm over all atoms)"
            )
        detail += "."
        if len(steps) >= 2 and steps[-1].energy_ry is not None and steps[-2].energy_ry is not None:
            de = abs(steps[-1].energy_ry - steps[-2].energy_ry)
            detail += f" Energy change in the last step: {de:.2e} Ry"
            if run.etot_conv_thr:
                detail += f" (etot_conv_thr = {run.etot_conv_thr:g})"
            detail += "."
    if run.calculation in ("relax", "vc-relax") and run.ionic_status == "max_steps":
        out.append(
            Finding(
                "error",
                "relax_max_steps",
                "Geometry optimization hit nstep before converging",
                f"The {run.calculation} stopped after {len(steps)} ionic steps because it "
                f"reached nstep = {run.nstep}.{detail}",
                [
                    "Increase nstep and restart from the last ATOMIC_POSITIONS (and CELL_PARAMETERS) printed in this output.",
                    "If forces stall instead of decreasing, tighten conv_thr: noisy forces slow down BFGS.",
                ],
                "The maximum number of steps has been reached.",
                run.ionic_status_line,
            )
        )
    elif run.ionic_status == "bfgs_failed":
        out.append(
            Finding(
                "error",
                "relax_bfgs_failed",
                "BFGS gave up before converging",
                "BFGS reset its history and still could not lower the energy. This "
                "usually happens when energies and forces are not consistent, because the "
                f"SCF is not converged tightly enough or the thresholds are below the numerical noise.{detail}",
                [
                    "Tighten conv_thr (e.g. 1e-8 to 1e-10) so forces are accurate.",
                    "Loosen etot_conv_thr / forc_conv_thr if they are tighter than needed.",
                    "Restart from the last geometry, or try ion_dynamics = 'damp' (or 'fire' in recent versions).",
                ],
                "bfgs failed after ...",
                run.ionic_status_line,
            )
        )
    elif (
        run.calculation in ("relax", "vc-relax")
        and run.job_done
        and run.ionic_status is None
        and run.error is None
        and not run.walltime_reached
        and not any(c.converged is False for c in run.scf_cycles)
    ):
        out.append(
            Finding(
                "warning",
                "relax_status_unknown",
                "Could not tell whether the relaxation converged",
                "The run finished but no convergence or failure message of the ionic "
                "minimizer was found.",
                ["Check the end of the ionic loop in the output by hand."],
            )
        )

    finals = [c for c in run.scf_cycles if c.is_final_scf]
    if run.calculation == "vc-relax" and finals and steps:
        p_final, p_last = finals[-1].pressure_kbar, steps[-1].pressure_kbar
        thr = run.press_conv_thr or 0.5
        if p_final is not None and p_last is not None and abs(p_final - p_last) > max(1.0, thr):
            out.append(
                Finding(
                    "warning",
                    "vcrelax_final_pressure",
                    "Pressure jumped in the final SCF",
                    f"The last relaxation step had P = {p_last:.2f} kbar, the final SCF at the "
                    f"relaxed cell gives P = {p_final:.2f} kbar. The final SCF rebuilds the "
                    "plane-wave basis for the new cell, so the jump is Pulay stress from an "
                    "incomplete basis set.",
                    [
                        "Increase ecutwfc (and ecutrho) and run another vc-relax starting from the final structure.",
                    ],
                )
            )
    return out


def _cutoffs(run: PwRun) -> Optional[Finding]:
    if not run.ecutwfc or not run.ecutrho:
        return None
    dual = run.ecutrho / run.ecutwfc
    types = " ".join(run.pseudo_types).lower()
    augmented = "ultrasoft" in types or "projector" in types or "paw" in types
    if augmented and dual < 8:
        return Finding(
            "info",
            "cutoff_ratio",
            f"ecutrho is {dual:g} x ecutwfc with ultrasoft/PAW pseudopotentials",
            "Rule of thumb, not a QE check: ultrasoft and PAW pseudopotentials usually "
            "need ecutrho of about 8-12 x ecutwfc to describe the augmentation charges. "
            "Check the cutoffs suggested in the pseudopotential files and test convergence.",
            ["Test total energy and forces against higher ecutrho."],
            f"ecutwfc = {run.ecutwfc:g} Ry, ecutrho = {run.ecutrho:g} Ry",
        )
    if not augmented and run.pseudo_types and dual < 4:
        return Finding(
            "info",
            "cutoff_ratio",
            f"ecutrho is {dual:g} x ecutwfc with norm-conserving pseudopotentials",
            "With norm-conserving pseudopotentials the density needs ecutrho = 4 x "
            "ecutwfc to be represented exactly; a smaller value loses accuracy.",
            ["Use ecutrho = 4 x ecutwfc (the default) unless you know why not."],
            f"ecutwfc = {run.ecutwfc:g} Ry, ecutrho = {run.ecutrho:g} Ry",
        )
    return None


def diagnose_pw(run: PwRun) -> list[Finding]:
    findings: list[Finding] = []
    if run.error is not None:
        findings.append(_explain_error(run.error, "pw.x"))
    elif run.walltime_reached:
        findings.append(
            Finding(
                "warning",
                "max_seconds",
                "Stopped by max_seconds",
                f"pw.x stopped itself because the max_seconds limit was reached ({_where_pw(run)}). "
                "It writes restart data before stopping.",
                [
                    "Rerun with restart_mode = 'restart' and the same prefix and outdir to continue.",
                    "Increase max_seconds if the batch wall-time allows it.",
                ],
                "Maximum CPU time exceeded",
            )
        )
    elif not run.job_done:
        findings.append(_incomplete(run, _where_pw(run)))

    for cyc in run.scf_cycles:
        if cyc.converged is False:
            findings.append(_scf_not_converged(run, cyc))
            break
    noisy = _scf_noisy(run)
    if noisy:
        findings.append(noisy)

    findings.extend(_relax(run))

    if run.scf_correction_warnings:
        findings.append(
            Finding(
                "warning",
                "scf_correction_large",
                "Forces are not accurate: SCF correction is large",
                "The SCF correction to the forces is more than 10 % of the forces themselves "
                f"(printed {run.scf_correction_warnings} time(s)), so the forces carry "
                "noticeable SCF error. In a relaxation this can stall or mislead the optimizer.",
                ["Lower conv_thr by one or two orders of magnitude."],
                "SCF correction compared to forces is large: reduce conv_thr to get better values",
            )
        )

    if run.integrated_charge is not None and (run.error is None or "charge" not in run.error.text):
        got, expected = run.integrated_charge
        rel = abs(got - expected) / abs(got) if got else 0.0
        findings.append(
            Finding(
                "warning" if rel > 1e-3 else "info",
                "integrated_charge",
                "Integrated charge differs from the number of electrons",
                f"Largest deviation: {got:.8f} vs {expected:.8f} (relative {rel:.1e}). "
                "pw.x prints this warning when the relative difference exceeds 1e-7 and stops "
                "with 'charge is wrong' above 1e-3, so small values are tolerated by QE itself.",
                ["If the deviation is large or grows between iterations, check ecutrho and the occupations."],
            )
        )

    n_cb = sum(it.unconverged_bands_warnings for c in run.scf_cycles for it in c.iterations)
    if n_cb:
        n_it = max(run.total_scf_iterations, 1)
        frequent = n_cb > 0.5 * n_it
        findings.append(
            Finding(
                "warning" if frequent else "info",
                "eigenvalues_not_converged",
                "Some eigenvalues were not converged in the diagonalization",
                f"'c_bands: N eigenvalues not converged' appeared {n_cb} time(s) in "
                f"{n_it} SCF iterations. Occasional occurrences, especially in early "
                "iterations, are usually harmless.",
                ["If it is frequent or the SCF struggles, try diagonalization = 'cg' or a larger diago_david_ndim."],
            )
        )

    for extra in (_cutoffs(run), _multi_run(run)):
        if extra:
            findings.append(extra)

    for msg in run.messages:
        if msg.text.startswith("c_bands"):
            continue
        if msg.routine:
            findings.append(
                Finding(
                    "info",
                    "qe_message",
                    f"Message from routine {msg.routine}",
                    msg.text,
                    [],
                    None,
                    msg.line,
                )
            )
        elif msg.text.startswith("Warning: card"):
            findings.append(
                Finding(
                    "info",
                    "input_ignored",
                    "Part of the input was ignored",
                    f"{msg.text}. pw.x skips namelists and cards that do not apply "
                    "to this calculation type. Harmless, but check it is what you intended.",
                    [],
                    None,
                    msg.line,
                )
            )
        elif "bfgs curvature condition failed" in msg.text:
            times = f"{msg.count} time(s)" if msg.count > 1 else "once"
            findings.append(
                Finding(
                    "info",
                    "bfgs_curvature",
                    "BFGS curvature condition failed",
                    f"Printed {times}. BFGS damped the Hessian update because the step did not "
                    "satisfy the curvature condition (s.y < 0.2 s.B.s). This is a standard "
                    "safeguard, common far from the minimum; it only matters if it repeats "
                    "on most steps and the relaxation does not progress.",
                    [],
                    msg.text,
                    msg.line,
                )
            )
        else:
            times = f" (x{msg.count})" if msg.count > 1 else ""
            findings.append(Finding("warning", "qe_warning", "Warning printed by pw.x", msg.text + times, [], None, msg.line))

    return _sorted(findings)


# --------------------------------------------------------------------------
# ph.x (experimental)
# --------------------------------------------------------------------------


def diagnose_ph(run: PhRun) -> list[Finding]:
    findings: list[Finding] = []
    if run.error is not None:
        findings.append(_explain_error(run.error, "ph.x"))
    elif run.walltime_reached:
        findings.append(
            Finding(
                "warning",
                "max_seconds",
                "Stopped by max_seconds",
                "ph.x stopped itself because the max_seconds limit was reached. "
                "It saves its progress before stopping.",
                ["Rerun ph.x with recover = .true. (same prefix, outdir and fildyn) to continue."],
                "Maximum CPU time exceeded",
            )
        )
    elif not run.job_done:
        where = "before the first q point"
        if run.representations:
            rep = run.representations[-1]
            where = f"while computing representation {rep.label} of q point {rep.q_index}"
        findings.append(_incomplete(run, where))

    bad = [r for r in run.representations if r.converged is False]
    if bad:
        r = bad[0]
        findings.append(
            Finding(
                "error",
                "ph_not_converged",
                "Linear-response SCF did not converge",
                f"ph.x reported 'No convergence has been achieved' for representation {r.label} "
                f"of q point {r.q_index} after {len(r.iterations)} iterations.",
                [
                    "Reduce alpha_mix(1) (default 0.7), e.g. to 0.3, and/or increase nmix_ph.",
                    "Increase niter_ph.",
                    "Make sure the preceding pw.x SCF is tightly converged (small conv_thr) and the structure is relaxed.",
                ],
                None,
                r.line,
            )
        )

    for q in run.q_points:
        neg = [f for f in q.frequencies_cm1 if f < 0]
        if not neg:
            continue
        at_gamma = all(abs(c) < 1e-6 for c in q.q)
        small = [f for f in neg if f > -30.0]
        if at_gamma and len(neg) <= 3 and len(small) == len(neg):
            findings.append(
                Finding(
                    "info",
                    "ph_acoustic_gamma",
                    "Small negative acoustic frequencies at Gamma",
                    f"{len(neg)} mode(s) at Gamma have small negative (imaginary) frequencies "
                    f"(lowest {min(neg):.2f} cm-1). At Gamma the acoustic modes should be zero; "
                    "small deviations usually come from the acoustic sum rule not being imposed. "
                    "qe-inspect does not check that these are really the acoustic modes.",
                    [
                        "Impose the acoustic sum rule in dynmat.x or matdyn.x (asr = 'crystal'; 'zero-dim' for molecules).",
                        "The sum rule does not fix residual forces: make sure the structure is relaxed first.",
                    ],
                )
            )
        elif at_gamma and len(neg) <= 6:
            findings.append(
                Finding(
                    "info",
                    "ph_negative_gamma",
                    "Negative frequencies at Gamma: impose the sum rule before judging",
                    f"{len(neg)} mode(s) at Gamma are negative (lowest {min(neg):.2f} cm-1). "
                    "Up to three translations, and three rotations for an isolated molecule, "
                    "should be zero. Without the acoustic sum rule they can come out clearly "
                    "negative, especially with a noisy exchange-correlation potential "
                    "(e.g. GGA with vacuum regions).",
                    [
                        "Apply the sum rule with dynmat.x: asr = 'crystal' for solids, 'zero-dim' for molecules.",
                        "If modes stay imaginary after that, check relaxation and convergence parameters.",
                    ],
                )
            )
        else:
            findings.append(
                Finding(
                    "warning",
                    "ph_imaginary",
                    "Imaginary phonon frequencies",
                    f"q = ({q.q[0]:.4f}, {q.q[1]:.4f}, {q.q[2]:.4f}) has {len(neg)} mode(s) with "
                    f"negative frequency (lowest {min(neg):.2f} cm-1). Negative values mean "
                    "imaginary frequencies: either a real dynamical instability or an "
                    "under-converged setup.",
                    [
                        "Check that the structure is fully relaxed (forces and stress).",
                        "Test convergence with respect to ecutwfc, k-points, smearing and tr2_ph.",
                    ],
                )
            )

    multi = _multi_run(run)
    if multi:
        findings.append(multi)
    for msg in run.messages:
        if msg.routine:
            findings.append(Finding("info", "qe_message", f"Message from routine {msg.routine}", msg.text, [], None, msg.line))
    return _sorted(findings)


def diagnose(run: Union[PwRun, PhRun]) -> list[Finding]:
    if isinstance(run, PhRun):
        return diagnose_ph(run)
    return diagnose_pw(run)


def status(run: Union[PwRun, PhRun], findings: list[Finding]) -> str:
    """One-word outcome: ok, warnings, failed, stopped, crashed or incomplete."""
    if run.error is not None:
        return "crashed"
    if any(f.code == "incomplete" for f in findings):
        return "incomplete"
    if any(f.severity == "error" for f in findings):
        return "failed"
    if run.walltime_reached:
        return "stopped"
    if any(f.severity == "warning" for f in findings):
        return "warnings"
    return "ok"


def _sorted(findings: list[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda f: SEVERITY_ORDER.get(f.severity, 9))
