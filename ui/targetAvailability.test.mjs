import test from "node:test";
import assert from "node:assert/strict";

import { buildTargetAvailability } from "./targetAvailability.js";

test("keeps selected target when ready", () => {
  const view = buildTargetAvailability(
    {
      "local-lab": { ready: true, blockers: [] },
      aws: { ready: false, blockers: ["missing credentials: AWS_ACCESS_KEY_ID"] },
    },
    "local-lab",
    ["aws", "local-lab"],
  );

  assert.equal(view.fallbackTarget, "local-lab");
  assert.match(view.selectedMessage, /selected target local-lab is available/i);
});

test("falls back to first ready target when selected target unavailable", () => {
  const view = buildTargetAvailability(
    {
      aws: { ready: false, blockers: ["missing credentials: AWS_ACCESS_KEY_ID"] },
      azure: { ready: false, blockers: ["missing credentials: ARM_CLIENT_ID"] },
      "local-lab": { ready: true, blockers: [] },
    },
    "aws",
    ["aws", "azure", "local-lab"],
  );

  assert.equal(view.fallbackTarget, "local-lab");
  assert.equal(view.rows[0].target, "aws");
  assert.equal(view.rows[0].ready, false);
  assert.match(view.rows[0].reason, /missing credentials/i);
});

test("keeps selected target when none are ready and reports blocker reason", () => {
  const view = buildTargetAvailability(
    {
      aws: {
        ready: false,
        blockers: ["missing credentials: AWS_ACCESS_KEY_ID", "AWX_HOST must use an https:// URL"],
      },
      azure: { ready: false, blockers: ["missing credentials: ARM_CLIENT_ID"] },
    },
    "aws",
    ["aws", "azure"],
  );

  assert.equal(view.fallbackTarget, "aws");
  assert.match(view.selectedMessage, /unavailable/i);
  assert.match(view.selectedMessage, /AWX_HOST must use an https:\/\//i);
});
