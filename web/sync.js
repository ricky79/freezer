// Ciclo di sincronizzazione: invia la coda a blocchi, oppure chiede solo l'istantanea.
export const MAX_BATCH = 500;

export function createSyncer({
  getQueue,
  onSuccess,
  onFailure,
  fetchImpl = (...args) => fetch(...args),
  timeoutMs = 5000,
}) {
  let running = false;
  let again = false;

  async function exchange(ops) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const request = ops.length
        ? {
            url: '/api/sync',
            options: {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ ops }),
            },
          }
        : { url: '/api/inventory', options: {} };
      const response = await fetchImpl(request.url, {
        ...request.options,
        cache: 'no-store',
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      onSuccess(await response.json(), new Set(ops.map((op) => op.op_id)));
    } finally {
      clearTimeout(timer);
    }
  }

  async function syncNow() {
    if (running) {
      again = true;
      return;
    }
    running = true;
    try {
      do {
        again = false;
        const ops = getQueue().slice(0, MAX_BATCH);
        await exchange(ops);
        if (ops.length > 0 && getQueue().length > 0) again = true;
      } while (again);
    } catch (error) {
      onFailure(error);
    } finally {
      running = false;
    }
  }

  return { syncNow };
}
