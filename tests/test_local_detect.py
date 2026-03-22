"""Tests for local environment target detection helper."""

from __future__ import annotations

from pathlib import Path

import pytest

from terraable.local_detect import detect_local_target


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
