// Web Storage that never throws. Private browsing, blocked site data or a
// full quota make window.localStorage / sessionStorage (even the property
// access itself) throw; callers get null / false instead and keep working
// with in-page state only (C-10).

function probe(kind) {
  try {
    const storage = window[kind];
    if (!storage) return null;
    const key = '__fta_storage_probe__';
    storage.setItem(key, '1');
    storage.removeItem(key);
    return storage;
  } catch {
    return null;
  }
}

export function createSafeStorage(kind) {
  let resolved = false;
  let storage = null;
  const get = () => {
    if (!resolved) {
      storage = probe(kind);
      resolved = true;
    }
    return storage;
  };
  return {
    get available() {
      return get() !== null;
    },
    getItem(key) {
      try {
        const s = get();
        return s ? s.getItem(key) : null;
      } catch {
        return null;
      }
    },
    setItem(key, value) {
      try {
        const s = get();
        if (!s) return false;
        s.setItem(key, String(value));
        return true;
      } catch {
        return false;
      }
    },
    removeItem(key) {
      try {
        const s = get();
        if (!s) return false;
        s.removeItem(key);
        return true;
      } catch {
        return false;
      }
    },
    getJSON(key, fallback = null) {
      const raw = this.getItem(key);
      if (raw === null) return fallback;
      try {
        return JSON.parse(raw);
      } catch {
        return fallback;
      }
    },
    setJSON(key, value) {
      try {
        return this.setItem(key, JSON.stringify(value));
      } catch {
        return false;
      }
    },
  };
}

export const sessionStore = createSafeStorage('sessionStorage');
export const localStore = createSafeStorage('localStorage');
