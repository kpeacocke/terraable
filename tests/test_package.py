import pytest

import terraable


@pytest.mark.unit
def test_package_importable() -> None:
    assert terraable.__version__ == "0.1.0"
    assert terraable.TargetPlatform.OPENSHIFT.value == "openshift"
    assert terraable.TargetPlatform.GCP.value == "gcp"
    assert terraable.TargetPlatform.VMWARE.value == "vmware"
    assert terraable.TargetPlatform.PARALLELS.value == "parallels"
    assert terraable.TargetPlatform.HYPER_V.value == "hyper-v"
    assert terraable.PortalImplementation.RHDH.value == "rhdh"
    assert terraable.HcpTerraformConfig(token="test").hostname == "app.terraform.io"
