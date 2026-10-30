# qe-inspect

Diagnostic reports for [Quantum ESPRESSO](https://www.quantum-espresso.org/) output files.

`qe-inspect` reads the text output of `pw.x` (and, experimentally, `ph.x`) and tells you
what happened in the run: whether it finished, whether the SCF and the ionic loop
converged, what QE warned about, and, when something went wrong, a short explanation
of the likely cause and what to change in the input.

## Why

When a QE run fails, the information you need is usually in the output, but spread
over thousands of lines: the SCF accuracy history, a `c_bands` warning in iteration 3,
a `%%%%` error block, or simply the absence of `JOB DONE.`. Debugging means scrolling
and grepping, and the same checks get repeated for every failed job. Existing Python
parsers focus on extracting results from runs that worked; `qe-inspect` focuses on
the runs that did not.

## Install

Requires Python 3.9 or newer. No runtime dependencies.

```bash
pip install git+https://github.com/sanjaygrr/qe-inspect
```

For development:

```bash
git clone https://github.com/sanjaygrr/qe-inspect
cd qe-inspect
pip install -e ".[test,ase]"
pytest
```

## Usage

```bash
qe-inspect run.out                    # terminal summary of one run
qe-inspect run.out --html report.html # self-contained HTML report with charts
qe-inspect calculations/              # one table for every pw.x/ph.x output found
qe-inspect run.out --json             # machine-readable output
qe-inspect run.out -v                 # every SCF cycle and informational messages
```

The exit code is 0 when the run(s) finished without errors (warnings allowed),
1 when at least one run failed, crashed, stopped or is incomplete, and 2 on usage
errors. This makes it usable in scripts, e.g. to flag failed jobs after a batch.

### Example

A `relax` that ran out of ionic steps (`tests/data/qe75/relax_nstep.out`):

```text
$ qe-inspect tests/data/qe75/relax_nstep.out
tests/data/qe75/relax_nstep.out
pw.x 7.5 | relax, 1 MPI process | 671 lines
Status: FAILED

  atoms / species    2 / 1
  electrons / bands  6 / 7
  cutoffs            20 Ry (wfc), 80 Ry (rho)
  pseudopotentials   Norm-conserving
  functional         SLA PZ NOGX NOGC
  k-points           18 (Marzari-Vanderbilt smearing, width (Ry)= 0.0200)
  conv_thr / mixing  1.0e-08 Ry / mixing_beta 0.7 (plain, ndim 8)
  SCF cycles         3 (12 iterations)
  ionic steps        3 of nstep = 3
  total energy       -8.19776094 Ry
  Fermi energy       2.1866 eV
  total force        0.023721 Ry/bohr (SCF correction 0.000000)
  wall time          6.2 s

SCF convergence
  cycle  iters  last accuracy (Ry)  energy (Ry)          status
  1      5      7.00e-09            -8.19658367          converged
  2      3      7.30e-09            -8.19714376          converged
  3      4      1.60e-11            -8.19776094          converged

Findings
  [ERROR] Geometry optimization hit nstep before converging (line 605)
      The relax stopped after 3 ionic steps because it reached nstep = 3. Last
      BFGS gradient error: 1.7e-02 Ry/bohr (forc_conv_thr = 0.001). Last energy
      error: 6.2e-04 Ry (etot_conv_thr = 0.0001).
      > The maximum number of steps has been reached.
      - Increase nstep and restart from the last ATOMIC_POSITIONS (and
        CELL_PARAMETERS) printed in this output.
      - If forces stall instead of decreasing, tighten conv_thr: noisy forces
        slow down BFGS.
  ...
```

Scanning a directory:

```text
$ qe-inspect tests/data/qe75
file                     program  calc      status                 scf   ionic  energy (Ry)  wall   main issue
-----------------------  -------  --------  ---------------------  ----  -----  -----------  -----  ----------
aborted_no_message.out   pw.x     scf       INCOMPLETE             1/1   -      -            -      Run did not finish
crash_too_few_bands.out  pw.x     ?         CRASHED                -     -      -            -      nbnd is smaller than the number of occupied bands
relax_nstep.out          pw.x     relax     FAILED                 3/12  3      -8.197761    6.2 s  Geometry optimization hit nstep before converging
scf_maxstep.out          pw.x     scf       FAILED                 1/4   -      -            0.7 s  SCF did not converge
scf_walltime.out         pw.x     scf       STOPPED (max_seconds)  1/3   -      -            3.3 s  Stopped by max_seconds
vcrelax_al.out           pw.x     vc-relax  OK                     6/23  5      -4.194049    1.1 s

6 run(s): 1 INCOMPLETE, 1 CRASHED, 2 FAILED, 1 STOPPED (max_seconds), 1 OK
```

The HTML report contains the same information plus a chart of the estimated SCF
accuracy over all iterations (with `conv_thr` marked), and for relaxations the energy
and the BFGS gradient error along the ionic steps. It is a single file with inline CSS
and SVG, so it can be attached to an email or opened offline.

### Python API

```python
from qe_inspect import parse_file, diagnose

run = parse_file("run.out")          # PwRun or PhRun dataclass
print(run.energy_ry, run.ionic_status)
for cycle in run.scf_cycles:
    print(cycle.index, cycle.converged, cycle.accuracies)
for finding in diagnose(run):
    print(finding.severity, finding.title)
```

## What it reads

From `pw.x` (scf, nscf/bands, relax, vc-relax; md is parsed but not diagnosed):

- program version, MPI processes, input file name;
- system summary: atoms, species, electrons, bands, cutoffs, pseudopotential types,
  functional, k-points and smearing, `conv_thr`, mixing parameters, `nstep` and the
  ionic thresholds;
- every SCF iteration: total energy and estimated SCF accuracy;
- per SCF cycle: convergence, total energy, Fermi energy or HOMO/LUMO, total force
  and SCF correction, BFGS energy and gradient errors, pressure, cell volume;
- outcome of the ionic minimization (BFGS, damped dynamics, FIRE);
- `%%%%` error blocks, `Message from routine` notes, `WARNING` lines, `c_bands`
  warnings, negative-density and integrated-charge warnings, `max_seconds` stops,
  `JOB DONE.`, CPU and wall time.

From `ph.x` (experimental): q points, irreducible representations, the
`|ddv_scf|^2` history of each linear-response cycle, convergence, and frequencies.

## What it diagnoses

| Problem | How it is detected |
| --- | --- |
| Crash | `Error in routine ...` block. Known messages get a specific explanation: `S matrix not positive definite`, `problems computing cholesky`, `charge is wrong` (with and without `smearing is needed`), `too many bands are not converged`, `too few bands`. Others are reported with routine and message. |
| Unfinished job | No `JOB DONE.` and no QE error: reports where the output stops and any MPI or scheduler abort lines (if stderr was merged). |
| `max_seconds` reached | `Maximum CPU time exceeded`; suggests `restart_mode = 'restart'`. |
| SCF not converged | `convergence NOT achieved`. The accuracy history is classified as stopped early, oscillating (charge sloshing), stagnating or slowly converging, and the suggestions differ for each case (`electron_maxstep`, `mixing_beta`, `mixing_ndim`, `mixing_mode = 'local-TF'`, smearing). |
| Noisy SCF | A converged SCF that needed many iterations with an oscillating accuracy. |
| Relaxation not converged | `The maximum number of steps has been reached.` or `bfgs failed after ...`, with the last BFGS energy and gradient errors compared to the thresholds. |
| Pulay stress after vc-relax | Pressure of the final SCF far from the last relaxation step. |
| Inaccurate forces | `SCF correction compared to forces is large`. |
| Charge warnings | `WARNING: integrated charge=`, with the relative deviation and the thresholds QE uses. |
| Diagonalization warnings | `c_bands: N eigenvalues not converged`, counted over the run. |
| Cutoff ratio | Heuristic, not a QE message: `ecutrho/ecutwfc` below 8 with ultrasoft/PAW pseudopotentials, or below 4 with norm-conserving ones. `pw.x` does not print cutoff warnings itself. |
| Phonons (experimental) | `No convergence has been achieved`; negative (imaginary) frequencies, separating small acoustic ones at Gamma (acoustic sum rule) from the rest. |

Every QE message matched above was checked against the QE source
(`PW/src`, `Modules`, `LAXlib`, `PHonon/PH`) or against real output files.
Thresholds quoted in explanations (1e-7 and 1e-3 for the integrated charge,
`max(5, nbnd/4)` for unconverged bands, 10 % for the SCF correction to forces)
come from the QE 7.x source.

## Related work

Several tools already parse QE output. `qe-inspect` does not try to replace them;
it is meant as a diagnostics and report layer for runs that need debugging.

- [ASE](https://gitlab.com/ase/ase) `ase.io.espresso` reads `pw.x` output into
  `Atoms` objects with energies, forces and stress. It targets results: with ASE 3.29,
  reading the non-converged SCF fixtures in this repository raises an `AssertionError`,
  and crashed or aborted runs return no images. The test suite uses ASE to cross-check
  the final energies parsed by `qe-inspect` on the converged fixtures.
- [qeschema](https://github.com/QEF/qeschema) reads and converts the XML data file
  (`data-file-schema.xml`). The XML is the most reliable source of final results, but
  it holds no SCF history or warnings and is not written when a run crashes early.
- [aiida-quantumespresso](https://github.com/aiidateam/aiida-quantumespresso) has the
  most complete `pw.x` and `ph.x` parsers, including exit codes for many failure modes.
  They are built for the AiiDA workflow engine and depend on it.
- [qe-tools](https://github.com/aiidateam/qe-tools) is being redesigned (v3), with
  output parsing and explanations of failure modes on its roadmap. That overlaps with
  the goals here; if it matures, `qe-inspect` could use it as its parsing backend.
- [pymatgen-io-espresso](https://github.com/Griffin-Group/pymatgen-io-espresso) reads
  the QE XML output into a pymatgen-style API modelled on `pymatgen.io.vasp`.

The parser in `qe-inspect` is a small line-based reader with no dependencies. It was
written instead of wrapping one of the above because the diagnostics need the full
iteration history, every warning with its line number, and robust behaviour on
truncated or crashed files.

## Test data

`tests/data/qe/` contains output files from the Quantum ESPRESSO repository
(test-suite benchmarks and example references, QE 6.0 to 7.2).
`tests/data/qe75/` contains small runs made with `pw.x` 7.5 to cover failure modes that
the QE test suite does not include (SCF and ionic step limits, a crash, a `max_seconds`
stop, an abort without error message), together with their inputs. Provenance for every
file is in [`tests/data/README.md`](tests/data/README.md).

## Limitations

- Only `pw.x` and `ph.x` text output is supported. Other programs are rejected.
- `ph.x` support is experimental and has been tested on few outputs.
- The calculation type is inferred from the output, since `pw.x` does not print it.
- Spin-polarized runs report only the spin-up Fermi energy in the summary.
- Hybrid-functional (EXX) runs and NEB are parsed only partially.
- When several runs were appended to the same file, only the last one is analysed.
- The whole file is read into memory, which is fine for typical outputs but not
  ideal for very long MD runs.
- The SCF trend classification and the cutoff-ratio check are heuristics. They are
  meant to point in the right direction, not to replace a convergence study.
- Output formats change between QE versions. Fixtures cover 6.0 to 7.5; please open an
  issue with the output file if something is parsed wrongly.

## License

MIT, see [LICENSE](LICENSE). The QE output files under `tests/data/qe/` come from
Quantum ESPRESSO, which is distributed under the GNU GPL; see
[`tests/data/README.md`](tests/data/README.md).

If you use Quantum ESPRESSO results in a publication, cite QE as requested at
<https://www.quantum-espresso.org/quote>.
