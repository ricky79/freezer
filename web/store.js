// Applicazione locale delle operazioni: stesse regole di freezer/ops.py, sui soli lotti attivi.

const EDITABLE_FIELDS = ['description', 'category', 'quantity', 'unit', 'expiry'];

export function applyOp(lots, op) {
  switch (op.type) {
    case 'add':
      if (lots.some((lot) => lot.id === op.lot.id)) return lots;
      return [...lots, { ...op.lot }];
    case 'take':
      return lots.flatMap((lot) => {
        if (lot.id !== op.lot_id) return [lot];
        const quantity = Math.max(0, lot.quantity - op.amount);
        return quantity > 0 ? [{ ...lot, quantity }] : [];
      });
    case 'edit':
      return lots.map((lot) => (lot.id === op.lot_id ? { ...lot, ...op.fields } : lot));
    case 'delete':
      return lots.filter((lot) => lot.id !== op.lot_id);
    default:
      return lots;
  }
}

export function compareLots(a, b) {
  if (a.expiry !== b.expiry) return a.expiry < b.expiry ? -1 : 1;
  return a.description.localeCompare(b.description, 'it', { sensitivity: 'base' });
}

export function viewLots(lots, queue) {
  return queue.reduce((current, op) => applyOp(current, op), lots).slice().sort(compareLots);
}

export function removeSent(queue, sentIds) {
  return queue.filter((op) => !sentIds.has(op.op_id));
}

export function makeOp(type, payload, { uuid = () => crypto.randomUUID(), now = () => new Date().toISOString() } = {}) {
  return { op_id: uuid(), type, at: now(), ...payload };
}

export function changedFields(original, updated) {
  const fields = {};
  for (const key of EDITABLE_FIELDS) {
    if (updated[key] !== original[key]) fields[key] = updated[key];
  }
  return fields;
}
