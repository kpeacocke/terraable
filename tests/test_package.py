import pytest

import terraable


@pytest.mark.unit()
def test_package_importable() -> None:
    assert terraable.__version__ == "0.1.0"
    assert terraable.TargetPlatform.OPENSHIFT.value == "openshift"
    assert terraable.PortalImplementation.RHDH.value == "rhdh"
    assert terraable.HcpTerraformConfig(token="test").hostname == "app.terraform.io"
