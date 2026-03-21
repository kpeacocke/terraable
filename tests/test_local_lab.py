"""Tests for the executable local-lab backend."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from terraable.local_lab import (
    DRIFT_SERVICE_PLAYBOOK,
    HCP_TOKEN_REQUIREMENT,
    MOCK_MODE_ENV_VAR,
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
    ) -> dict[str, Any]:
        assert env_dir.exists()
        return {
            "environment_name": environment_name,
            "target_platform": "local-lab",
            "portal_impl": portal,
            "security_profile": profile,
            "connection": {
                "ansible_inventory_group": "local_lab",
                "ssh_user": "lab",
                "ssh_port": 22,
                "api_endpoint": "http://localhost:8080",
            },
        }

    def _run_playbook(self, playbook: str, extra_vars: dict[str, Any]) -> None:
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
        status = "pass" if "PermitRootLogin no" in ssh_text else "fail"
        Path(str(extra_vars["scan_output_path"])).write_text(
            json.dumps(
                {
                    "control": "ssh_root_login",
                    "status": status,
                    "evidence": "fake ssh scan",
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
    ) -> dict[str, Any]:
        return self._terraform_apply(
            env_dir,
            environment_name=environment_name,
            portal=portal,
            profile=profile,
        )

    def ensure_environment_for_test(self, environment_name: str) -> Path:
        return self._ensure_environment(environment_name)

    def save_state_for_test(self, state: dict[str, Any]) -> None:
        self._save_state(state)

    def run_playbook_for_test(self, playbook: str, extra_vars: dict[str, Any]) -> None:
        self._run_playbook(playbook, extra_vars)

    def ansible_vars_for_test(self, env_dir: Path) -> dict[str, Any]:
        return self._ansible_vars(env_dir)


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
    assert result["state"]["controls"] == {
        "ssh_root_login": False,
        "portal_service_health": False,
    }
    env_dir = tmp_path / ".terraable" / "local-lab" / "local-lab-1700000000"
    assert (env_dir / "inventory.yml").exists()
    assert (env_dir / "sshd_config").exists()
    assert (env_dir / "portal_service.state").exists()


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
    assert clean_scan["status"] == "succeeded"
    assert clean_scan["state"]["trend"][0] == {"pct": 100, "label": "Scan #1"}
    assert (
        ssh_drift["state"]["eda_history"][0]["message"]
        == "ssh_root_login drift injected - rulebook triggered"
    )
    assert svc_drift["state"]["controls"]["portal_service_health"] is False
    assert scan["status"] == "failed"
    assert scan["state"]["trend"][0] == {"pct": 0, "label": "Scan #2"}
    assert (
        scan["state"]["eda_history"][0]["message"]
        == "compliance_drift event emitted for ssh_root_login, portal_service_health"
    )
    assert remediation["state"]["controls"] == {
        "ssh_root_login": True,
        "portal_service_health": True,
    }


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
    assert "only local-lab is wired end-to-end" in result["detail"]


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
def test_local_lab_rhdh_portal_not_marked_ready(tmp_path: Path) -> None:
    backend = _InspectableLocalLabBackend(tmp_path)
    backend.configure_credentials({"HCP_TERRAFORM_TOKEN": "token"})

    auth = backend.get_auth_status(target="local-lab", portal="rhdh")

    assert auth["authenticated"] is True
    assert auth["ready"] is False


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
