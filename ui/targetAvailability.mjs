export function describeBlockers(auth) {
  if (auth == null) {
    return "availability checks not yet loaded";
  }
  const blockers = auth.blockers || [];
  if (!blockers.length) {
    return "configured for selected portal";
  }
  return blockers.join("; ");
}

export function buildTargetAvailability(authByTarget, selectedTarget, targetOrder) {
  const order = Array.isArray(targetOrder) ? targetOrder : Object.keys(authByTarget || {});
  const rows = order.map((target) => {
    const auth = authByTarget?.[target] ?? null;
    const ready = Boolean(auth?.ready);
    return {
      target,
      ready,
      reason: describeBlockers(auth),
    };
  });

  const readyTargets = rows.filter((row) => row.ready).map((row) => row.target);
  const selectedRow = rows.find((row) => row.target === selectedTarget) || null;

  let fallbackTarget = selectedTarget;
  if (!selectedRow?.ready && readyTargets.length > 0) {
    fallbackTarget = readyTargets[0];
  }

  const resolvedSelected = rows.find((row) => row.target === fallbackTarget) || selectedRow;
  let selectedMessage;
  if (!resolvedSelected) {
    selectedMessage = "Target availability unknown while authentication checks are loading.";
  } else if (resolvedSelected.ready) {
    selectedMessage = `Selected target ${resolvedSelected.target} is available.`;
  } else {
    selectedMessage = `Selected target ${resolvedSelected.target} is unavailable: ${resolvedSelected.reason}.`;
  }

  return {
    rows,
    readyTargets,
    fallbackTarget,
    selectedMessage,
  };
}
