"""Plain data containers for parsed runs and diagnostics."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class Message:
    """A warning, informational message or fatal error printed by QE."""

    kind: str  # "error", "warning" or "info"
    text: str
    line: Optional[int] = None
    routine: Optional[str] = None
    code: Optional[int] = None
    count: int = 1


@dataclass
class ScfIteration:
    number: int
    line: int
    energy_ry: Optional[float] = None
    accuracy_ry: Optional[float] = None
    unconverged_bands_warnings: int = 0


@dataclass
class ScfCycle:
    """One self-consistent cycle. A relax run has one per ionic step."""

    index: int
    line: int
    iterations: list[ScfIteration] = field(default_factory=list)
    converged: Optional[bool] = None
    reported_iterations: Optional[int] = None
    energy_ry: Optional[float] = None
    fermi_energy_ev: Optional[float] = None
    homo_ev: Optional[float] = None
    lumo_ev: Optional[float] = None
    total_force: Optional[float] = None
    scf_correction: Optional[float] = None
    pressure_kbar: Optional[float] = None
    volume_bohr3: Optional[float] = None
    bfgs_energy_error: Optional[float] = None
    bfgs_gradient_error: Optional[float] = None
    is_final_scf: bool = False

    @property
    def accuracies(self) -> list[float]:
        return [it.accuracy_ry for it in self.iterations if it.accuracy_ry is not None]


@dataclass
class Finding:
    """A diagnosed problem with an explanation and suggested fixes."""

    severity: str  # "error", "warning" or "info"
    code: str
    title: str
    explanation: str
    suggestions: list[str] = field(default_factory=list)
    evidence: Optional[str] = None
    line: Optional[int] = None


@dataclass
class PwRun:
    path: str
    program: str = "pw.x"
    version: Optional[str] = None
    calculation: Optional[str] = None
    mpi_processes: Optional[int] = None
    input_file: Optional[str] = None
    n_lines: int = 0

    # system summary
    nat: Optional[int] = None
    ntyp: Optional[int] = None
    n_electrons: Optional[float] = None
    n_bands: Optional[int] = None
    ecutwfc: Optional[float] = None
    ecutrho: Optional[float] = None
    conv_thr: Optional[float] = None
    mixing_beta: Optional[float] = None
    mixing_ndim: Optional[int] = None
    mixing_mode: Optional[str] = None
    nstep: Optional[int] = None
    etot_conv_thr: Optional[float] = None
    forc_conv_thr: Optional[float] = None
    press_conv_thr: Optional[float] = None
    xc: Optional[str] = None
    n_kpoints: Optional[int] = None
    occupations: Optional[str] = None
    pseudo_types: list[str] = field(default_factory=list)

    # progress and results
    scf_cycles: list[ScfCycle] = field(default_factory=list)
    ionic_status: Optional[str] = None  # converged, max_steps, bfgs_failed, None
    ionic_status_line: Optional[int] = None
    final_enthalpy_ry: Optional[float] = None
    wall_time_s: Optional[float] = None
    cpu_time_s: Optional[float] = None
    job_done: bool = False
    walltime_reached: bool = False
    abort_marker: Optional[str] = None
    error: Optional[Message] = None
    messages: list[Message] = field(default_factory=list)
    negative_rho_max: Optional[float] = None
    integrated_charge: Optional[tuple[float, float]] = None
    scf_correction_warnings: int = 0
    last_line: str = ""

    @property
    def final_cycle(self) -> Optional[ScfCycle]:
        return self.scf_cycles[-1] if self.scf_cycles else None

    @property
    def energy_ry(self) -> Optional[float]:
        for cyc in reversed(self.scf_cycles):
            if cyc.energy_ry is not None:
                return cyc.energy_ry
        return None

    @property
    def fermi_energy_ev(self) -> Optional[float]:
        for cyc in reversed(self.scf_cycles):
            if cyc.fermi_energy_ev is not None:
                return cyc.fermi_energy_ev
        return None

    @property
    def ionic_steps(self) -> int:
        return sum(1 for c in self.scf_cycles if not c.is_final_scf)

    @property
    def total_scf_iterations(self) -> int:
        return sum(len(c.iterations) for c in self.scf_cycles)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["energy_ry"] = self.energy_ry
        data["fermi_energy_ev"] = self.fermi_energy_ev
        data["ionic_steps"] = self.ionic_steps
        data["total_scf_iterations"] = self.total_scf_iterations
        return data


@dataclass
class PhIteration:
    number: int
    line: int
    dvscf: Optional[float] = None  # |ddv_scf|^2


@dataclass
class PhRepresentation:
    """Linear-response cycle for one irreducible representation."""

    q_index: int
    label: str
    line: int
    iterations: list[PhIteration] = field(default_factory=list)
    converged: Optional[bool] = None


@dataclass
class PhQPoint:
    index: int
    q: tuple[float, float, float]
    frequencies_cm1: list[float] = field(default_factory=list)


@dataclass
class PhRun:
    path: str
    program: str = "ph.x"
    version: Optional[str] = None
    mpi_processes: Optional[int] = None
    input_file: Optional[str] = None
    n_lines: int = 0
    tr2_ph: Optional[float] = None
    alpha_mix: Optional[float] = None
    q_points: list[PhQPoint] = field(default_factory=list)
    representations: list[PhRepresentation] = field(default_factory=list)
    wall_time_s: Optional[float] = None
    cpu_time_s: Optional[float] = None
    job_done: bool = False
    walltime_reached: bool = False
    abort_marker: Optional[str] = None
    error: Optional[Message] = None
    messages: list[Message] = field(default_factory=list)
    last_line: str = ""

    @property
    def calculation(self) -> str:
        return "phonon"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
