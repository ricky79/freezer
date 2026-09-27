import { test, assertEqual } from './harness.js';
import { createPersist } from '../../web/persist.js';

function memoryStorage() {
  const data = new Map();
  return {
    getItem: (key) => (data.has(key) ? data.get(key) : null),
    setItem: (key, value) => data.set(key, String(value)),
  };
}

test('salva e rilegge', () => {
  const persist = createPersist(memoryStorage());
  assertEqual(persist.save('k', { a: [1, 2] }), true);
  assertEqual(persist.load('k', null), { a: [1, 2] });
});

test('chiave assente restituisce il valore di default', () => {
  assertEqual(createPersist(memoryStorage()).load('manca', []), []);
});

test('JSON corrotto restituisce il valore di default', () => {
  const storage = memoryStorage();
  storage.setItem('k', '{rotto');
  assertEqual(createPersist(storage).load('k', 'default'), 'default');
});

test('storage che lancia eccezioni non blocca l\'app', () => {
  const broken = {
    getItem: () => { throw new Error('SecurityError'); },
    setItem: () => { throw new Error('QuotaExceededError'); },
  };
  const persist = createPersist(broken);
  assertEqual(persist.load('k', 1), 1);
  assertEqual(persist.save('k', 2), false);
});

test('storage assente', () => {
  const persist = createPersist(null);
  assertEqual(persist.load('k', 'x'), 'x');
  assertEqual(persist.save('k', 'y'), false);
});
