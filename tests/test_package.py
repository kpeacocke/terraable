import pytest

import terraable


@pytest.mark.unit()
def test_package_importable() -> None:
    assert terraable.__version__ == "0.1.0"
