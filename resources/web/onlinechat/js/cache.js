(function () {
  const { CACHE_KEY, CACHE_TTL, CACHE_MAX } = QW.config;

  let memory = null;

  function read() {
    if (memory) return memory;
    try {
      const raw = JSON.parse(localStorage.getItem(CACHE_KEY));
      memory = raw && typeof raw === 'object' ? raw : {};
    } catch (e) {
      memory = {};
    }
    return memory;
  }

  function write() {
    const store = read();
    const keys = Object.keys(store);

    if (keys.length > CACHE_MAX) {
      keys
        .sort((a, b) => (store[a].used || 0) - (store[b].used || 0))
        .slice(0, keys.length - CACHE_MAX)
        .forEach(key => delete store[key]);
    }

    try {
      localStorage.setItem(CACHE_KEY, JSON.stringify(store));
    } catch (e) {
      memory = {};
    }
  }

  function keyOf(model, question) {
    return model + '\u0000' + question;
  }

  function expired(entry) {
    return CACHE_TTL > 0 && Date.now() - entry.ts > CACHE_TTL * 1000;
  }

  function get(model, question) {
    const store = read();
    const key = keyOf(model, question);
    const entry = store[key];
    if (!entry) return null;

    if (expired(entry)) {
      delete store[key];
      write();
      return null;
    }

    entry.used = Date.now();
    entry.hits = (entry.hits || 0) + 1;
    write();
    return entry;
  }

  function put(model, question, answer) {
    if (!answer) return null;

    const store = read();
    const key = keyOf(model, question);
    const now = Date.now();
    const previous = store[key];

    store[key] = {
      answer: answer,
      model: model,
      ts: previous ? previous.ts : now,
      used: now,
      hits: previous ? previous.hits || 0 : 0
    };
    write();
    return store[key];
  }

  function drop(model, question) {
    const store = read();
    const key = keyOf(model, question);
    if (!(key in store)) return false;
    delete store[key];
    write();
    return true;
  }

  function clear() {
    const store = read();
    const removed = Object.keys(store).length;
    memory = {};
    try {
      localStorage.removeItem(CACHE_KEY);
    } catch (e) {}
    return removed;
  }

  function stats() {
    const store = read();
    return {
      entries: Object.keys(store).length,
      bytes: JSON.stringify(store).length,
      max: CACHE_MAX,
      ttl: CACHE_TTL
    };
  }

  QW.cache = { get, put, drop, clear, stats };
})();
