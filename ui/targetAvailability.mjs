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

function isCredentialOnlyBlockers(blockers) {
  if (!Array.isArray(blockers) || blockers.length === 0) {
    return false;
  }
  return blockers.every((blocker) => /^missing credentials:/i.test(String(blocker)));
}

export function buildTargetAvailability(authByTarget, selectedTarget, targetOrder) {
  const order = Array.isArray(targetOrder) ? targetOrder : Object.keys(authByTarget || {});
  const rows = order.map((target) => {
    const known = Object.hasOwn(authByTarget || {}, target);
    const auth = known ? (authByTarget?.[target] ?? null) : null;
    const ready = Boolean(auth?.ready);
    const blockers = Array.isArray(auth?.blockers) ? auth.blockers : [];
    const credentialOnly = isCredentialOnlyBlockers(blockers);
    return {
      target,
      known,
      ready,
      selectable: ready || credentialOnly,
      reason: describeBlockers(auth),
    };
  });

  const readyTargets = rows.filter((row) => row.ready).map((row) => row.target);
  const selectedRow = rows.find((row) => row.target === selectedTarget) || null;

  let fallbackTarget = selectedTarget;
  if (selectedRow && !selectedRow.selectable && readyTargets.length > 0) {
    fallbackTarget = readyTargets[0];
  }

  const resolvedSelected = rows.find((row) => row.target === fallbackTarget) || selectedRow;
  let selectedMessage;
  if (!resolvedSelected) {
    selectedMessage = "Target availability unknown while authentication checks are loading.";
  } else if (resolvedSelected.ready) {
    selectedMessage = `Selected target ${resolvedSelected.target} is available.`;
  } else if (resolvedSelected.selectable) {
    selectedMessage = `Selected target ${resolvedSelected.target} needs credentials before actions can run: ${resolvedSelected.reason}.`;
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
