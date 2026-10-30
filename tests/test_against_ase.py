"""Cross-check energies with ASE's pw.x reader, when ASE is installed."""

import pytest

from qe_inspect.pw import parse_pw

from conftest import DATA

ase_io = pytest.importorskip("ase.io")
units = pytest.importorskip("ase.units")


@pytest.mark.parametrize(
    "path",
    [
        "qe/pw_scf_si.out",
        "qe/pw_scf_al_metal.out",
        "qe/pw_relax_co.out",
        "qe75/relax_nstep.out",
        "qe75/vcrelax_al.out",
    ],
)
def test_final_energy_matches_ase(path):
    run = parse_pw(DATA / path)
    images = ase_io.read(DATA / path, format="espresso-out", index=":")
    assert images, "ASE found no images"
    e_ase = images[-1].get_potential_energy()
    # ASE's reader converts Ry with an older CODATA set, hence the relative tolerance.
    assert run.energy_ry * units.Ry == pytest.approx(e_ase, rel=1e-6)
