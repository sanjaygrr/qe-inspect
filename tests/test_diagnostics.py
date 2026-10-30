import pytest

from qe_inspect.detect import parse_file
from qe_inspect.diagnostics import diagnose, scf_trend, status

from conftest import DATA


def codes(path):
    run = parse_file(DATA / path)
    findings = diagnose(run)
    return run, findings, {f.code for f in findings}


@pytest.mark.parametrize(
    "path, expected_status",
    [
        ("qe/pw_scf_si.out", "ok"),
        ("qe/pw_scf_al_metal.out", "ok"),
        ("qe/pw_scf_ar_vdwdf.out", "ok"),
        ("qe/pw_relax_co.out", "warnings"),
        ("qe/pw_vcrelax_as.out", "warnings"),
        ("qe/pw_scf_srvo3_maxstep1.out", "failed"),
        ("qe/ph_si_gamma.out", "ok"),
        ("qe/ph_ahc_error.out", "crashed"),
        ("qe75/scf_maxstep.out", "failed"),
        ("qe75/relax_nstep.out", "failed"),
        ("qe75/vcrelax_al.out", "ok"),
        ("qe75/crash_too_few_bands.out", "crashed"),
        ("qe75/scf_walltime.out", "stopped"),
        ("qe75/aborted_no_message.out", "incomplete"),
    ],
)
def test_status(path, expected_status):
    run, findings, _ = codes(path)
    assert status(run, findings) == expected_status


def test_scf_not_converged_short():
    _, findings, c = codes("qe75/scf_maxstep.out")
    assert "scf_not_converged" in c
    f = next(f for f in findings if f.code == "scf_not_converged")
    assert "electron_maxstep" in " ".join(f.suggestions)


def test_relax_max_steps_finding():
    _, findings, c = codes("qe75/relax_nstep.out")
    f = next(f for f in findings if f.code == "relax_max_steps")
    assert "nstep = 3" in f.explanation
    assert "1.7e-02" in f.explanation


def test_known_crash_explained():
    _, findings, _ = codes("qe75/crash_too_few_bands.out")
    assert findings[0].severity == "error"
    assert "nbnd" in findings[0].title


def test_cutoff_rule_of_thumb_for_ultrasoft():
    _, findings, c = codes("qe/pw_relax_co.out")
    assert "cutoff_ratio" in c
    assert "scf_correction_large" in c


def test_no_cutoff_note_for_norm_conserving_default():
    _, _, c = codes("qe/pw_scf_si.out")
    assert "cutoff_ratio" not in c


def test_input_card_warning_is_info():
    _, findings, _ = codes("qe75/relax_nstep.out")
    f = next(f for f in findings if f.code == "input_ignored")
    assert f.severity == "info"


def test_bfgs_curvature_is_info():
    _, findings, _ = codes("qe75/relax_nstep.out")
    f = next(f for f in findings if f.code == "bfgs_curvature")
    assert f.severity == "info"


def test_trend_oscillating():
    acc = [1e-2, 1e-3, 5e-3, 8e-4, 4e-3, 6e-4, 3e-3, 5e-4, 2e-3, 4e-4]
    assert scf_trend(acc).kind == "oscillating"


def test_trend_converging():
    acc = [10.0 ** (-k) for k in range(2, 12)]
    t = scf_trend(acc)
    assert t.kind == "converging"
    assert t.decades_per_iteration == pytest.approx(1.0)


def test_trend_stagnating():
    acc = [1e-4, 9e-5, 8.5e-5, 8e-5, 7.9e-5, 7.5e-5, 7.4e-5, 7.2e-5, 7e-5]
    assert scf_trend(acc).kind == "stagnating"


def test_trend_too_short():
    assert scf_trend([1e-3]).kind == "too_short"
