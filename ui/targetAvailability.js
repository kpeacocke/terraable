export function describeBlockers(auth) {
  const blockers = auth?.blockers || [];
  if (!blockers.length) {
    return "configured for selected portal";
  }
  return blockers.join("; ");
}

export function buildTargetAvailability(authByTarget, selectedTarget, targetOrder) {
  const order = Array.isArray(targetOrder) ? targetOrder : Object.keys(authByTarget || {});
  const rows = order.map((target) => {
    const auth = authByTarget?.[target] || {};
    const ready = Boolean(auth.ready);
    return {
      target,
      ready,
      reason: describeBlockers(auth),
    };
  });

  const readyTargets = rows.filter((row) => row.ready).map((row) => row.target);
  const selectedRow = rows.find((row) => row.target === selectedTarget) || null;

  let fallbackTarget = selectedTarget;
  if ((!selectedRow || !selectedRow.ready) && readyTargets.length > 0) {
    fallbackTarget = readyTargets[0];
  }

  const resolvedSelected = rows.find((row) => row.target === fallbackTarget) || selectedRow;
  const selectedMessage = resolvedSelected
    ? resolvedSelected.ready
      ? `Selected target ${resolvedSelected.target} is available.`
      : `Selected target ${resolvedSelected.target} is unavailable: ${resolvedSelected.reason}.`
    : "Target availability unknown while authentication checks are loading.";

  return {
    rows,
    readyTargets,
    fallbackTarget,
    selectedMessage,
  };
}
