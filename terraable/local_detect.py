"""Local environment detection helpers for Phase 3 target suggestion."""

from __future__ import annotations

import os
from pathlib import Path


def _is_container_runtime() -> bool:
    dockerenv = Path("/.dockerenv")
    if dockerenv.exists():
        return True

    cgroup_path = Path("/proc/1/cgroup")
    try:
        if cgroup_path.exists():
            cgroup_text = cgroup_path.read_text(encoding="utf-8").lower()
            container_markers = ("docker", "containerd", "kubepods", "podman")
            return any(marker in cgroup_text for marker in container_markers)
    except (OSError, UnicodeDecodeError):
        return False
    return False


def runtime_target_availability() -> dict[str, dict[str, str | bool]]:
    """Return runtime capability checks used for target readiness.

    This is intentionally conservative for containerized runs: host-level hypervisor
    substrates are marked unavailable unless explicitly overridden.
    """

    is_container = _is_container_runtime()
    allow_container_hypervisors = os.getenv(
        "TERRAABLE_ALLOW_CONTAINER_HYPERVISOR_TARGETS", ""
    ).lower() in {"1", "true", "yes"}

    vmware_marker = bool(os.getenv("VMWARE_VERSION", "").strip()) or any(
        path.exists() for path in (Path("/usr/bin/vmrun"), Path("/usr/local/bin/vmrun"))
    )
    parallels_marker = bool(os.getenv("PARALLELS_VM_NAME", "").strip()) or any(
        path.exists() for path in (Path("/usr/bin/prlctl"), Path("/usr/local/bin/prlctl"))
    )

    hyperv_marker = bool(os.getenv("WSL_DISTRO_NAME", "").strip())
    osrelease_path = Path("/proc/sys/kernel/osrelease")
    try:
        if osrelease_path.exists():
            hyperv_marker = (
                hyperv_marker or "microsoft" in osrelease_path.read_text(encoding="utf-8").lower()
            )
    except (OSError, UnicodeDecodeError):
        pass

    shared_container_reason = (
        "container runtime detected; host hypervisor substrate is unavailable from this runtime"
    )

    def resolve_hypervisor_target(marker_found: bool, substrate_name: str) -> dict[str, str | bool]:
        if is_container and not allow_container_hypervisors:
            return {"available": False, "reason": shared_container_reason}
        if marker_found:
            return {"available": True, "reason": f"detected local substrate for {substrate_name}"}
        return {
            "available": False,
            "reason": f"{substrate_name} substrate markers were not detected on this runtime",
        }

    return {
        "local-lab": {
            "available": True,
            "reason": "local-lab is always executable in this runtime",
        },
        "gcp": {
            "available": True,
            "reason": "gcp execution depends on credentials and Terraform tooling checks",
        },
        "vmware": resolve_hypervisor_target(vmware_marker, "vmware"),
        "parallels": resolve_hypervisor_target(parallels_marker, "parallels"),
        "hyper-v": resolve_hypervisor_target(hyperv_marker, "hyper-v"),
    }


def detect_local_target() -> dict[str, str]:
    """Return a best-effort local target suggestion and rationale.

    Detection order (highest confidence first):
    1. Environment variables: ``VMWARE_VERSION``, ``PARALLELS_VM_NAME``, ``WSL_DISTRO_NAME``.
    2. Host binaries: ``vmrun`` (VMware), ``prlctl`` (Parallels).
    3. Kernel osrelease: ``microsoft`` in ``/proc/sys/kernel/osrelease`` → Hyper-V/WSL.
    4. Default fallback: ``local-lab``.

    Docker and KVM detection are not implemented here; those environments map to
    the ``local-lab`` default target and are not given a dedicated substrate module
    in the current phase.
    """

    env_markers = {
        "vmware": os.getenv("VMWARE_VERSION", ""),
        "parallels": os.getenv("PARALLELS_VM_NAME", ""),
        "hyper-v": os.getenv("WSL_DISTRO_NAME", ""),
    }
    for target, marker in env_markers.items():
        if marker.strip():
            return {
                "target": target,
                "confidence": "high",
                "reason": f"environment marker detected for {target}",
            }

    binary_markers = {
        "vmware": [Path("/usr/bin/vmrun"), Path("/usr/local/bin/vmrun")],
        "parallels": [Path("/usr/bin/prlctl"), Path("/usr/local/bin/prlctl")],
    }
    for target, candidates in binary_markers.items():
        if any(path.exists() for path in candidates):
            return {
                "target": target,
                "confidence": "medium",
                "reason": f"detected host binary for {target}",
            }

    osrelease_path = Path("/proc/sys/kernel/osrelease")
    try:
        if osrelease_path.exists():
            osrelease = osrelease_path.read_text(encoding="utf-8").lower()
            if "microsoft" in osrelease:
                return {
                    "target": "hyper-v",
                    "confidence": "medium",
                    "reason": "kernel indicates WSL/Hyper-V substrate",
                }
    except (OSError, UnicodeDecodeError):
        # Best-effort detection: on failure, fall back to the default suggestion below.
        pass

    return {
        "target": "local-lab",
        "confidence": "low",
        "reason": "no local hypervisor markers found; defaulting to local-lab",
    }
