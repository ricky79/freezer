// Mini harness: nessuna dipendenza, gira in qualunque browser.
const tests = [];

export function test(name, fn) {
  tests.push({ name, fn });
}

function deepEqual(a, b) {
  if (Object.is(a, b)) return true;
  if (typeof a !== 'object' || typeof b !== 'object' || a === null || b === null) return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  const keysA = Object.keys(a);
  const keysB = Object.keys(b);
  if (keysA.length !== keysB.length) return false;
  return keysA.every((key) => Object.prototype.hasOwnProperty.call(b, key) && deepEqual(a[key], b[key]));
}

export function assert(condition, message = 'condizione falsa') {
  if (!condition) throw new Error(message);
}

export function assertEqual(actual, expected, message = '') {
  if (!deepEqual(actual, expected)) {
    throw new Error(`${message} atteso ${JSON.stringify(expected)}, ottenuto ${JSON.stringify(actual)}`);
  }
}

export async function run() {
  const list = document.getElementById('results');
  let failed = 0;
  for (const { name, fn } of tests) {
    const item = document.createElement('li');
    try {
      await fn();
      item.className = 'pass';
      item.textContent = `✓ ${name}`;
    } catch (error) {
      failed += 1;
      item.className = 'fail';
      item.textContent = `✗ ${name}: ${error.message}`;
      console.error(name, error);
    }
    list.appendChild(item);
  }
  const status = failed ? 'FAIL' : 'PASS';
  const summary = document.getElementById('summary');
  summary.textContent = `${status}: ${tests.length - failed}/${tests.length} test passati`;
  summary.dataset.summary = `${status} ${tests.length - failed}/${tests.length}`;
  document.title = summary.textContent;
}
