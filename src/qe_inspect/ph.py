"""Parser for ph.x standard output (experimental)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .common import FLOAT, parse_qe_time, read_lines, scan_common, to_float
from .model import PhIteration, PhQPoint, PhRepresentation, PhRun

RE_QCALC = re.compile(rf"Calculation of q\s*=\s*({FLOAT})\s+({FLOAT})\s+({FLOAT})")
RE_REPR = re.compile(r"Representation #\s*(\d+)\s+modes? #\s*(.*)")
RE_ITER = re.compile(r"iter #\s*(\d+)\s+total cpu time")
RE_DVSCF = re.compile(rf"alpha_mix\s*=\s*({FLOAT}).*\|ddv_scf\|\^2\s*=\s*({FLOAT})")
RE_QLINE = re.compile(rf"^\s*q = \(\s*({FLOAT})\s+({FLOAT})\s+({FLOAT})\s*\)")
RE_FREQ = re.compile(rf"freq \(\s*\d+\)\s*=\s*({FLOAT})\s*\[THz\]\s*=\s*({FLOAT})\s*\[cm-1\]")
RE_TIMING = re.compile(r"^\s*PHONON\s*:\s*(.+?)\s*CPU\s+(.+?)\s*WALL")


def parse_ph(path: str | Path, lines: Optional[list[str]] = None) -> PhRun:
    if lines is None:
        lines = read_lines(path)
    run = PhRun(path=str(path), n_lines=len(lines))
    q_index = 0
    rep: Optional[PhRepresentation] = None
    in_dyn = False
    qpoint: Optional[PhQPoint] = None

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        lineno = i + 1
        consumed = scan_common(line, i, lines, run)
        if consumed != i:
            i = consumed + 1
            continue

        m = RE_QCALC.search(line)
        if m:
            q_index += 1
            rep = None
            in_dyn = False
        elif "Electric Fields Calculation" in line:
            rep = PhRepresentation(q_index=q_index, label="electric field", line=lineno)
            run.representations.append(rep)
        elif (m := RE_REPR.search(line)) is not None:
            label = f"#{m.group(1)} (modes {' '.join(m.group(2).split())})"
            rep = PhRepresentation(q_index=q_index, label=label, line=lineno)
            run.representations.append(rep)
        elif (m := RE_ITER.search(line)) is not None and rep is not None:
            rep.iterations.append(PhIteration(number=int(m.group(1)), line=lineno))
        elif (m := RE_DVSCF.search(line)) is not None:
            if run.alpha_mix is None:
                run.alpha_mix = to_float(m.group(1))
            if rep is not None and rep.iterations:
                rep.iterations[-1].dvscf = to_float(m.group(2))
        elif "No convergence has been achieved" in line:
            if rep is not None:
                rep.converged = False
        elif "Convergence has been achieved" in line:
            if rep is not None:
                rep.converged = True
        elif "Diagonalizing the dynamical matrix" in line:
            in_dyn = True
            qpoint = None
        elif in_dyn and (m := RE_QLINE.match(line)) is not None:
            q = (to_float(m.group(1)), to_float(m.group(2)), to_float(m.group(3)))
            qpoint = PhQPoint(index=q_index or len(run.q_points) + 1, q=q)
            run.q_points.append(qpoint)
        elif in_dyn and qpoint is not None and (m := RE_FREQ.search(line)) is not None:
            qpoint.frequencies_cm1.append(to_float(m.group(2)))
        elif (m := RE_TIMING.search(line)) is not None:
            run.cpu_time_s = parse_qe_time(m.group(1))
            run.wall_time_s = parse_qe_time(m.group(2))
        i += 1

    for text in reversed(lines):
        if text.strip():
            run.last_line = text.strip()
            break
    return run
