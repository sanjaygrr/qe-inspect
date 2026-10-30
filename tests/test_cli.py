import json

from qe_inspect.cli import main

from conftest import DATA


def test_text_output(capsys):
    rc = main(["--no-color", str(DATA / "qe75/relax_nstep.out")])
    out = capsys.readouterr().out
    assert rc == 1
    assert "Status: FAILED" in out
    assert "Geometry optimization hit nstep" in out


def test_ok_exit_code(capsys):
    assert main(["--no-color", str(DATA / "qe/pw_scf_si.out")]) == 0


def test_json_output(capsys):
    main(["--json", str(DATA / "qe75/scf_maxstep.out")])
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "failed"
    assert data["run"]["scf_cycles"][0]["converged"] is False
    assert data["findings"][0]["code"] == "scf_not_converged"


def test_directory_table(capsys):
    main(["--no-color", str(DATA)])
    out = capsys.readouterr().out
    assert "relax_nstep.out" in out
    assert "ph_si_gamma.out" in out
    assert "14 run(s)" in out


def test_directory_json(capsys):
    main(["--json", str(DATA / "qe")])
    data = json.loads(capsys.readouterr().out)
    assert isinstance(data, list) and len(data) == 8


def test_html_report(tmp_path, capsys):
    out = tmp_path / "r.html"
    main([str(DATA / "qe75/relax_nstep.out"), "--html", str(out)])
    html = out.read_text()
    assert html.startswith("<!doctype html>")
    assert "<svg" in html
    assert "http" not in html.split("<body>")[0].replace("http-equiv", "")


def test_not_a_qe_file(tmp_path, capsys):
    f = tmp_path / "x.out"
    f.write_text("hello\n")
    assert main([str(f)]) == 2


def test_missing_file(capsys):
    assert main(["/nonexistent/file.out"]) == 2
