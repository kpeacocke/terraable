"""Tests for local environment target detection helper."""

from __future__ import annotations

from pathlib import Path

import pytest

from terraable.local_detect import detect_local_target, runtime_target_availability


@pytest.mark.unit
def test_detect_local_target_from_environment_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VMWARE_VERSION", "17")

    detected = detect_local_target()

    assert detected["target"] == "vmware"
    assert detected["confidence"] == "high"


@pytest.mark.unit
def test_detect_local_target_from_binary_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VMWARE_VERSION", raising=False)
    monkeypatch.delenv("PARALLELS_VM_NAME", raising=False)
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)

    original_exists = Path.exists

    def fake_exists(path: Path) -> bool:
        return str(path) == "/usr/bin/prlctl" or original_exists(path)

    monkeypatch.setattr(Path, "exists", fake_exists)

    detected = detect_local_target()

    assert detected["target"] == "parallels"
    assert detected["confidence"] == "medium"


@pytest.mark.unit
def test_detect_local_target_defaults_to_local_lab(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VMWARE_VERSION", raising=False)
    monkeypatch.delenv("PARALLELS_VM_NAME", raising=False)
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)

    original_exists = Path.exists
    original_read_text = Path.read_text

    def fake_exists(path: Path) -> bool:
        if str(path) in {
            "/usr/bin/vmrun",
            "/usr/local/bin/vmrun",
            "/usr/bin/prlctl",
            "/usr/local/bin/prlctl",
            "/proc/sys/kernel/osrelease",
        }:
            return False
        return original_exists(path)

    def fake_read_text(path: Path, encoding: str = "utf-8") -> str:
        if str(path) == "/proc/sys/kernel/osrelease":
            return "linux"
        return original_read_text(path, encoding=encoding)

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(Path, "read_text", fake_read_text)

    detected = detect_local_target()

    assert detected["target"] == "local-lab"
    assert detected["confidence"] == "low"


@pytest.mark.unit
def test_detect_local_target_from_kernel_wsl_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VMWARE_VERSION", raising=False)
    monkeypatch.delenv("PARALLELS_VM_NAME", raising=False)
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)

    original_exists = Path.exists
    original_read_text = Path.read_text

    def fake_exists(path: Path) -> bool:
        if str(path) in {
            "/usr/bin/vmrun",
            "/usr/local/bin/vmrun",
            "/usr/bin/prlctl",
            "/usr/local/bin/prlctl",
        }:
            return False
        if str(path) == "/proc/sys/kernel/osrelease":
            return True
        return original_exists(path)

    def fake_read_text(path: Path, encoding: str = "utf-8") -> str:
        if str(path) == "/proc/sys/kernel/osrelease":
            return "5.15.90.1-microsoft-standard-WSL2"
        return original_read_text(path, encoding=encoding)

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(Path, "read_text", fake_read_text)

    detected = detect_local_target()

    assert detected["target"] == "hyper-v"
    assert detected["confidence"] == "medium"


@pytest.mark.unit
def test_detect_local_target_handles_osrelease_read_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test fallback when osrelease read fails with exception."""
    monkeypatch.delenv("VMWARE_VERSION", raising=False)
    monkeypatch.delenv("PARALLELS_VM_NAME", raising=False)
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)

    original_exists = Path.exists
    original_read_text = Path.read_text

    def fake_exists(path: Path) -> bool:
        if str(path) in {
            "/usr/bin/vmrun",
            "/usr/local/bin/vmrun",
            "/usr/bin/prlctl",
            "/usr/local/bin/prlctl",
        }:
            return False
        if str(path) == "/proc/sys/kernel/osrelease":
            return True
        return original_exists(path)

    def fake_read_text(path: Path, encoding: str = "utf-8") -> str:
        if str(path) == "/proc/sys/kernel/osrelease":
            raise OSError("permission denied")
        return original_read_text(path, encoding=encoding)

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(Path, "read_text", fake_read_text)

    detected = detect_local_target()

    assert detected["target"] == "local-lab"
    assert detected["confidence"] == "low"
    assert "no local hypervisor markers found" in detected["reason"]


@pytest.mark.unit
def test_runtime_target_availability_blocks_hypervisors_in_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TERRAABLE_ALLOW_CONTAINER_HYPERVISOR_TARGETS", raising=False)
    monkeypatch.delenv("VMWARE_VERSION", raising=False)
    monkeypatch.delenv("PARALLELS_VM_NAME", raising=False)
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)

    original_exists = Path.exists
    original_read_text = Path.read_text

    def fake_exists(path: Path) -> bool:
        if str(path) == "/.dockerenv":
            return True
        if str(path) == "/proc/1/cgroup":
            return False
        return original_exists(path)

    def fake_read_text(path: Path, encoding: str = "utf-8") -> str:
        if str(path) == "/proc/sys/kernel/osrelease":
            return "linux"
        return original_read_text(path, encoding=encoding)

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(Path, "read_text", fake_read_text)

    availability = runtime_target_availability()

    assert availability["local-lab"]["available"] is True
    assert availability["vmware"]["available"] is False
    assert availability["parallels"]["available"] is False
    assert availability["hyper-v"]["available"] is False
    assert "container runtime detected" in str(availability["vmware"]["reason"])


@pytest.mark.unit
def test_runtime_target_availability_allows_hypervisors_with_container_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TERRAABLE_ALLOW_CONTAINER_HYPERVISOR_TARGETS", "true")
    monkeypatch.setenv("VMWARE_VERSION", "17")
    monkeypatch.delenv("PARALLELS_VM_NAME", raising=False)
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")

    original_exists = Path.exists

    def fake_exists(path: Path) -> bool:
        if str(path) == "/.dockerenv":
            return True
        if str(path) in {"/usr/bin/prlctl", "/usr/local/bin/prlctl"}:
            return True
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", fake_exists)

    availability = runtime_target_availability()

    assert availability["vmware"]["available"] is True
    assert availability["parallels"]["available"] is True
    assert availability["hyper-v"]["available"] is True


@pytest.mark.unit
def test_runtime_target_availability_detects_container_from_cgroup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TERRAABLE_ALLOW_CONTAINER_HYPERVISOR_TARGETS", raising=False)
    monkeypatch.delenv("VMWARE_VERSION", raising=False)
    monkeypatch.delenv("PARALLELS_VM_NAME", raising=False)
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)

    original_exists = Path.exists
    original_read_text = Path.read_text

    def fake_exists(path: Path) -> bool:
        if str(path) == "/.dockerenv":
            return False
        if str(path) == "/proc/1/cgroup":
            return True
        return original_exists(path)

    def fake_read_text(path: Path, encoding: str = "utf-8") -> str:
        if str(path) == "/proc/1/cgroup":
            return "0::/docker/12345"
        if str(path) == "/proc/sys/kernel/osrelease":
            return "linux"
        return original_read_text(path, encoding=encoding)

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(Path, "read_text", fake_read_text)

    availability = runtime_target_availability()

    assert availability["vmware"]["available"] is False
    assert "container runtime detected" in str(availability["vmware"]["reason"])


@pytest.mark.unit
def test_runtime_target_availability_handles_cgroup_read_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VMWARE_VERSION", "17")
    monkeypatch.setenv("TERRAABLE_ALLOW_CONTAINER_HYPERVISOR_TARGETS", "true")

    original_exists = Path.exists
    original_read_text = Path.read_text

    def fake_exists(path: Path) -> bool:
        if str(path) == "/.dockerenv":
            return False
        if str(path) == "/proc/1/cgroup":
            return True
        return original_exists(path)

    def fake_read_text(path: Path, encoding: str = "utf-8") -> str:
        if str(path) == "/proc/1/cgroup":
            raise UnicodeDecodeError("utf-8", b"x", 0, 1, "bad")
        if str(path) == "/proc/sys/kernel/osrelease":
            return "linux"
        return original_read_text(path, encoding=encoding)

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(Path, "read_text", fake_read_text)

    availability = runtime_target_availability()

    assert availability["vmware"]["available"] is True


@pytest.mark.unit
def test_runtime_target_availability_non_container_without_markers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TERRAABLE_ALLOW_CONTAINER_HYPERVISOR_TARGETS", raising=False)
    monkeypatch.delenv("VMWARE_VERSION", raising=False)
    monkeypatch.delenv("PARALLELS_VM_NAME", raising=False)
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)

    original_exists = Path.exists
    original_read_text = Path.read_text

    def fake_exists(path: Path) -> bool:
        if str(path) in {"/.dockerenv", "/proc/1/cgroup"}:
            return False
        if str(path) == "/proc/sys/kernel/osrelease":
            return True
        if str(path) in {
            "/usr/bin/vmrun",
            "/usr/local/bin/vmrun",
            "/usr/bin/prlctl",
            "/usr/local/bin/prlctl",
        }:
            return False
        return original_exists(path)

    def fake_read_text(path: Path, encoding: str = "utf-8") -> str:
        if str(path) == "/proc/sys/kernel/osrelease":
            return "linux"
        return original_read_text(path, encoding=encoding)

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(Path, "read_text", fake_read_text)

    availability = runtime_target_availability()

    assert availability["vmware"]["available"] is False
    assert "substrate markers were not detected" in str(availability["vmware"]["reason"])


@pytest.mark.unit
def test_runtime_target_availability_sets_hyperv_from_osrelease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TERRAABLE_ALLOW_CONTAINER_HYPERVISOR_TARGETS", raising=False)
    monkeypatch.delenv("VMWARE_VERSION", raising=False)
    monkeypatch.delenv("PARALLELS_VM_NAME", raising=False)
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)

    original_exists = Path.exists
    original_read_text = Path.read_text

    def fake_exists(path: Path) -> bool:
        if str(path) in {"/.dockerenv", "/proc/1/cgroup"}:
            return False
        if str(path) == "/proc/sys/kernel/osrelease":
            return True
        if str(path) in {
            "/usr/bin/vmrun",
            "/usr/local/bin/vmrun",
            "/usr/bin/prlctl",
            "/usr/local/bin/prlctl",
        }:
            return False
        return original_exists(path)

    def fake_read_text(path: Path, encoding: str = "utf-8") -> str:
        if str(path) == "/proc/sys/kernel/osrelease":
            return "5.15.90.1-microsoft-standard-WSL2"
        return original_read_text(path, encoding=encoding)

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(Path, "read_text", fake_read_text)

    availability = runtime_target_availability()

    assert availability["hyper-v"]["available"] is True


@pytest.mark.unit
def test_runtime_target_availability_handles_osrelease_read_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TERRAABLE_ALLOW_CONTAINER_HYPERVISOR_TARGETS", raising=False)
    monkeypatch.delenv("VMWARE_VERSION", raising=False)
    monkeypatch.delenv("PARALLELS_VM_NAME", raising=False)
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)

    original_exists = Path.exists
    original_read_text = Path.read_text

    def fake_exists(path: Path) -> bool:
        if str(path) in {"/.dockerenv", "/proc/1/cgroup"}:
            return False
        if str(path) == "/proc/sys/kernel/osrelease":
            return True
        if str(path) in {
            "/usr/bin/vmrun",
            "/usr/local/bin/vmrun",
            "/usr/bin/prlctl",
            "/usr/local/bin/prlctl",
        }:
            return False
        return original_exists(path)

    def fake_read_text(path: Path, encoding: str = "utf-8") -> str:
        if str(path) == "/proc/sys/kernel/osrelease":
            raise OSError("permission denied")
        return original_read_text(path, encoding=encoding)

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(Path, "read_text", fake_read_text)

    availability = runtime_target_availability()

    assert availability["hyper-v"]["available"] is False
