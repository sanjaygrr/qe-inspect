"""Identify which QE program wrote a file and dispatch to the right parser."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from .common import read_lines
from .model import PhRun, PwRun
from .ph import parse_ph
from .pw import parse_pw

PROGRAMS = {"PWSCF": "pw.x", "PHONON": "ph.x"}
HEAD_BYTES = 262144


def sniff(path: Union[str, Path]) -> Optional[str]:
    """Return 'pw.x', 'ph.x' or None by looking at the start of the file."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(HEAD_BYTES).decode("utf-8", errors="replace")
    except OSError:
        return None
    for line in head.splitlines():
        if "Program " in line and " starts" in line:
            for key, prog in PROGRAMS.items():
                if f"Program {key} " in line:
                    return prog
            return None
    return None


def parse_file(path: Union[str, Path]) -> Union[PwRun, PhRun]:
    """Parse a QE output file. Raises ValueError if the program is unsupported."""
    prog = sniff(path)
    if prog is None:
        raise ValueError(
            f"{path}: not a pw.x or ph.x output (no 'Program PWSCF' or "
            "'Program PHONON' header found)"
        )
    lines = read_lines(path)
    starts = [i for i, line in enumerate(lines) if "Program " in line and " starts on " in line]
    first = starts[-1] if len(starts) > 1 else 0
    prog = sniff_lines(lines[first : first + 50]) or prog
    parser = parse_pw if prog == "pw.x" else parse_ph
    run = parser(path, lines, start=first)
    run.runs_in_file = max(1, len(starts))
    return run


def sniff_lines(lines: list[str]) -> Optional[str]:
    for line in lines:
        for key, prog in PROGRAMS.items():
            if f"Program {key} " in line:
                return prog
    return None


def find_outputs(directory: Union[str, Path]) -> list[Path]:
    """Recursively list files under ``directory`` written by pw.x or ph.x."""
    root = Path(directory)
    found = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or any(part.startswith(".") for part in p.relative_to(root).parts):
            continue
        if p.suffix.lower() in {".upf", ".xml", ".in", ".py", ".json", ".html", ".gz"}:
            continue
        if sniff(p) is not None:
            found.append(p)
    return found
