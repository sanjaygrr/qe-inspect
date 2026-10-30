"""Parsing helpers shared by the pw.x and ph.x parsers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .model import Message

FLOAT = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[EeDd][-+]?\d+)?"

RE_VERSION = re.compile(r"Program\s+(\S+)\s+v\.?\s*(\S+)")
RE_PROCS = re.compile(r"running on\s+(\d+)\s+processor")
RE_MPI_PROCS = re.compile(r"Number of MPI processes:\s+(\d+)")
RE_INPUT = re.compile(r"Reading input from\s+(\S+)")
RE_PERCENT = re.compile(r"^\s*%{20,}\s*$")
RE_ERROR_HEAD = re.compile(r"Error in routine\s+(.+?)\s*\(\s*(-?\d+)\s*\):")
RE_INFOMSG = re.compile(r"Message from routine\s+(.+?)\s*:\s*$")
RE_TIME_TOKEN = re.compile(r"(?:(\d+)d)?\s*(?:(\d+)h)?\s*(?:(\d+)m)?\s*(?:([\d.]+)s)?")

# Lines that only appear when stderr of the job was merged into the output,
# or that are printed by the MPI runtime / batch system rather than by QE.
ABORT_MARKERS = (
    "MPI_ABORT was invoked",
    "Program received signal",
    "DUE TO TIME LIMIT",
    "CANCELLED AT",
    "oom-kill",
    "Out Of Memory",
)


def to_float(text: str) -> Optional[float]:
    try:
        return float(text.replace("D", "E").replace("d", "e"))
    except ValueError:
        return None


def parse_qe_time(text: str) -> Optional[float]:
    """Convert QE clock strings such as '1h23m', '2m33.47s' or '5.10s' to seconds."""
    text = text.strip()
    m = RE_TIME_TOKEN.fullmatch(text)
    if not m or not any(m.groups()):
        return None
    d, h, mi, s = m.groups()
    return (
        int(d or 0) * 86400
        + int(h or 0) * 3600
        + int(mi or 0) * 60
        + float(s or 0.0)
    )


def read_lines(path: str | Path) -> list[str]:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read().splitlines()


def parse_error_block(lines: list[str], start: int) -> tuple[Optional[Message], int]:
    """Parse a '%%%%' block starting at ``start``.

    Returns the error (or None if the block is not an error, e.g. a citation
    banner) and the index of the closing line.
    """
    end = start + 1
    while end < len(lines) and not RE_PERCENT.match(lines[end]):
        end += 1
    body = lines[start + 1 : end]
    for i, text in enumerate(body):
        m = RE_ERROR_HEAD.search(text)
        if m:
            msg_lines = [b.strip() for b in body[i + 1 :] if b.strip()]
            return (
                Message(
                    kind="error",
                    text=" ".join(msg_lines),
                    line=start + i + 2,
                    routine=m.group(1).strip(),
                    code=int(m.group(2)),
                ),
                end,
            )
    return None, end


def add_message(messages: list[Message], kind: str, text: str, line: int, **kw) -> None:
    """Append a message, merging exact repeats into a counter."""
    for msg in messages:
        if msg.kind == kind and msg.text == text and msg.routine == kw.get("routine"):
            msg.count += 1
            return
    messages.append(Message(kind=kind, text=text, line=line, **kw))


def scan_common(line: str, idx: int, lines: list[str], run) -> int:
    """Handle lines that look the same in every QE program.

    Returns the index of the last consumed line.
    """
    stripped = line.strip()
    if run.version is None:
        m = RE_VERSION.search(line)
        if m:
            run.version = m.group(2)
            return idx
    if run.mpi_processes is None:
        m = RE_PROCS.search(line) or RE_MPI_PROCS.search(line)
        if m:
            run.mpi_processes = int(m.group(1))
            return idx
        if stripped == "Serial version":
            run.mpi_processes = 1
            return idx
    if run.input_file is None:
        m = RE_INPUT.search(line)
        if m:
            run.input_file = m.group(1)
            return idx
    if RE_PERCENT.match(line):
        err, end = parse_error_block(lines, idx)
        if err is not None and run.error is None:
            run.error = err
        return end
    m = RE_INFOMSG.search(line)
    if m:
        nxt = idx + 1
        while nxt < len(lines) and not lines[nxt].strip():
            nxt += 1
        text = lines[nxt].strip() if nxt < len(lines) else ""
        add_message(run.messages, "info", text, idx + 1, routine=m.group(1).strip())
        return nxt
    if stripped == "JOB DONE.":
        run.job_done = True
        return idx
    if stripped == "Maximum CPU time exceeded":
        run.walltime_reached = True
        return idx
    if run.abort_marker is None:
        for marker in ABORT_MARKERS:
            if marker in line:
                run.abort_marker = stripped
                break
    if stripped.startswith("Warning: card"):
        add_message(run.messages, "info", stripped, idx + 1)
    return idx
