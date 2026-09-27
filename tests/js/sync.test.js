import { test, assert, assertEqual } from './harness.js';
import { removeSent } from '../../web/store.js';
import { createSyncer } from '../../web/sync.js';

const op = (id) => ({ op_id: id, type: 'delete', lot_id: 'x' });
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
const okResponse = (data = { lots: [] }) => ({ ok: true, status: 200, json: async () => data });

function setup(initialQueue, fetchImpl, timeoutMs = 5000) {
  const state = { queue: initialQueue, successes: [], failures: [] };
  const syncer = createSyncer({
    getQueue: () => state.queue,
    onSuccess: (data, sentIds) => {
      state.successes.push({ data, sentIds });
      state.queue = removeSent(state.queue, sentIds);
    },
    onFailure: (error) => state.failures.push(error),
    fetchImpl,
    timeoutMs,
  });
  return { state, syncer };
}

function recordingFetch(respond = () => okResponse()) {
  const calls = [];
  const fetchImpl = async (url, options = {}) => {
    calls.push({ url, method: options.method ?? 'GET', body: options.body ? JSON.parse(options.body) : null });
    return respond(url, options);
  };
  return { calls, fetchImpl };
}

test('coda vuota: chiede solo l\'istantanea', async () => {
  const { calls, fetchImpl } = recordingFetch(() => okResponse({ lots: ['L'] }));
  const { state, syncer } = setup([], fetchImpl);
  await syncer.syncNow();
  assertEqual(calls.map((c) => `${c.method} ${c.url}`), ['GET /api/inventory']);
  assertEqual(state.successes[0].data, { lots: ['L'] });
  assertEqual(state.successes[0].sentIds.size, 0);
});

test('coda piena: invia le operazioni e le toglie dalla coda', async () => {
  const { calls, fetchImpl } = recordingFetch();
  const { state, syncer } = setup([op('a'), op('b')], fetchImpl);
  await syncer.syncNow();
  assertEqual(calls.map((c) => `${c.method} ${c.url}`), ['POST /api/sync']);
  assertEqual(calls[0].body.ops.map((o) => o.op_id), ['a', 'b']);
  assertEqual(state.queue, []);
  assertEqual(state.failures, []);
});

test('rete assente: la coda resta intatta', async () => {
  const { state, syncer } = setup([op('a')], async () => { throw new TypeError('Failed to fetch'); });
  await syncer.syncNow();
  assertEqual(state.queue.map((o) => o.op_id), ['a']);
  assertEqual(state.successes.length, 0);
  assertEqual(state.failures.length, 1);
});

test('errore HTTP: fallimento, coda intatta', async () => {
  const { state, syncer } = setup([op('a')], async () => ({ ok: false, status: 502, json: async () => ({}) }));
  await syncer.syncNow();
  assertEqual(state.failures[0].message, 'HTTP 502');
  assertEqual(state.queue.length, 1);
});

test('timeout: la richiesta viene annullata', async () => {
  const hanging = (url, { signal }) => new Promise((resolve, reject) => {
    signal.addEventListener('abort', () => reject(new DOMException('Annullata', 'AbortError')));
  });
  const { state, syncer } = setup([op('a')], hanging, 20);
  await syncer.syncNow();
  assertEqual(state.failures.length, 1);
  assertEqual(state.queue.length, 1);
});

test('una sola sincronizzazione alla volta, con un giro in più se richiesto', async () => {
  let inFlight = 0;
  let maxInFlight = 0;
  let count = 0;
  let release = null;
  const fetchImpl = () => {
    count += 1;
    inFlight += 1;
    maxInFlight = Math.max(maxInFlight, inFlight);
    return new Promise((resolve) => {
      release = () => { inFlight -= 1; resolve(okResponse()); };
    });
  };
  const { syncer } = setup([op('a')], fetchImpl);
  const first = syncer.syncNow();
  syncer.syncNow();
  await tick();
  release();
  await tick();
  release();
  await first;
  assertEqual(count, 2);
  assertEqual(maxInFlight, 1);
});

test('coda più lunga di 500: invio a blocchi', async () => {
  const { calls, fetchImpl } = recordingFetch();
  const queue = Array.from({ length: 1200 }, (_, i) => op(`op${i}`));
  const { state, syncer } = setup(queue, fetchImpl);
  await syncer.syncNow();
  assertEqual(calls.map((c) => c.body.ops.length), [500, 500, 200]);
  assertEqual(calls[1].body.ops[0].op_id, 'op500');
  assertEqual(state.queue, []);
});

test('operazione aggiunta durante l\'invio: resta in coda e parte al giro dopo', async () => {
  const bodies = [];
  let release = null;
  const fetchImpl = (url, options) => {
    bodies.push(JSON.parse(options.body));
    return new Promise((resolve) => { release = () => resolve(okResponse()); });
  };
  const { state, syncer } = setup([op('a')], fetchImpl);
  const done = syncer.syncNow();
  state.queue = [...state.queue, op('nuova')];
  release();
  await tick();
  release();
  await done;
  assertEqual(bodies.map((b) => b.ops.map((o) => o.op_id)), [['a'], ['nuova']]);
  assert(state.queue.length === 0, 'coda vuota alla fine');
});
