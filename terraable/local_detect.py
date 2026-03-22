"""Local environment detection helpers for Phase 3 target suggestion."""

from __future__ import annotations

import os
from pathlib import Path


def detect_local_target() -> dict[str, str]:
    """Return a best-effort local target suggestion and rationale.

    The helper intentionally favours deterministic checks that work in
    containers and CI: explicit environment markers first, then host binaries.
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
