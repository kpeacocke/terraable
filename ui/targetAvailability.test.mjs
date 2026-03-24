import test from "node:test";
import assert from "node:assert/strict";

import { buildTargetAvailability } from "./targetAvailability.mjs";

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

test("reports availability-unknown reason when auth entry is missing", () => {
  // authByTarget has no entry for 'gcp'; the target was in targetOrder but not yet returned by the API
  const view = buildTargetAvailability(
    {
      "local-lab": { ready: true, blockers: [] },
    },
    "gcp",
    ["local-lab", "gcp"],
  );

  const gcpRow = view.rows.find((r) => r.target === "gcp");
  assert.equal(gcpRow.known, false);
  assert.equal(gcpRow.ready, false);
  assert.match(gcpRow.reason, /not yet loaded/i);
  // Falls back to local-lab since gcp has no auth data
  assert.equal(view.fallbackTarget, "local-lab");
});
