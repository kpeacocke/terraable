# Offline / Mock Mode

Offline mode supports deterministic rehearsal runs using simulated outcomes and pre-seeded evidence. No live HCP Terraform, AAP, or cloud credentials are needed.

## When to use

- Screenshot and screen-recording sessions where live infra is unavailable
- Presenter rehearsal before a live demo
- CI validation of UI and orchestrator logic without external dependencies

## How it works

Set `TERRAABLE_MOCK_MODE=true` before starting the API server. When mock mode is active, `LocalLabBackend` bypasses all credential requirements and returns deterministic pre-seeded responses for every action — no live HCP Terraform, AAP, or cloud credentials are needed.

## Quick start

```bash
cp .env.example .env
# Ensure TERRAABLE_MOCK_MODE=true is set in .env

source .venv/bin/activate
TERRAABLE_MOCK_MODE=true python -m terraable.api_server --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` in a browser. All UI actions (create, baseline, scan, drift, remediate) work immediately with no credentials.

## Pre-seeded mock scenarios

| Scenario | How to trigger |
|----------|---------------|
| Clean environment | Open UI, click **Create environment** |
| SSH drift detected | Click **Inject SSH drift**, then **Run compliance scan** |
| Service health drift | Click **Inject service drift**, then **Run compliance scan** |
| EDA auto-remediation | Enable EDA in the selector before injecting drift |
| Full remediation | After drift, click **Run remediation** to restore all controls |

## Mock data location

Sample mock scan output JSON files are in [mock-data/](./mock-data/):

- `scan-clean.json` — scan result with all controls passing
- `scan-ssh-drift.json` — scan result with SSH drift present
- `scan-service-drift.json` — scan result with service health drift

These files are not loaded by `LocalLabBackend` at runtime. They are provided as fixture inputs for integration tests, offline screenshot or recording scripts, and manual inspection of example scan payloads.
