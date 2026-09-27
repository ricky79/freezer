import { test, assert, assertEqual } from './harness.js';
import { applyOp, changedFields, makeOp, removeSent, validateLot, viewLots } from '../../web/store.js';

const lot = (id, extra = {}) => ({
  id, description: 'Piselli', category: 'verdure', quantity: 5, unit: 'buste', expiry: '2027-01-31', ...extra,
});
const add = (l) => ({ op_id: `add-${l.id}`, type: 'add', lot: l });
const take = (id, amount, opId = `take-${id}-${amount}`) => ({ op_id: opId, type: 'take', lot_id: id, amount });

test('add aggiunge, add con id esistente è ignorata', () => {
  assertEqual(applyOp([], add(lot('a'))), [lot('a')]);
  assertEqual(applyOp([lot('a')], add(lot('a', { description: 'Altro' }))), [lot('a')]);
});

test('take riduce, e a zero o sotto toglie il lotto', () => {
  assertEqual(applyOp([lot('a')], take('a', 2)), [lot('a', { quantity: 3 })]);
  assertEqual(applyOp([lot('a')], take('a', 5)), []);
  assertEqual(applyOp([lot('a')], take('a', 9)), []);
  assertEqual(applyOp([lot('a')], take('manca', 1)), [lot('a')]);
});

test('aggiungi e poi prendi offline sullo stesso lotto', () => {
  assertEqual(viewLots([], [add(lot('a')), take('a', 2)]), [lot('a', { quantity: 3 })]);
});

test('edit unisce i campi, delete toglie', () => {
  const edited = applyOp([lot('a')], { op_id: 'e', type: 'edit', lot_id: 'a', fields: { quantity: 8 } });
  assertEqual(edited, [lot('a', { quantity: 8 })]);
  assertEqual(applyOp([lot('a')], { op_id: 'd', type: 'delete', lot_id: 'a' }), []);
  assertEqual(applyOp([lot('a')], { op_id: 'e2', type: 'edit', lot_id: 'manca', fields: { quantity: 1 } }), [lot('a')]);
});

test('viewLots non modifica l\'istantanea e ordina per scadenza e descrizione', () => {
  const snapshot = [
    lot('z', { description: 'zucchine', expiry: '2027-01-10' }),
    lot('b', { description: 'Burro', expiry: '2026-12-01' }),
    lot('a', { description: 'Àrista', expiry: '2027-01-10' }),
  ];
  const copy = JSON.parse(JSON.stringify(snapshot));
  const view = viewLots(snapshot, [take('b', 1)]);
  assertEqual(view.map((l) => l.id), ['b', 'a', 'z']);
  assertEqual(view[0].quantity, 4);
  assertEqual(snapshot, copy);
});

test('removeSent toglie solo le operazioni inviate', () => {
  const queue = [take('a', 1, 'op1'), take('a', 1, 'op2'), take('a', 1, 'op3')];
  assertEqual(removeSent(queue, new Set(['op1', 'op3'])).map((op) => op.op_id), ['op2']);
});

test('makeOp aggiunge op_id, tipo e ora', () => {
  const op = makeOp('take', { lot_id: 'a', amount: 2 }, { uuid: () => 'u1', now: () => 'T' });
  assertEqual(op, { op_id: 'u1', type: 'take', at: 'T', lot_id: 'a', amount: 2 });
  assert(typeof makeOp('delete', { lot_id: 'a' }).op_id === 'string', 'uuid di default');
});

test('changedFields restituisce solo i campi cambiati', () => {
  assertEqual(changedFields(lot('a'), { ...lot('a'), quantity: 3, expiry: '2027-02-01' }), {
    quantity: 3, expiry: '2027-02-01',
  });
  assertEqual(changedFields(lot('a'), lot('a')), {});
});

test('validateLot restituisce il primo errore in italiano', () => {
  const ok = { description: 'Ragù', category: 'sughi', unit: 'barattoli_grandi', quantity: 2, expiry: '2027-03-27' };
  assertEqual(validateLot(ok), null);
  assertEqual(validateLot({ ...ok, description: '' }), 'Scrivi una descrizione.');
  assertEqual(validateLot({ ...ok, description: 'x'.repeat(101) }), 'La descrizione può avere al massimo 100 caratteri.');
  assertEqual(validateLot({ ...ok, category: '' }), 'Scegli il tipo.');
  assertEqual(validateLot({ ...ok, unit: '' }), 'Scegli l\'unità.');
  assertEqual(validateLot({ ...ok, quantity: null }), 'La quantità deve essere un numero intero tra 1 e 99999.');
  assertEqual(validateLot({ ...ok, expiry: '' }), 'Scegli la data di scadenza.');
});
