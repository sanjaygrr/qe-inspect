import pytest

from qe_inspect.ph import parse_ph

from conftest import DATA


def test_ph_gamma():
    run = parse_ph(DATA / "qe/ph_si_gamma.out")
    assert run.version == "6.0"
    assert run.job_done
    labels = [r.label for r in run.representations]
    assert labels[0] == "electric field"
    assert len(labels) == 3
    assert all(r.converged for r in run.representations[1:])
    assert len(run.q_points) == 1
    q = run.q_points[0]
    assert q.q == (0.0, 0.0, 0.0)
    assert q.frequencies_cm1[0] == pytest.approx(3.286472)
    assert q.frequencies_cm1[-1] == pytest.approx(510.157229)
    assert run.representations[1].iterations[-1].dvscf is not None


def test_ph_error():
    run = parse_ph(DATA / "qe/ph_ahc_error.out")
    assert run.error.routine == "elph_ahc_setup"
    assert "cannot be greater than nbnd" in run.error.text
    assert not run.job_done
