"""Values below were checked by hand against the raw output files."""

import pytest

from qe_inspect.pw import parse_pw

from conftest import DATA


def test_scf_insulator():
    run = parse_pw(DATA / "qe/pw_scf_si.out")
    assert run.version == "6.1"
    assert run.calculation == "scf"
    assert run.job_done
    assert run.nat == 2 and run.ntyp == 1
    assert run.ecutwfc == 12.0 and run.ecutrho == 48.0
    assert run.pseudo_types == ["Norm-conserving"]
    assert len(run.scf_cycles) == 1
    cyc = run.scf_cycles[0]
    assert cyc.converged is True
    assert len(cyc.iterations) == 5
    assert run.energy_ry == pytest.approx(-15.79449593)
    assert cyc.homo_ev == pytest.approx(5.5371)
    assert cyc.pressure_kbar == pytest.approx(-30.30)
    assert run.wall_time_s == pytest.approx(0.15)


def test_scf_metal_fermi_and_smearing():
    run = parse_pw(DATA / "qe/pw_scf_al_metal.out")
    assert run.energy_ry == pytest.approx(-4.18546970)
    assert run.fermi_energy_ev == pytest.approx(8.3513)
    assert run.occupations.startswith("Marzari-Vanderbilt smearing")
    assert run.n_kpoints == 10


def test_scf_accuracy_history():
    run = parse_pw(DATA / "qe75/scf_maxstep.out")
    acc = run.scf_cycles[0].accuracies
    assert len(acc) == 4
    assert all(a > b for a, b in zip(acc, acc[1:]))
    assert run.conv_thr == pytest.approx(1e-10)


def test_relax_converged():
    run = parse_pw(DATA / "qe/pw_relax_co.out")
    assert run.calculation == "relax"
    assert run.ionic_status == "converged"
    assert run.ionic_steps == 5
    assert run.total_scf_iterations == 30
    assert run.energy_ry == pytest.approx(-43.10976799)
    assert run.scf_correction_warnings == 2
    assert {"Ultrasoft"} == set(run.pseudo_types)


def test_relax_max_steps():
    run = parse_pw(DATA / "qe75/relax_nstep.out")
    assert run.calculation == "relax"
    assert run.ionic_status == "max_steps"
    assert run.nstep == 3
    assert run.ionic_steps == 3
    last = run.scf_cycles[-1]
    assert last.total_force == pytest.approx(0.023721)
    assert last.bfgs_gradient_error == pytest.approx(1.7e-2)
    assert last.bfgs_energy_error == pytest.approx(6.2e-4)


def test_vcrelax_bfgs_with_final_scf():
    run = parse_pw(DATA / "qe75/vcrelax_al.out")
    assert run.calculation == "vc-relax"
    assert run.ionic_status == "converged"
    assert run.scf_cycles[-1].is_final_scf
    assert run.ionic_steps == 5
    assert run.final_enthalpy_ry == pytest.approx(-4.1943518337)
    assert run.scf_cycles[-1].pressure_kbar == pytest.approx(-0.22)
    assert run.scf_cycles[0].volume_bohr3 == pytest.approx(117.44669)
    assert run.press_conv_thr == pytest.approx(0.5)


def test_vcrelax_damped_dynamics():
    run = parse_pw(DATA / "qe/pw_vcrelax_as.out")
    assert run.version == "6.7GPU"
    assert run.calculation == "vc-relax"
    assert run.ionic_status == "converged"
    assert run.mpi_processes == 4
    assert run.energy_ry == pytest.approx(-25.40150714)
    assert run.integrated_charge == pytest.approx((10.00111789, 10.0))


def test_scf_not_converged():
    run = parse_pw(DATA / "qe/pw_scf_srvo3_maxstep1.out")
    cyc = run.scf_cycles[0]
    assert cyc.converged is False
    assert cyc.reported_iterations == 1
    assert run.energy_ry is None
    assert run.job_done


def test_crash_block_parsed():
    run = parse_pw(DATA / "qe75/crash_too_few_bands.out")
    assert run.error is not None
    assert run.error.routine == "setup"
    assert run.error.code == 1
    assert run.error.text == "too few bands"
    assert not run.job_done
    assert run.abort_marker.startswith("MPI_ABORT")


def test_citation_banner_is_not_an_error():
    run = parse_pw(DATA / "qe/pw_scf_ar_vdwdf.out")
    assert run.error is None
    assert run.job_done
    assert run.energy_ry == pytest.approx(-85.03249832)


def test_max_seconds():
    run = parse_pw(DATA / "qe75/scf_walltime.out")
    assert run.walltime_reached
    assert run.job_done
    assert run.scf_cycles[0].converged is None


def test_aborted_without_message():
    run = parse_pw(DATA / "qe75/aborted_no_message.out")
    assert not run.job_done
    assert run.error is None
    assert run.abort_marker is not None
    assert len(run.scf_cycles[0].iterations) == 1


def test_truncated_file_does_not_raise():
    lines = (DATA / "qe/pw_relax_co.out").read_text().splitlines()
    for cut in (5, 50, 120, 300, 500):
        run = parse_pw("partial.out", lines[:cut])
        assert not run.job_done
