"""Tests for the executable local-lab backend."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.error import URLError

import pytest

from terraable.local_lab import (
    DRIFT_SERVICE_PLAYBOOK,
    EXECUTION_MODE_ENV_VAR,
    HCP_TOKEN_REQUIREMENT,
    MOCK_MODE_ENV_VAR,
    STATE_LOG_LIMIT,
    CommandResult,
    LocalLabBackend,
    default_runner,
)


class _FakeLocalLabBackend(LocalLabBackend):
    def __init__(self, workspace_root: Path) -> None:
        super().__init__(workspace_root, clock=lambda: 1_700_000_000.0)
        self.playbook_calls: list[str] = []

    def _terraform_apply(
        self,
        env_dir: Path,
        *,
        environment_name: str,
        portal: str,
        profile: str,
        target: str = "local-lab",
    ) -> dict[str, Any]:
        assert env_dir.exists()
        return {
            "environment_name": environment_name,
            "target_platform": target,
            "portal_impl": portal,
            "security_profile": profile,
            "connection": {
                "ansible_inventory_group": "local_lab",
                "ssh_user": "lab",
                "ssh_port": 22,
                "api_endpoint": "http://localhost:8080",
            },
        }

    def _run_playbook(self, playbook: str, extra_vars: dict[str, Any]) -> dict[str, Any]:
        self.playbook_calls.append(playbook)
        env_dir = Path(str(extra_vars["sshd_config_path"])).parent

        handlers = {
            "playbooks/aap_operationalise.yml": self._handle_operationalise,
            "playbooks/drift_ssh_root.yml": self._handle_ssh_drift,
            "playbooks/remediate_ssh_root.yml": self._handle_ssh_remediation,
            "playbooks/compliance_scan.yml": self._handle_ssh_scan,
            DRIFT_SERVICE_PLAYBOOK: self._handle_service_playbook,
        }

        handler = handlers.get(playbook)
        if handler is None:
            raise AssertionError(f"Unexpected playbook call: {playbook}")
        handler(env_dir, extra_vars)
        return {
            "backend": "direct",
            "job_id": f"fake-{playbook}",
            "status": "successful",
            "playbook": playbook,
        }

    def _handle_operationalise(self, env_dir: Path, extra_vars: dict[str, Any]) -> None:
        del extra_vars
        (env_dir / "sshd_config").write_text(
            "PermitRootLogin no\nPasswordAuthentication no\n",
            encoding="utf-8",
        )
        (env_dir / "portal_service.state").write_text("active\n", encoding="utf-8")
        (env_dir / "portal_release.txt").write_text("portal=backstage\n", encoding="utf-8")

    def _handle_ssh_drift(self, env_dir: Path, extra_vars: dict[str, Any]) -> None:
        del extra_vars
        (env_dir / "sshd_config").write_text(
            "PermitRootLogin yes\nPasswordAuthentication no\n",
            encoding="utf-8",
        )

    def _handle_ssh_remediation(self, env_dir: Path, extra_vars: dict[str, Any]) -> None:
        del extra_vars
        (env_dir / "sshd_config").write_text(
            "PermitRootLogin no\nPasswordAuthentication no\n",
            encoding="utf-8",
        )

    def _handle_ssh_scan(self, env_dir: Path, extra_vars: dict[str, Any]) -> None:
        ssh_text = (env_dir / "sshd_config").read_text(encoding="utf-8")
        root_login_status = "pass" if "PermitRootLogin no" in ssh_text else "fail"
        password_auth_status = "pass" if "PasswordAuthentication no" in ssh_text else "fail"
        Path(str(extra_vars["scan_output_path"])).write_text(
            json.dumps(
                {
                    "control": "ssh_root_login",
                    "status": root_login_status,
                    "evidence": "fake ssh scan",
                    "ssh_password_authentication": password_auth_status,
                }
            ),
            encoding="utf-8",
        )

    def _handle_service_playbook(self, env_dir: Path, extra_vars: dict[str, Any]) -> None:
        action = str(extra_vars["drift_action"])
        service_file = env_dir / "portal_service.state"
        if action == "inject":
            service_file.write_text("stopped\n", encoding="utf-8")
            return
        if action == "remediate":
            service_file.write_text("active\n", encoding="utf-8")
            return

        current = service_file.read_text(encoding="utf-8").strip()
        status = "pass" if current == "active" else "fail"
        Path(str(extra_vars["scan_output_path"])).write_text(
            json.dumps(
                {
                    "control": "portal_service_health",
                    "status": status,
                    "evidence": f"service={current}",
                }
            ),
            encoding="utf-8",
        )


class _InspectableLocalLabBackend(LocalLabBackend):
    def __init__(self, workspace_root: Path, runner: Any | None = None) -> None:
        super().__init__(workspace_root, runner=runner)

    def run_command_for_test(
        self,
        argv: list[str],
        *,
        cwd: Path | None,
        env: dict[str, str] | None,
    ) -> CommandResult:
        return self._run(argv, cwd=cwd, env=env)

    def current_environment_for_test(self) -> dict[str, Any]:
        return self._current_environment()

    def terraform_apply_for_test(
        self,
        env_dir: Path,
        *,
        environment_name: str,
        portal: str,
        profile: str,
        target: str = "local-lab",
    ) -> dict[str, Any]:
        return self._terraform_apply(
            env_dir,
            environment_name=environment_name,
            portal=portal,
            profile=profile,
            target=target,
        )

    def ensure_environment_for_test(self, environment_name: str) -> Path:
        return self._ensure_environment(environment_name)

    def save_state_for_test(self, state: dict[str, Any]) -> None:
        self._save_state(state)

    def run_playbook_for_test(self, playbook: str, extra_vars: dict[str, Any]) -> dict[str, Any]:
        return self._run_playbook(playbook, extra_vars)

    def ansible_vars_for_test(self, env_dir: Path) -> dict[str, Any]:
        return self._ansible_vars(env_dir)


class _ActionLockProbeBackend(LocalLabBackend):
    def __init__(self, workspace_root: Path) -> None:
        super().__init__(workspace_root, clock=lambda: 1_700_000_000.0)
        self._probe_lock = threading.Lock()
        self._active_ensures = 0
        self.max_active_ensures = 0

    def _ensure_environment(self, environment_name: str) -> Path:
        with self._probe_lock:
            self._active_ensures += 1
            self.max_active_ensures = max(self.max_active_ensures, self._active_ensures)

        try:
            time.sleep(0.05)
            return super()._ensure_environment(environment_name)
        finally:
            with self._probe_lock:
                self._active_ensures -= 1


@pytest.mark.unit
def test_create_environment_builds_real_local_lab_state(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("HCP_TERRAFORM_TOKEN=test-token\n", encoding="utf-8")
    backend = _FakeLocalLabBackend(tmp_path)

    result = backend.create_environment(
        target="local-lab",
        portal="backstage",
        profile="strict",
        eda="enabled",
    )

    assert result["status"] == "succeeded"
    assert result["state"]["current"]["target"] == "local-lab"
    assert result["state"]["terraform"]["status"] == "applied"
    assert result["state"]["controls"] == {
        "ssh_root_login": False,
        "portal_service_health": False,
    }
    env_dir = tmp_path / ".terraable" / "local-lab" / "local-lab-1700000000"
    assert (env_dir / "inventory.yml").exists()
    assert (env_dir / "sshd_config").exists()
    assert (env_dir / "portal_service.state").exists()


@pytest.mark.unit
def test_create_environment_serializes_concurrent_requests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(MOCK_MODE_ENV_VAR, "true")
    backend = _ActionLockProbeBackend(tmp_path)
    start = threading.Event()
    failures: list[Exception] = []

    def worker() -> None:
        start.wait()
        try:
            backend.create_environment(
                target="local-lab",
                portal="backstage",
                profile="baseline",
                eda="disabled",
            )
        except Exception as exc:  # pragma: no cover - defensive guard
            failures.append(exc)

    thread_a = threading.Thread(target=worker)
    thread_b = threading.Thread(target=worker)
    thread_a.start()
    thread_b.start()
    start.set()
    thread_a.join()
    thread_b.join()

    assert not failures
    assert backend.max_active_ensures == 1


@pytest.mark.unit
def test_full_local_lab_lifecycle_updates_controls_and_eda_history(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("HCP_TERRAFORM_TOKEN=test-token\n", encoding="utf-8")
    backend = _FakeLocalLabBackend(tmp_path)
    backend.create_environment(
        target="local-lab",
        portal="backstage",
        profile="baseline",
        eda="enabled",
    )

    baseline = backend.apply_baseline()
    clean_scan = backend.run_compliance_scan()
    ssh_drift = backend.inject_ssh_drift()
    svc_drift = backend.inject_service_drift()
    scan = backend.run_compliance_scan()
    remediation = backend.run_remediation()

    assert baseline["state"]["controls"] == {
        "ssh_root_login": True,
        "portal_service_health": True,
    }
    assert baseline["state"]["compliance_controls"] == {
        "ssh_root_login": True,
        "ssh_password_authentication": True,
    }
    assert clean_scan["status"] == "succeeded"
    assert clean_scan["state"]["trend"][0] == {"pct": 100, "label": "Scan #1"}
    assert (
        ssh_drift["state"]["eda_history"][0]["message"]
        == "ssh_root_login drift injected - rulebook triggered"
    )
    assert svc_drift["state"]["controls"]["portal_service_health"] is False
    assert scan["status"] == "failed"
    assert scan["state"]["trend"][0] == {"pct": 33, "label": "Scan #2"}
    assert (
        scan["state"]["eda_history"][0]["message"]
        == "compliance_drift event emitted for ssh_root_login, portal_service_health"
    )
    assert remediation["state"]["controls"] == {
        "ssh_root_login": True,
        "portal_service_health": True,
    }
    assert remediation["state"]["jobs"]["last_action"] == "run_remediation"
    assert remediation["state"]["jobs"]["last_status"] == "succeeded"


@pytest.mark.unit
def test_non_local_target_is_rejected_until_provider_path_exists(tmp_path: Path) -> None:
    backend = _FakeLocalLabBackend(tmp_path)

    result = backend.create_environment(
        target="aws",
        portal="backstage",
        profile="baseline",
        eda="disabled",
    )

    assert result["status"] == "failed"
    assert "supported local targets" in result["detail"]


@pytest.mark.unit
def test_local_virtualisation_targets_are_executable(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("HCP_TERRAFORM_TOKEN=test-token\n", encoding="utf-8")
    backend = _FakeLocalLabBackend(tmp_path)

    result = backend.create_environment(
        target="vmware",
        portal="backstage",
        profile="baseline",
        eda="disabled",
    )

    assert result["status"] == "succeeded"
    assert result["state"]["current"]["target"] == "vmware"
    assert result["state"]["terraform"]["status"] == "applied"


@pytest.mark.unit
def test_default_runner_executes_subprocess() -> None:
    result = default_runner([sys.executable, "-c", "print('ok')"], None, None)

    assert result.stdout.strip() == "ok"
    assert result.stderr == ""


@pytest.mark.unit
def test_load_state_returns_default_for_malformed_json(tmp_path: Path) -> None:
    backend = _InspectableLocalLabBackend(tmp_path)
    backend.runtime_root.mkdir(parents=True, exist_ok=True)
    backend.state_file.write_text("{not-json", encoding="utf-8")

    state = backend.get_state()

    assert state["current"] is None
    assert state["controls"] == {"ssh_root_login": False, "portal_service_health": False}


@pytest.mark.unit
def test_load_state_returns_default_for_non_object_json(tmp_path: Path) -> None:
    backend = _InspectableLocalLabBackend(tmp_path)
    backend.runtime_root.mkdir(parents=True, exist_ok=True)
    backend.state_file.write_text("[]", encoding="utf-8")

    state = backend.get_state()

    assert state["current"] is None
    assert state["controls"] == {"ssh_root_login": False, "portal_service_health": False}


@pytest.mark.unit
def test_record_action_persists_evidence_entry(tmp_path: Path) -> None:
    backend = _InspectableLocalLabBackend(tmp_path)

    result = backend._record_action("unit_action", "succeeded", "unit detail", "ok")

    assert result["status"] == "succeeded"
    state = backend.get_state()
    assert state["evidence"]
    assert state["evidence"][0]["message"] == "unit detail"


@pytest.mark.unit
def test_append_eda_event_persists_history_entry(tmp_path: Path) -> None:
    backend = _InspectableLocalLabBackend(tmp_path)

    backend._append_eda_event("eda event detail", "warn")

    state = backend.get_state()
    assert state["eda_history"]
    assert state["eda_history"][0]["message"] == "eda event detail"


@pytest.mark.unit
def test_record_action_caps_evidence_history(tmp_path: Path) -> None:
    backend = _InspectableLocalLabBackend(tmp_path)

    for i in range(STATE_LOG_LIMIT + 5):
        backend._record_action("unit_action", "succeeded", f"detail-{i}", "ok")

    state = backend.get_state()
    evidence = state["evidence"]
    assert len(evidence) == STATE_LOG_LIMIT
    assert evidence[0]["message"] == f"detail-{STATE_LOG_LIMIT + 4}"


@pytest.mark.unit
def test_append_eda_event_caps_history(tmp_path: Path) -> None:
    backend = _InspectableLocalLabBackend(tmp_path)

    for i in range(STATE_LOG_LIMIT + 5):
        backend._append_eda_event(f"event-{i}", "warn")

    state = backend.get_state()
    eda_history = state["eda_history"]
    assert len(eda_history) == STATE_LOG_LIMIT
    assert eda_history[0]["message"] == f"event-{STATE_LOG_LIMIT + 4}"


@pytest.mark.unit
def test_run_wraps_called_process_error(tmp_path: Path) -> None:
    def boom(argv: list[str], cwd: Path | None, env: dict[str, str] | None) -> CommandResult:
        del argv, cwd, env
        raise subprocess.CalledProcessError(1, ["cmd"], output="", stderr="broken")

    backend = _InspectableLocalLabBackend(tmp_path, runner=boom)

    with pytest.raises(RuntimeError, match="broken"):
        backend.run_command_for_test(["cmd"], cwd=None, env=None)


@pytest.mark.unit
def test_run_wraps_file_not_found_error(tmp_path: Path) -> None:
    def missing(argv: list[str], cwd: Path | None, env: dict[str, str] | None) -> CommandResult:
        del argv, cwd, env
        raise FileNotFoundError("missing executable")

    backend = _InspectableLocalLabBackend(tmp_path, runner=missing)

    with pytest.raises(RuntimeError, match="missing executable"):
        backend.run_command_for_test(["cmd"], cwd=None, env=None)


@pytest.mark.unit
def test_current_environment_requires_active_state(tmp_path: Path) -> None:
    backend = _InspectableLocalLabBackend(tmp_path)

    with pytest.raises(RuntimeError, match="No environment has been created yet"):
        backend.current_environment_for_test()


@pytest.mark.unit
def test_terraform_apply_runs_init_apply_and_output(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def runner(argv: list[str], cwd: Path | None, env: dict[str, str] | None) -> CommandResult:
        del env
        calls.append(argv)
        assert cwd == tmp_path
        if "output" in argv:
            return CommandResult(
                stdout=json.dumps(
                    {
                        "environment_name": {"value": "demo"},
                        "target_platform": {"value": "local-lab"},
                        "portal_impl": {"value": "backstage"},
                        "security_profile": {"value": "baseline"},
                        "connection": {
                            "value": {
                                "ansible_inventory_group": "local_lab",
                                "ssh_user": "lab",
                                "ssh_port": 22,
                                "api_endpoint": "http://localhost:8080",
                            }
                        },
                    }
                ),
                stderr="",
            )
        return CommandResult(stdout="", stderr="")

    backend = _InspectableLocalLabBackend(tmp_path, runner=runner)
    env_dir = tmp_path / ".terraable" / "local-lab" / "demo"
    env_dir.mkdir(parents=True)

    outputs = backend.terraform_apply_for_test(
        env_dir,
        environment_name="demo",
        portal="backstage",
        profile="baseline",
    )

    assert outputs["environment_name"] == "demo"
    assert len(calls) == 3
    assert calls[0][2] == "init"
    assert calls[1][2] == "apply"
    assert calls[2][2] == "output"


@pytest.mark.unit
def test_run_playbook_uses_local_inventory_and_ansible_config(tmp_path: Path) -> None:
    calls: list[tuple[list[str], Path | None, dict[str, str] | None]] = []

    def runner(argv: list[str], cwd: Path | None, env: dict[str, str] | None) -> CommandResult:
        calls.append((argv, cwd, env))
        return CommandResult(stdout="", stderr="")

    backend = _InspectableLocalLabBackend(tmp_path, runner=runner)
    env_dir = backend.ensure_environment_for_test("demo")
    backend.save_state_for_test(
        {
            "current": {
                "environment_name": "demo",
                "target": "local-lab",
                "portal": "backstage",
                "profile": "baseline",
                "eda": "disabled",
                "runtime_dir": str(env_dir),
                "runtime_vars": {
                    "connection": {"ansible_inventory_group": "local_lab"},
                    "portal_impl": "backstage",
                    "security_profile": "baseline",
                },
            },
            "controls": {"ssh_root_login": False, "portal_service_health": False},
            "evidence": [],
            "eda_history": [],
            "trend": [],
            "scan_count": 0,
            "eda_enabled": False,
        }
    )

    backend.run_playbook_for_test(
        "playbooks/compliance_scan.yml", backend.ansible_vars_for_test(env_dir)
    )

    argv, cwd, env = calls[0]
    assert argv[0].endswith(("python", "python3"))
    assert argv[1:5] == ["-m", "ansible.cli.playbook", "-i", str(env_dir / "inventory.yml")]
    assert cwd == tmp_path / "ansible"
    assert env is not None
    assert env["ANSIBLE_CONFIG"] == str(tmp_path / "ansible" / "ansible.cfg")


@pytest.mark.unit
def test_auth_status_uses_dotenv_credentials(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "HCP_TERRAFORM_TOKEN=from-dotenv\n",
        encoding="utf-8",
    )
    backend = _InspectableLocalLabBackend(tmp_path)

    auth = backend.get_auth_status(target="local-lab", portal="backstage")
    tf_token_key = backend._tf_token_env_var()

    assert auth["authenticated"] is True
    assert auth["ready"] is True
    assert auth["missing_credentials"] == []
    assert auth["credential_sources"] == {tf_token_key: "dotenv (from HCP_TERRAFORM_TOKEN)"}


@pytest.mark.unit
def test_auth_status_marks_missing_and_unsupported_target(tmp_path: Path) -> None:
    backend = _InspectableLocalLabBackend(tmp_path)

    auth = backend.get_auth_status(target="aws", portal="backstage")
    tf_token_key = backend._tf_token_env_var()

    assert auth["authenticated"] is False
    assert auth["ready"] is False
    assert auth["missing_credentials"] == [
        tf_token_key,
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
    ]
    assert "target=aws is not executable yet; select local-lab" in auth["blockers"]


@pytest.mark.unit
def test_configure_credentials_merges_ui_values(tmp_path: Path) -> None:
    backend = _InspectableLocalLabBackend(tmp_path)

    auth = backend.configure_credentials({"HCP_TERRAFORM_TOKEN": "from-ui"})
    tf_token_key = backend._tf_token_env_var()

    assert auth["authenticated"] is True
    assert auth["ready"] is True
    assert auth["credential_sources"] == {tf_token_key: "ui (from HCP_TERRAFORM_TOKEN)"}


@pytest.mark.unit
def test_create_environment_requires_ready_auth(tmp_path: Path) -> None:
    backend = _FakeLocalLabBackend(tmp_path)

    result = backend.create_environment(
        target="local-lab",
        portal="backstage",
        profile="baseline",
        eda="disabled",
    )

    assert result["status"] == "failed"
    assert "create_environment blocked:" in result["detail"]


@pytest.mark.unit
def test_get_state_includes_auth_summary(tmp_path: Path) -> None:
    backend = _InspectableLocalLabBackend(tmp_path)
    state = backend.get_state()

    assert "auth" in state
    assert state["auth"]["ready"] is False
    assert "target_suggestion" in state
    assert "observability" in state


@pytest.mark.unit
def test_configure_credentials_ignores_unknown_and_can_clear_ui_value(tmp_path: Path) -> None:
    backend = _InspectableLocalLabBackend(tmp_path)
    backend.configure_credentials(
        {
            "HCP_TERRAFORM_TOKEN": "token",
            "NOT_A_REAL_KEY": "ignored",
        }
    )

    auth_after_clear = backend.configure_credentials({"HCP_TERRAFORM_TOKEN": "   "})
    tf_token_key = backend._tf_token_env_var()

    assert auth_after_clear["authenticated"] is False
    assert tf_token_key in auth_after_clear["missing_credentials"]


@pytest.mark.unit
def test_configure_credentials_clear_restores_dotenv_value(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("HCP_TERRAFORM_TOKEN=from-dotenv\n", encoding="utf-8")
    backend = _InspectableLocalLabBackend(tmp_path)
    tf_token_key = backend._tf_token_env_var()

    auth_after_ui = backend.configure_credentials({"HCP_TERRAFORM_TOKEN": "from-ui"})
    assert auth_after_ui["credential_sources"] == {tf_token_key: "ui (from HCP_TERRAFORM_TOKEN)"}

    auth_after_clear = backend.configure_credentials({"HCP_TERRAFORM_TOKEN": "   "})

    assert auth_after_clear["authenticated"] is True
    assert auth_after_clear["ready"] is True
    assert auth_after_clear["credential_sources"] == {
        tf_token_key: "dotenv (from HCP_TERRAFORM_TOKEN)"
    }


@pytest.mark.unit
def test_configure_credentials_clear_restores_dotenv_after_ui_update(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("HCP_TERRAFORM_TOKEN=from-dotenv\n", encoding="utf-8")
    backend = _InspectableLocalLabBackend(tmp_path)
    tf_token_key = backend._tf_token_env_var()

    backend.configure_credentials({"HCP_TERRAFORM_TOKEN": "from-ui-1"})
    auth_after_second_ui = backend.configure_credentials({"HCP_TERRAFORM_TOKEN": "from-ui-2"})
    assert auth_after_second_ui["credential_sources"] == {
        tf_token_key: "ui (from HCP_TERRAFORM_TOKEN)"
    }

    auth_after_clear = backend.configure_credentials({"HCP_TERRAFORM_TOKEN": ""})

    assert auth_after_clear["credential_sources"] == {
        tf_token_key: "dotenv (from HCP_TERRAFORM_TOKEN)"
    }


@pytest.mark.unit
def test_configure_credentials_returns_auth_for_requested_target(tmp_path: Path) -> None:
    backend = _InspectableLocalLabBackend(tmp_path)

    auth = backend.configure_credentials(
        {"HCP_TERRAFORM_TOKEN": "token"},
        target="aws",
        portal="backstage",
    )

    # AWS requires additional credentials; token alone is insufficient.
    assert auth["ready"] is False
    assert "AWS_ACCESS_KEY_ID" in auth["missing_credentials"]


@pytest.mark.unit
def test_get_auth_status_includes_portal_blocker(tmp_path: Path) -> None:
    backend = _InspectableLocalLabBackend(tmp_path)
    backend.configure_credentials({"HCP_TERRAFORM_TOKEN": "token"})

    auth = backend.get_auth_status(target="local-lab", portal="custom")

    assert auth["authenticated"] is True
    assert auth["ready"] is False
    assert "portal=custom is not supported" in auth["blockers"]


@pytest.mark.unit
def test_local_lab_rhdh_portal_marked_ready(tmp_path: Path) -> None:
    backend = _InspectableLocalLabBackend(tmp_path)
    backend.configure_credentials({"HCP_TERRAFORM_TOKEN": "token"})

    auth = backend.get_auth_status(target="local-lab", portal="rhdh")

    assert auth["authenticated"] is True
    assert auth["ready"] is True


@pytest.mark.unit
def test_create_environment_allows_local_lab_rhdh(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("HCP_TERRAFORM_TOKEN=test-token\n", encoding="utf-8")
    backend = _FakeLocalLabBackend(tmp_path)

    result = backend.create_environment(
        target="local-lab",
        portal="rhdh",
        profile="baseline",
        eda="disabled",
    )

    assert result["status"] == "succeeded"
    assert result["state"]["current"]["portal"] == "rhdh"


@pytest.mark.unit
def test_unknown_target_uses_hostname_tf_token_requirement(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("TERRAABLE_TFC_HOSTNAME", "app.terraform.io")
    monkeypatch.setenv("TF_TOKEN_app_terraform_io", "token")
    backend = _InspectableLocalLabBackend(tmp_path)

    auth = backend.get_auth_status(target="future-target", portal="backstage")

    assert "TF_TOKEN_app_terraform_io" in auth["required_credentials"]
    assert "TF_TOKEN_app_terraform_io" not in auth["missing_credentials"]


@pytest.mark.unit
def test_bootstrap_prefers_environment_over_dotenv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / ".env").write_text("HCP_TERRAFORM_TOKEN=from-dotenv\n", encoding="utf-8")
    monkeypatch.setenv("HCP_TERRAFORM_TOKEN", "from-env")

    backend = _InspectableLocalLabBackend(tmp_path)
    auth = backend.get_auth_status(target="local-lab", portal="backstage")
    tf_token_key = backend._tf_token_env_var()

    assert auth["credential_sources"] == {tf_token_key: "env (from HCP_TERRAFORM_TOKEN)"}


@pytest.mark.unit
def test_read_dotenv_missing_file_returns_empty(tmp_path: Path) -> None:
    backend = _InspectableLocalLabBackend(tmp_path)

    loaded = backend._read_dotenv(tmp_path / "missing.env")

    assert loaded == {}


@pytest.mark.unit
def test_read_dotenv_skips_comments_and_invalid_lines(tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "# comment\nINVALID_LINE\nHCP_TERRAFORM_TOKEN=from-dotenv\n",
        encoding="utf-8",
    )
    backend = _InspectableLocalLabBackend(tmp_path)

    loaded = backend._read_dotenv(dotenv_path)

    assert loaded == {"HCP_TERRAFORM_TOKEN": "from-dotenv"}


@pytest.mark.unit
def test_credential_value_prefers_hostname_specific_token_and_non_token_value(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("TERRAABLE_TFC_HOSTNAME", "app.terraform.io")
    monkeypatch.setenv("TF_TOKEN_app_terraform_io", "hostname-token")
    backend = _InspectableLocalLabBackend(tmp_path)

    backend.configure_credentials(
        {
            "HCP_TERRAFORM_TOKEN": "alias-token",
            "AWS_ACCESS_KEY_ID": "aws-key",
        }
    )

    assert backend._credential_value(HCP_TOKEN_REQUIREMENT) == "hostname-token"
    assert backend._credential_value("AWS_ACCESS_KEY_ID") == "aws-key"


@pytest.mark.unit
def test_auth_source_includes_hostname_specific_and_non_token_sources(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("TERRAABLE_TFC_HOSTNAME", "app.terraform.io")
    monkeypatch.setenv("TF_TOKEN_app_terraform_io", "hostname-token")
    backend = _InspectableLocalLabBackend(tmp_path)
    tf_token_key = backend._tf_token_env_var()

    backend.configure_credentials({"AWS_ACCESS_KEY_ID": "aws-key"})

    sources = backend._auth_source((HCP_TOKEN_REQUIREMENT, "AWS_ACCESS_KEY_ID"))

    assert sources[tf_token_key] == "env"
    assert sources["AWS_ACCESS_KEY_ID"] == "ui"


@pytest.mark.unit
def test_mock_mode_auth_is_always_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(MOCK_MODE_ENV_VAR, "true")
    backend = LocalLabBackend(tmp_path)

    auth = backend.get_auth_status(target="any-target", portal="any-portal")

    assert auth["ready"] is True
    assert auth["missing_credentials"] == []
    assert auth["blockers"] == []


@pytest.mark.unit
def test_mock_mode_state_reports_offline_mock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(MOCK_MODE_ENV_VAR, "true")
    backend = LocalLabBackend(tmp_path)

    state = backend.get_state()

    assert state["mode"] == "offline-mock"
    assert state["auth"]["ready"] is True


@pytest.mark.unit
def test_mock_mode_full_lifecycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(MOCK_MODE_ENV_VAR, "true")
    backend = LocalLabBackend(tmp_path, clock=lambda: 1_700_000_000.0)

    result = backend.create_environment(
        target="local-lab", portal="backstage", profile="cis", eda="disabled"
    )
    assert result["status"] == "succeeded"
    assert "mock" in result["detail"]
    current = backend.get_state()["current"]
    assert current is not None
    assert "runtime_dir" in current
    assert "runtime_vars" in current

    result = backend.apply_baseline()
    assert result["status"] == "succeeded"
    assert result["state"]["controls"]["ssh_root_login"] is True

    result = backend.run_compliance_scan()
    assert result["status"] == "succeeded"

    result = backend.inject_ssh_drift()
    assert result["status"] == "succeeded"
    assert result["state"]["controls"]["ssh_root_login"] is False

    result = backend.run_compliance_scan()
    assert result["status"] == "failed"
    assert "ssh_root_login" in result["detail"]

    result = backend.inject_service_drift()
    assert result["status"] == "succeeded"
    assert result["state"]["controls"]["portal_service_health"] is False

    result = backend.run_remediation()
    assert result["status"] == "succeeded"
    state = backend.get_state()
    assert state["controls"]["ssh_root_login"] is True
    assert state["controls"]["portal_service_health"] is True
    assert state["compliance_controls"]["ssh_root_login"] is True


@pytest.mark.unit
def test_mock_mode_eda_events_on_drift_and_remediation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(MOCK_MODE_ENV_VAR, "true")
    backend = LocalLabBackend(tmp_path, clock=lambda: 1_700_000_000.0)

    backend.create_environment(target="local-lab", portal="backstage", profile="cis", eda="enabled")

    result = backend.inject_ssh_drift()
    assert "state" in result
    state = backend.get_state()
    assert any("ssh_root_login" in e["message"] for e in state["eda_history"])

    result = backend.inject_service_drift()
    assert "state" in result
    state = backend.get_state()
    assert any("portal_service_health" in e["message"] for e in state["eda_history"])

    backend.inject_ssh_drift()  # set ssh drift again for scan
    result = backend.run_compliance_scan()
    assert "state" in result

    result = backend.run_remediation()
    assert "state" in result
    state = backend.get_state()
    assert any("remediation complete" in e["message"] for e in state["eda_history"])


@pytest.mark.unit
def test_inject_synthetic_incident_updates_feed_and_evidence(tmp_path: Path) -> None:
    backend = _InspectableLocalLabBackend(tmp_path)

    result = backend.inject_synthetic_incident()

    assert result["status"] == "succeeded"
    state = backend.get_state()
    assert state["incidents"]
    assert state["incidents"][0]["id"].startswith("incident-")
    assert any("synthetic incident" in item["message"] for item in state["evidence"])


@pytest.mark.unit
def test_awx_execution_mode_requires_awx_connection_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(EXECUTION_MODE_ENV_VAR, "awx")
    backend = _InspectableLocalLabBackend(tmp_path)
    backend.configure_credentials({"HCP_TERRAFORM_TOKEN": "token"})

    auth = backend.get_auth_status(target="local-lab", portal="backstage")

    assert auth["authenticated"] is True
    assert auth["ready"] is False
    assert any("awx execution mode requires" in blocker for blocker in auth["blockers"])


@pytest.mark.unit
def test_awx_execution_mode_requires_https_host_for_ready_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(EXECUTION_MODE_ENV_VAR, "awx")
    monkeypatch.setenv("AWX_HOST", "http://awx.example.invalid")
    monkeypatch.setenv("AWX_USERNAME", "admin")
    monkeypatch.setenv("AWX_PASSWORD", "password")
    backend = _InspectableLocalLabBackend(tmp_path)
    backend.configure_credentials({"HCP_TERRAFORM_TOKEN": "token"})

    auth = backend.get_auth_status(target="local-lab", portal="backstage")

    assert auth["ready"] is False
    assert "AWX_HOST must use an https:// URL" in auth["blockers"]


@pytest.mark.unit
def test_run_playbook_awx_mode_launches_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(EXECUTION_MODE_ENV_VAR, "awx")
    monkeypatch.setenv("AWX_HOST", "https://awx.example.invalid")
    monkeypatch.setenv("AWX_USERNAME", "admin")
    monkeypatch.setenv("AWX_PASSWORD", "password")
    backend = _InspectableLocalLabBackend(tmp_path)

    requests: list[tuple[str, str]] = []

    def fake_awx_request(
        host: str,
        username: str,
        password: str,
        path: str,
        *,
        method: str,
        body: bytes | None = None,
    ) -> dict[str, Any]:
        del host, username, password, body
        requests.append((method, path))
        if path.startswith("/api/v2/job_templates/?name="):
            return {"results": [{"id": 42}]}
        if path == "/api/v2/job_templates/42/launch/":
            return {"job": 99}
        if path == "/api/v2/jobs/99/":
            return {"status": "successful"}
        raise AssertionError(f"Unexpected AWX path: {path}")

    monkeypatch.setattr(backend, "_awx_request", fake_awx_request)

    result = backend.run_playbook_for_test(
        "playbooks/compliance_scan.yml",
        {"target_group": "all"},
    )

    assert result["backend"] == "awx"
    assert result["job_id"] == "99"
    assert requests[0][0] == "GET"
    assert requests[1][0] == "POST"
    assert requests[2][0] == "GET"


@pytest.mark.unit
def test_invalid_execution_mode_defaults_to_direct(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(EXECUTION_MODE_ENV_VAR, "invalid-mode")
    backend = _InspectableLocalLabBackend(tmp_path)

    state = backend.get_state()

    assert state["controller_mode"] == "direct"


@pytest.mark.unit
def test_awx_run_rejects_unmapped_playbook(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(EXECUTION_MODE_ENV_VAR, "awx")
    backend = _InspectableLocalLabBackend(tmp_path)

    with pytest.raises(RuntimeError, match="No AWX template mapping"):
        backend._run_awx_job_template("playbooks/unknown.yml", {})


@pytest.mark.unit
def test_awx_run_requires_awx_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(EXECUTION_MODE_ENV_VAR, "awx")
    backend = _InspectableLocalLabBackend(tmp_path)

    with pytest.raises(RuntimeError, match="AWX execution requires"):
        backend._run_awx_job_template("playbooks/compliance_scan.yml", {})


@pytest.mark.unit
def test_awx_run_requires_https_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(EXECUTION_MODE_ENV_VAR, "awx")
    monkeypatch.setenv("AWX_HOST", "http://awx.example.invalid")
    monkeypatch.setenv("AWX_USERNAME", "admin")
    monkeypatch.setenv("AWX_PASSWORD", "password")
    backend = _InspectableLocalLabBackend(tmp_path)

    with pytest.raises(RuntimeError, match="AWX_HOST must use an https:// URL"):
        backend._run_awx_job_template("playbooks/compliance_scan.yml", {})


@pytest.mark.unit
def test_awx_run_raises_when_template_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(EXECUTION_MODE_ENV_VAR, "awx")
    monkeypatch.setenv("AWX_HOST", "https://awx.example.invalid")
    monkeypatch.setenv("AWX_USERNAME", "admin")
    monkeypatch.setenv("AWX_PASSWORD", "password")
    backend = _InspectableLocalLabBackend(tmp_path)

    def fake_awx_request(*args: object, **kwargs: object) -> dict[str, Any]:
        del args, kwargs
        return {"results": []}

    monkeypatch.setattr(backend, "_awx_request", fake_awx_request)

    with pytest.raises(RuntimeError, match="AWX template not found"):
        backend._run_awx_job_template("playbooks/compliance_scan.yml", {})


@pytest.mark.unit
def test_awx_run_raises_when_launch_missing_job_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(EXECUTION_MODE_ENV_VAR, "awx")
    monkeypatch.setenv("AWX_HOST", "https://awx.example.invalid")
    monkeypatch.setenv("AWX_USERNAME", "admin")
    monkeypatch.setenv("AWX_PASSWORD", "password")
    backend = _InspectableLocalLabBackend(tmp_path)

    def fake_awx_request(
        host: str,
        username: str,
        password: str,
        path: str,
        *,
        method: str,
        body: bytes | None = None,
    ) -> dict[str, Any]:
        del host, username, password, method, body
        if path.startswith("/api/v2/job_templates/?name="):
            return {"results": [{"id": 42}]}
        if path == "/api/v2/job_templates/42/launch/":
            return {}
        raise AssertionError(f"Unexpected path {path}")

    monkeypatch.setattr(backend, "_awx_request", fake_awx_request)

    with pytest.raises(RuntimeError, match="did not return job id"):
        backend._run_awx_job_template("playbooks/compliance_scan.yml", {})


@pytest.mark.unit
def test_awx_run_raises_when_job_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(EXECUTION_MODE_ENV_VAR, "awx")
    monkeypatch.setenv("AWX_HOST", "https://awx.example.invalid")
    monkeypatch.setenv("AWX_USERNAME", "admin")
    monkeypatch.setenv("AWX_PASSWORD", "password")
    backend = _InspectableLocalLabBackend(tmp_path)

    def fake_awx_request(
        host: str,
        username: str,
        password: str,
        path: str,
        *,
        method: str,
        body: bytes | None = None,
    ) -> dict[str, Any]:
        del host, username, password, method, body
        if path.startswith("/api/v2/job_templates/?name="):
            return {"results": [{"id": 42}]}
        if path == "/api/v2/job_templates/42/launch/":
            return {"job": 99}
        if path == "/api/v2/jobs/99/":
            return {"status": "failed"}
        raise AssertionError(f"Unexpected path {path}")

    monkeypatch.setattr(backend, "_awx_request", fake_awx_request)

    with pytest.raises(RuntimeError, match="ended with status failed"):
        backend._run_awx_job_template("playbooks/compliance_scan.yml", {})


@pytest.mark.unit
def test_awx_request_raises_on_non_object_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = _InspectableLocalLabBackend(tmp_path)

    class _Response:
        def __enter__(self) -> _Response:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(["not-an-object"]).encode("utf-8")

    monkeypatch.setattr("terraable.local_lab.urlopen", lambda req, timeout=30: _Response())

    with pytest.raises(RuntimeError, match="not a JSON object"):
        backend._awx_request(
            "https://awx.example.invalid",
            "admin",
            "password",
            "/api/v2/ping/",
            method="GET",
        )


@pytest.mark.unit
def test_awx_request_wraps_url_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    backend = _InspectableLocalLabBackend(tmp_path)

    def raise_url_error(req: object, timeout: int = 30) -> object:
        del req, timeout
        raise URLError("network down")

    monkeypatch.setattr("terraable.local_lab.urlopen", raise_url_error)

    with pytest.raises(RuntimeError, match="AWX API request failed"):
        backend._awx_request(
            "https://awx.example.invalid",
            "admin",
            "password",
            "/api/v2/ping/",
            method="GET",
        )


@pytest.mark.unit
def test_awx_run_raises_when_job_times_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(EXECUTION_MODE_ENV_VAR, "awx")
    monkeypatch.setenv("AWX_HOST", "https://awx.example.invalid")
    monkeypatch.setenv("AWX_USERNAME", "admin")
    monkeypatch.setenv("AWX_PASSWORD", "password")
    backend = _InspectableLocalLabBackend(tmp_path)

    def fake_awx_request(
        host: str,
        username: str,
        password: str,
        path: str,
        *,
        method: str,
        body: bytes | None = None,
    ) -> dict[str, Any]:
        del host, username, password, method, body
        if path.startswith("/api/v2/job_templates/?name="):
            return {"results": [{"id": 42}]}
        if path == "/api/v2/job_templates/42/launch/":
            return {"job": 99}
        if path == "/api/v2/jobs/99/":
            return {"status": "running"}
        raise AssertionError(f"Unexpected path {path}")

    monkeypatch.setattr(backend, "_awx_request", fake_awx_request)
    monkeypatch.setattr("terraable.local_lab.time.sleep", lambda seconds: None)

    with pytest.raises(RuntimeError, match="timed out"):
        backend._run_awx_job_template("playbooks/compliance_scan.yml", {})


@pytest.mark.unit
def test_awx_request_returns_json_object(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    backend = _InspectableLocalLabBackend(tmp_path)

    class _Response:
        def __enter__(self) -> _Response:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"status": "ok"}).encode("utf-8")

    monkeypatch.setattr("terraable.local_lab.urlopen", lambda req, timeout=30: _Response())

    payload = backend._awx_request(
        "https://awx.example.invalid",
        "admin",
        "password",
        "/api/v2/ping/",
        method="GET",
    )

    assert payload == {"status": "ok"}


@pytest.mark.unit
def test_awx_request_raises_on_json_decode_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = _InspectableLocalLabBackend(tmp_path)

    class _Response:
        def __enter__(self) -> _Response:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def read(self) -> bytes:
            return b"{invalid-json"

    monkeypatch.setattr("terraable.local_lab.urlopen", lambda req, timeout=30: _Response())

    with pytest.raises(RuntimeError, match="AWX API response parse failed"):
        backend._awx_request(
            "https://awx.example.invalid",
            "admin",
            "password",
            "/api/v2/ping/",
            method="GET",
        )


@pytest.mark.unit
def test_apply_baseline_marks_failed_job_status_on_exception(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("HCP_TERRAFORM_TOKEN=test-token\n", encoding="utf-8")
    backend = _FakeLocalLabBackend(tmp_path)
    backend.create_environment(
        target="local-lab",
        portal="backstage",
        profile="baseline",
        eda="disabled",
    )

    def failing_run_playbook(playbook: str, extra_vars: dict[str, Any]) -> dict[str, Any]:
        del playbook, extra_vars
        raise RuntimeError("playbook failed")

    backend._run_playbook = failing_run_playbook  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="playbook failed"):
        backend.apply_baseline()

    state = backend.get_state()
    assert state["jobs"]["last_action"] == "apply_baseline"
    assert state["jobs"]["last_status"] == "failed"


@pytest.mark.unit
def test_run_compliance_scan_marks_failed_job_status_on_exception(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("HCP_TERRAFORM_TOKEN=test-token\n", encoding="utf-8")
    backend = _FakeLocalLabBackend(tmp_path)
    backend.create_environment(
        target="local-lab",
        portal="backstage",
        profile="baseline",
        eda="disabled",
    )

    def failing_run_playbook(playbook: str, extra_vars: dict[str, Any]) -> dict[str, Any]:
        del playbook, extra_vars
        raise RuntimeError("scan playbook failed")

    backend._run_playbook = failing_run_playbook  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="scan playbook failed"):
        backend.run_compliance_scan()

    state = backend.get_state()
    assert state["jobs"]["last_action"] == "run_compliance_scan"
    assert state["jobs"]["last_status"] == "failed"


@pytest.mark.unit
def test_inject_ssh_drift_marks_failed_job_status_on_exception(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("HCP_TERRAFORM_TOKEN=test-token\n", encoding="utf-8")
    backend = _FakeLocalLabBackend(tmp_path)
    backend.create_environment(
        target="local-lab",
        portal="backstage",
        profile="baseline",
        eda="disabled",
    )

    def failing_run_playbook(playbook: str, extra_vars: dict[str, Any]) -> dict[str, Any]:
        del playbook, extra_vars
        raise RuntimeError("ssh drift playbook failed")

    backend._run_playbook = failing_run_playbook  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="ssh drift playbook failed"):
        backend.inject_ssh_drift()

    state = backend.get_state()
    assert state["jobs"]["last_action"] == "inject_ssh_drift"
    assert state["jobs"]["last_status"] == "failed"


@pytest.mark.unit
def test_inject_service_drift_marks_failed_job_status_on_exception(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("HCP_TERRAFORM_TOKEN=test-token\n", encoding="utf-8")
    backend = _FakeLocalLabBackend(tmp_path)
    backend.create_environment(
        target="local-lab",
        portal="backstage",
        profile="baseline",
        eda="disabled",
    )

    def failing_run_playbook(playbook: str, extra_vars: dict[str, Any]) -> dict[str, Any]:
        del playbook, extra_vars
        raise RuntimeError("service drift playbook failed")

    backend._run_playbook = failing_run_playbook  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="service drift playbook failed"):
        backend.inject_service_drift()

    state = backend.get_state()
    assert state["jobs"]["last_action"] == "inject_service_drift"
    assert state["jobs"]["last_status"] == "failed"


@pytest.mark.unit
def test_run_remediation_marks_failed_job_status_on_exception(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("HCP_TERRAFORM_TOKEN=test-token\n", encoding="utf-8")
    backend = _FakeLocalLabBackend(tmp_path)
    backend.create_environment(
        target="local-lab",
        portal="backstage",
        profile="baseline",
        eda="disabled",
    )

    def failing_run_playbook(playbook: str, extra_vars: dict[str, Any]) -> dict[str, Any]:
        del playbook, extra_vars
        raise RuntimeError("remediation playbook failed")

    backend._run_playbook = failing_run_playbook  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="remediation playbook failed"):
        backend.run_remediation()

    state = backend.get_state()
    assert state["jobs"]["last_action"] == "run_remediation"
    assert state["jobs"]["last_status"] == "failed"


@pytest.mark.unit
def test_current_environment_requires_runtime_context(tmp_path: Path) -> None:
    backend = _InspectableLocalLabBackend(tmp_path)
    backend.save_state_for_test(
        {
            "current": {
                "environment_name": "broken",
                "target": "local-lab",
                "portal": "backstage",
                "profile": "baseline",
                "eda": "disabled",
            }
        }
    )

    with pytest.raises(RuntimeError, match="missing runtime context"):
        backend.current_environment_for_test()
