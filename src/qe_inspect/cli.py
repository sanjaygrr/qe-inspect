"""Command-line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .detect import find_outputs, parse_file
from .html import render_html
from .report import Report, render_json, render_table, render_text, use_color

EXIT_CODES = {"ok": 0, "warnings": 0, "stopped": 1, "failed": 1, "crashed": 1, "incomplete": 1}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="qe-inspect",
        description="Diagnose Quantum ESPRESSO pw.x and ph.x output files.",
    )
    p.add_argument("paths", nargs="+", help="output file(s) or directories to scan")
    p.add_argument("--html", metavar="FILE", help="write a self-contained HTML report (single file only)")
    p.add_argument("--json", action="store_true", help="print JSON instead of text")
    p.add_argument("-v", "--verbose", action="store_true", help="show every SCF cycle and informational messages")
    p.add_argument("--no-color", action="store_true", help="disable colored output")
    p.add_argument("--version", action="version", version=f"qe-inspect {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    color = use_color() and not args.no_color

    files: list[Path] = []
    scanned_dir = False
    input_error = False
    for raw in args.paths:
        path = Path(raw)
        if path.is_dir():
            scanned_dir = True
            found = find_outputs(path)
            if not found:
                print(f"qe-inspect: no pw.x or ph.x outputs found in {path}", file=sys.stderr)
            files.extend(found)
        elif path.is_file():
            files.append(path)
        else:
            print(f"qe-inspect: {path}: no such file or directory", file=sys.stderr)
            input_error = True

    reports: list[Report] = []
    for f in files:
        try:
            reports.append(Report.from_run(parse_file(f)))
        except ValueError as exc:
            print(f"qe-inspect: {exc}", file=sys.stderr)
            input_error = True
    if not reports:
        return 2

    if args.html:
        if len(reports) != 1:
            print("qe-inspect: --html takes exactly one output file", file=sys.stderr)
            return 2
        Path(args.html).write_text(render_html(reports[0]), encoding="utf-8")
        print(f"HTML report written to {args.html}", file=sys.stderr)

    if args.json:
        print(render_json(reports[0] if len(reports) == 1 and not scanned_dir else reports))
    elif len(reports) == 1 and not scanned_dir:
        print(render_text(reports[0], color=color, verbose=args.verbose))
    else:
        dirs = [p for p in args.paths if Path(p).is_dir()]
        base = dirs[0] if len(dirs) == 1 and len(args.paths) == 1 else None
        print(render_table(reports, color=color, base=base))

    if input_error:
        return 2
    return max(EXIT_CODES[r.status] for r in reports)
