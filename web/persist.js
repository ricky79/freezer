// localStorage protetto: in navigazione privata o a memoria piena può lanciare eccezioni.
export function createPersist(storage) {
  return {
    load(key, fallback) {
      try {
        const raw = storage ? storage.getItem(key) : null;
        return raw == null ? fallback : JSON.parse(raw);
      } catch {
        return fallback;
      }
    },
    save(key, value) {
      try {
        if (!storage) return false;
        storage.setItem(key, JSON.stringify(value));
        return true;
      } catch {
        return false;
      }
    },
  };
}

function browserStorage() {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export const persist = createPersist(browserStorage());
