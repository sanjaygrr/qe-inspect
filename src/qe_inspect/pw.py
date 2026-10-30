"""Parser for pw.x standard output (scf, nscf, relax, vc-relax, md)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .common import FLOAT, add_message, parse_qe_time, read_lines, scan_common, to_float
from .model import PwRun, ScfCycle, ScfIteration

_SUMMARY_FLOATS = {
    "n_electrons": re.compile(rf"number of electrons\s*=\s*({FLOAT})"),
    "ecutwfc": re.compile(rf"kinetic-energy cutoff\s*=\s*({FLOAT})\s*Ry"),
    "ecutrho": re.compile(rf"charge density cutoff\s*=\s*({FLOAT})\s*Ry"),
    "conv_thr": re.compile(rf"convergence threshold\s*=\s*({FLOAT})"),
    "mixing_beta": re.compile(rf"mixing beta\s*=\s*({FLOAT})"),
    "etot_conv_thr": re.compile(rf"energy convergence thresh\.\s*=\s*({FLOAT})"),
    "forc_conv_thr": re.compile(rf"force convergence thresh\.\s*=\s*({FLOAT})"),
    "press_conv_thr": re.compile(rf"press convergence thresh\.\s*=\s*({FLOAT})"),
}
_SUMMARY_INTS = {
    "nat": re.compile(r"number of atoms/cell\s*=\s*(\d+)"),
    "ntyp": re.compile(r"number of atomic types\s*=\s*(\d+)"),
    "n_bands": re.compile(r"number of Kohn-Sham states\s*=\s*(\d+)"),
    "nstep": re.compile(r"^\s*nstep\s*=\s*(\d+)"),
}

RE_MIXING = re.compile(r"number of iterations used\s*=\s*(\d+)\s+(\S+)\s+mixing")
RE_XC = re.compile(r"Exchange-correlation\s*=\s*(.+)")
RE_KPOINTS = re.compile(r"number of k points\s*=\s*(\d+)\s*(.*)")
RE_PSEUDO = re.compile(r"Pseudo is ([^,]+),")
RE_ITERATION = re.compile(r"iteration #\s*(\d+)")
RE_ENERGY = re.compile(rf"^\s*(!*)\s*total energy\s*=\s*({FLOAT})\s*Ry")
RE_ACCURACY = re.compile(rf"estimated scf accuracy\s*<\s*({FLOAT})\s*Ry")
RE_CONVERGED = re.compile(r"convergence has been achieved in\s+(\d+)\s+iterations")
RE_NOT_CONVERGED = re.compile(r"convergence NOT achieved after\s+(\d+)\s+iterations")
RE_CBANDS = re.compile(r"c_bands:\s*(\d+)\s+eigenvalues not converged")
RE_FERMI = re.compile(rf"the Fermi energy is\s+({FLOAT})\s*ev")
RE_FERMI_SPIN = re.compile(rf"the spin up/dw Fermi energies are\s+({FLOAT})\s+({FLOAT})")
RE_HOMO = re.compile(rf"highest occupied level \(ev\):\s*({FLOAT})")
RE_HOMO_LUMO = re.compile(rf"highest occupied, lowest unoccupied level \(ev\):\s*({FLOAT})\s+({FLOAT})")
RE_FORCE = re.compile(rf"Total force\s*=\s*({FLOAT})\s+Total SCF correction\s*=\s*({FLOAT})")
RE_PRESSURE = re.compile(rf"total\s+stress.*P\s*=\s*({FLOAT})")
RE_VOLUME = re.compile(rf"new unit-cell volume\s*=\s*({FLOAT})")
RE_BFGS_EERR = re.compile(rf"^\s*Energy error\s*=\s*({FLOAT})\s*Ry")
RE_BFGS_GERR = re.compile(rf"^\s*Gradient error\s*=\s*({FLOAT})\s*Ry/Bohr")
RE_FINAL_ENTHALPY = re.compile(rf"Final (?:enthalpy|energy)\s*=\s*({FLOAT})")
RE_NEG_RHO = re.compile(rf"negative rho \(up,\s*down\):\s*({FLOAT})\s+({FLOAT})")
RE_INT_CHARGE = re.compile(rf"WARNING: integrated charge=\s*({FLOAT}),\s*expected=\s*({FLOAT})")
RE_TIMING = re.compile(r"^\s*PWSCF\s*:\s*(.+?)\s*CPU\s+(.+?)\s*WALL")

IONIC_CONVERGED = (
    "bfgs converged in",
    "Damped Dynamics: convergence achieved",
    "FIRE: convergence achieved",
    "convergence achieved, Efinal=",
)


def parse_pw(path: str | Path, lines: Optional[list[str]] = None) -> PwRun:
    """Parse a pw.x output file. Never raises on truncated or odd files."""
    if lines is None:
        lines = read_lines(path)
    run = PwRun(path=str(path), n_lines=len(lines))

    cycle: Optional[ScfCycle] = None
    cycle_ended = False
    next_is_final = False
    in_final_coords = False
    flags = {
        "md": False, "dyn": False, "bands": False, "vc": False, "relax": False, "minimization": False
    }

    def new_cycle(line_no: int) -> ScfCycle:
        nonlocal next_is_final
        cyc = ScfCycle(index=len(run.scf_cycles) + 1, line=line_no, is_final_scf=next_is_final)
        next_is_final = False
        run.scf_cycles.append(cyc)
        return cyc

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        lineno = i + 1
        if line.startswith("Begin final coordinates"):
            in_final_coords = True
        elif line.startswith("End final coordinates"):
            in_final_coords = False
        consumed = scan_common(line, i, lines, run)
        if consumed != i:
            i = consumed + 1
            continue

        # --- SCF iterations -------------------------------------------------
        m = RE_ITERATION.search(line)
        if m and "ecut" in line:
            number = int(m.group(1))
            if cycle is None or cycle_ended or (number == 1 and cycle.iterations):
                cycle = new_cycle(lineno)
                cycle_ended = False
            cycle.iterations.append(ScfIteration(number=number, line=lineno))
            i += 1
            continue

        m = RE_ENERGY.match(line)
        if m and cycle is not None:
            energy = to_float(m.group(2))
            if m.group(1):
                cycle.energy_ry = energy
                if cycle.iterations and cycle.iterations[-1].energy_ry is None:
                    cycle.iterations[-1].energy_ry = energy
            elif cycle.iterations and not cycle_ended:
                cycle.iterations[-1].energy_ry = energy
            i += 1
            continue

        m = RE_ACCURACY.search(line)
        if m:
            if cycle is not None and cycle.iterations and cycle.iterations[-1].accuracy_ry is None:
                cycle.iterations[-1].accuracy_ry = to_float(m.group(1))
            i += 1
            continue

        if "End of self-consistent calculation" in line or "End of band structure calculation" in line:
            cycle_ended = True
            i += 1
            continue

        m = RE_CONVERGED.search(line)
        if m and cycle is not None:
            cycle.converged = True
            cycle.reported_iterations = int(m.group(1))
            cycle_ended = True
            i += 1
            continue

        m = RE_NOT_CONVERGED.search(line)
        if m:
            if cycle is None:
                cycle = new_cycle(lineno)
            cycle.converged = False
            cycle.reported_iterations = int(m.group(1))
            cycle_ended = True
            i += 1
            continue

        m = RE_CBANDS.search(line)
        if m:
            if cycle is not None and cycle.iterations and not cycle_ended:
                cycle.iterations[-1].unconverged_bands_warnings += 1
            add_message(run.messages, "warning", "c_bands: eigenvalues not converged", lineno)
            i += 1
            continue

        # --- per-cycle results ---------------------------------------------
        if cycle is not None:
            m = RE_FERMI.search(line)
            if m:
                cycle.fermi_energy_ev = to_float(m.group(1))
                i += 1
                continue
            m = RE_FERMI_SPIN.search(line)
            if m:
                # report the spin-up value; both are kept in the message list
                cycle.fermi_energy_ev = to_float(m.group(1))
                i += 1
                continue
            m = RE_HOMO_LUMO.search(line)
            if m:
                cycle.homo_ev, cycle.lumo_ev = to_float(m.group(1)), to_float(m.group(2))
                i += 1
                continue
            m = RE_HOMO.search(line)
            if m:
                cycle.homo_ev = to_float(m.group(1))
                i += 1
                continue
            m = RE_FORCE.search(line)
            if m:
                cycle.total_force = to_float(m.group(1))
                cycle.scf_correction = to_float(m.group(2))
                i += 1
                continue
            m = RE_BFGS_EERR.match(line)
            if m:
                cycle.bfgs_energy_error = to_float(m.group(1))
                i += 1
                continue
            m = RE_BFGS_GERR.match(line)
            if m:
                cycle.bfgs_gradient_error = to_float(m.group(1))
                i += 1
                continue
            m = RE_PRESSURE.search(line)
            if m:
                cycle.pressure_kbar = to_float(m.group(1))
                i += 1
                continue
            m = RE_VOLUME.search(line)
            if m:
                if not in_final_coords:
                    flags["vc"] = True
                if cycle.volume_bohr3 is None:
                    cycle.volume_bohr3 = to_float(m.group(1))
                i += 1
                continue

        # --- run summary (first occurrence wins) ---------------------------
        matched = False
        for attr, rx in _SUMMARY_FLOATS.items():
            m = rx.search(line)
            if m:
                if getattr(run, attr) is None:
                    setattr(run, attr, to_float(m.group(1)))
                if attr == "press_conv_thr":
                    flags["vc"] = True
                matched = True
                break
        if not matched:
            for attr, rx in _SUMMARY_INTS.items():
                m = rx.search(line)
                if m:
                    if getattr(run, attr) is None:
                        setattr(run, attr, int(m.group(1)))
                    if attr == "nstep":
                        flags["relax"] = True
                    matched = True
                    break
        if matched:
            i += 1
            continue

        m = RE_MIXING.search(line)
        if m:
            if run.mixing_ndim is None:
                run.mixing_ndim = int(m.group(1))
                run.mixing_mode = m.group(2)
            i += 1
            continue
        m = RE_XC.search(line)
        if m:
            if run.xc is None:
                run.xc = " ".join(m.group(1).split())
            i += 1
            continue
        m = RE_KPOINTS.search(line)
        if m:
            if run.n_kpoints is None:
                run.n_kpoints = int(m.group(1))
                rest = " ".join(m.group(2).split())
                run.occupations = rest or None
            i += 1
            continue
        m = RE_PSEUDO.search(line)
        if m:
            if not run.scf_cycles:
                run.pseudo_types.append(m.group(1).strip())
            i += 1
            continue

        # --- ionic loop ----------------------------------------------------
        if "Molecular Dynamics Calculation" in line:
            flags["md"] = True
        elif "Entering Dynamics" in line:
            flags["dyn"] = True
        elif "Band Structure Calculation" in line:
            flags["bands"] = True
        elif (
            "BFGS Geometry Optimization" in line
            or "Damped Dynamics" in line
            or "FIRE" in line
            or "Damped Cell Dynamics Minimization" in line
        ):
            flags["minimization"] = True

        if "final scf calculation at the relaxed structure" in line.lower():
            next_is_final = True
        elif any(key in line for key in IONIC_CONVERGED):
            run.ionic_status = "converged"
            run.ionic_status_line = lineno
        elif "The maximum number of steps has been reached." in line:
            run.ionic_status = "max_steps"
            run.ionic_status_line = lineno
        elif "bfgs failed after" in line:
            run.ionic_status = "bfgs_failed"
            run.ionic_status_line = lineno

        m = RE_FINAL_ENTHALPY.search(line)
        if m:
            run.final_enthalpy_ry = to_float(m.group(1))
            i += 1
            continue

        # --- warnings ------------------------------------------------------
        if "SCF correction compared to forces is large" in line:
            run.scf_correction_warnings += 1
            i += 1
            continue
        m = RE_NEG_RHO.search(line)
        if m:
            value = max(abs(to_float(m.group(1)) or 0.0), abs(to_float(m.group(2)) or 0.0))
            if run.negative_rho_max is None or value > run.negative_rho_max:
                run.negative_rho_max = value
            i += 1
            continue
        m = RE_INT_CHARGE.search(line)
        if m:
            got, expected = to_float(m.group(1)), to_float(m.group(2))
            if got is not None and expected is not None:
                prev = run.integrated_charge
                if prev is None or abs(got - expected) > abs(prev[0] - prev[1]):
                    run.integrated_charge = (got, expected)
            i += 1
            continue
        if "WARNING" in line or "DEPRECATED" in line:
            add_message(run.messages, "warning", line.strip(), lineno)
            i += 1
            continue

        m = RE_TIMING.search(line)
        if m:
            run.cpu_time_s = parse_qe_time(m.group(1))
            run.wall_time_s = parse_qe_time(m.group(2))
        i += 1

    for text in reversed(lines):
        if text.strip():
            run.last_line = text.strip()
            break

    if flags["md"] and not flags["minimization"]:
        run.calculation = "md"
    elif flags["vc"]:
        moving = flags["dyn"] and not flags["minimization"]
        run.calculation = "vc-md" if moving else "vc-relax"
    elif flags["relax"] or flags["minimization"]:
        run.calculation = "relax"
    elif flags["bands"]:
        run.calculation = "nscf/bands"
    elif run.scf_cycles or run.n_kpoints is not None:
        run.calculation = "scf"
    return run
