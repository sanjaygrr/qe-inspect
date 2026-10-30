# Test data

All files are unmodified standard output of Quantum ESPRESSO programs.

## `qe/`: from the Quantum ESPRESSO repository

Copied from <https://github.com/QEF/q-e> at commit
`61569eb480231b649c47f631df9c5c83537df461` (branch `develop`, October 2026).
Quantum ESPRESSO is free software distributed under the GNU General Public License
(version 2 or later); these output files are redistributed here, unchanged, under
the same terms, with credit to the Quantum ESPRESSO developers.

| File | Source in the QE repository | QE version | What it covers |
| --- | --- | --- | --- |
| `pw_scf_si.out` | `test-suite/pw_scf/benchmark.out.git.inp=scf.in` | 6.1 | converged scf, insulator |
| `pw_scf_al_metal.out` | `test-suite/pw_metal/benchmark.out.git.inp=metal.in` | 6.1 | converged scf, metal with smearing |
| `pw_relax_co.out` | `test-suite/pw_relax/benchmark.out.git.inp=relax.in` | 6.1 | converged BFGS relax, ultrasoft, SCF-correction warning |
| `pw_vcrelax_as.out` | `test-suite/pw_vc-relax/benchmark.out.git.inp=vc-relax2.in` | 6.7GPU | converged vc-relax with damped (Wentzcovitch) dynamics, 4 MPI processes |
| `pw_scf_srvo3_maxstep1.out` | `PW/examples/example14/reference/srvo3.dmft_scf.out` | 6.8 | SCF stopped after one iteration (`convergence NOT achieved`) |
| `pw_scf_ar_vdwdf.out` | `PW/examples/vdwDF_example/reference/Ar.scf.out` | 6.4.1 | `%%%%` citation banner that is not an error; ignored input cards |
| `ph_si_gamma.out` | `test-suite/ph_base/benchmark.out.git.inp=si.phG.in.args=2` | 6.0 | ph.x at Gamma with dielectric part |
| `ph_ahc_error.out` | `test-suite/ph_ahc_bas/benchmark.out.git.inp=ahc.in.args=2` | 7.2 | ph.x stopped by `Error in routine` |

## `qe75/`: runs made for this project

The QE test suite has almost no failing runs, so these were run with `pw.x` 7.5
(macOS arm64 build, one MPI process) to cover common failure modes. The input of each
run is next to its output. All use bulk aluminium and the `Al.pz-vbc.UPF`
norm-conserving pseudopotential distributed with QE (not included here).

| File | What was done | Result |
| --- | --- | --- |
| `scf_maxstep` | `electron_maxstep = 4` with `conv_thr = 1e-10` | `convergence NOT achieved after 4 iterations` |
| `relax_nstep` | two-atom cell with a displaced atom, `nstep = 3` | `The maximum number of steps has been reached.` |
| `vcrelax_al` | fcc Al starting from a stretched lattice | converged vc-relax with final scf |
| `crash_too_few_bands` | `nbnd = 1` for a metal with 3 electrons | `Error in routine setup (1): too few bands` |
| `scf_walltime` | `max_seconds = 3` with a dense k-point grid | `Maximum CPU time exceeded` |
| `aborted_no_message` | same input as `scf_walltime` but with the default Davidson solver | this build aborted through `MPI_ABORT` in the first SCF iteration without printing an error block; kept as a real example of a run that dies without an explanation in the output |
