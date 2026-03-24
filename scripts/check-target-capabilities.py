#!/usr/bin/env python3
"""Validate documentation target status against docs/target-capabilities.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def fail(message: str) -> None:
    print(f"target-capabilities: {message}", file=sys.stderr)
    raise SystemExit(1)


repo_root = Path(__file__).resolve().parents[1]
manifest_path = repo_root / "docs" / "target-capabilities.json"

try:
    manifest_text = manifest_path.read_text(encoding="utf-8")
except FileNotFoundError:
    fail(f"manifest file not found at {manifest_path}")

try:
    manifest = json.loads(manifest_text)
except json.JSONDecodeError as exc:
    fail(f"failed to parse JSON from manifest at {manifest_path}: {exc}")

README_MD = "README.md"
SHOWCASE_README_MD = "modes/showcase/README.md"

try:
    docs = {
        README_MD: (repo_root / README_MD).read_text(encoding="utf-8"),
        "docs/lab-guide.md": (repo_root / "docs" / "lab-guide.md").read_text(encoding="utf-8"),
        "docs/mvp-demo-runbook.md": (repo_root / "docs" / "mvp-demo-runbook.md").read_text(
            encoding="utf-8"
        ),
        SHOWCASE_README_MD: (repo_root / SHOWCASE_README_MD).read_text(encoding="utf-8"),
    }
except FileNotFoundError as exc:
    missing = getattr(exc, "filename", None) or "<unknown>"
    fail(f"documentation file not found: {missing}")

try:
    scripted = manifest["scripted_mvp_target"]
    if f"`{scripted} + backstage`" not in docs[README_MD]:
        fail(f"{README_MD} missing scripted MVP target reference")
    if f"`{scripted} + backstage`" not in docs["docs/mvp-demo-runbook.md"]:
        fail("docs/mvp-demo-runbook.md missing scripted MVP flow reference")

    for target in manifest["extended_live_targets"]:
        if f"`{target}`" not in docs[README_MD]:
            fail(f"{README_MD} missing extended live target `{target}`")

    for target, details in manifest["targets"].items():
        executable = bool(details["executable"])

        # Lab guide executable matrix.
        expected = "Yes" if executable else "No"
        if f"| `{target}` | {expected}" not in docs["docs/lab-guide.md"]:
            fail(f"docs/lab-guide.md target row for `{target}` is inconsistent with manifest")

    # Showcase status labels for key showcase targets.
    showcase_checks = {
        "local-lab": manifest["targets"]["local-lab"]["status_label"],
        "aws": manifest["targets"]["aws"]["status_label"],
        "azure": manifest["targets"]["azure"]["status_label"],
        "okd": manifest["targets"]["okd"]["status_label"],
        "openshift": manifest["targets"]["openshift"]["status_label"],
    }
    for target, label in showcase_checks.items():
        expected_row_fragment = f"| `{target}`"
        if (
            expected_row_fragment not in docs[SHOWCASE_README_MD]
            or label not in docs[SHOWCASE_README_MD]
        ):
            fail(f"{SHOWCASE_README_MD} missing expected status for `{target}`")
except (KeyError, TypeError) as exc:
    fail(f"invalid manifest structure in {manifest_path}: {exc}")

print("target-capabilities: OK")
