# UI

Control-plane UI for selector input, action dispatch, and evidence/status display.

Preconditions:
- Start the backend API with `python -m terraable.api_server` from the repository root.

Open `http://127.0.0.1:8000` in a browser to exercise the live local-lab flow.

Failure mode:
- If the masthead badge shows `API offline`, the page is not connected to the backend and no actions will run.
