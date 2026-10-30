from pathlib import Path

import pytest

DATA = Path(__file__).parent / "data"


@pytest.fixture
def data():
    return DATA
