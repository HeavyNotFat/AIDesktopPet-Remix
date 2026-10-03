(function () {
  const { API_BASE } = QW.config;

  const ANSWER_KEYS = ['answer', 'response', 'reply', 'content', 'text', 'message', 'result', 'output', 'data'];
  const NAME_KEYS = ['name', 'model_name', 'modelname', 'modelName', 'model', 'data', 'result', 'text', 'content'];
  const LIST_KEYS = ['models', 'model_list', 'modellist', 'modelList', 'list', 'data', 'result', 'items'];

  function parse(raw) {
    try {
      return JSON.parse(raw);
    } catch (e) {
      return raw;
    }
  }

  function pick(v, keys) {
    if (typeof v === 'string') return v;
    if (Array.isArray(v)) {
      for (const x of v) {
        const r = pick(x, keys);
        if (r) return r;
      }
      return '';
    }
    if (v && typeof v === 'object') {
      if (v.choices) {
        const r = pick(v.choices, keys);
        if (r) return r;
      }
      for (const k of keys) {
        if (k in v) {
          const r = pick(v[k], keys);
          if (r) return r;
        }
      }
    }
    return '';
  }

  function findList(v) {
    if (Array.isArray(v)) return v;
    if (v && typeof v === 'object') {
      for (const k of LIST_KEYS) {
        if (k in v) {
          const r = findList(v[k]);
          if (r) return r;
        }
      }
    }
    return null;
  }

  function normalizeModel(item) {
    if (item && typeof item === 'object') {
      const value = item.value ?? item.id ?? item.model ?? item.model_name ?? item.name;
      if (value == null) return null;
      const label = item.label ?? item.name ?? item.title ?? item.model_name ?? item.model ?? value;
      return { label: String(label), value: String(value) };
    }
    if (item == null || item === '') return null;
    return { label: String(item), value: String(item) };
  }

  async function post(path, body, signal) {
    const init = { method: 'POST', signal };
    if (body) {
      init.headers = { 'Content-Type': 'application/json' };
      init.body = JSON.stringify(body);
    }
    const res = await fetch(API_BASE + path, init);
    const raw = await res.text();
    if (!res.ok) {
      const data = parse(raw);
      const detail = pick(data, ['detail', 'message', 'error']) || raw;
      throw new Error('HTTP ' + res.status + (detail ? '：' + detail.slice(0, 200) : ''));
    }
    return raw;
  }

  async function chat(model, question, signal) {
    const raw = await post('/chat', { model, question }, signal);
    const data = parse(raw);
    if (typeof data === 'string') return data.trim() || '（空响应）';
    return pick(data, ANSWER_KEYS) || JSON.stringify(data, null, 2);
  }

  async function getModelName() {
    const raw = await post('/getmodelname');
    return String(pick(parse(raw), NAME_KEYS)).trim();
  }

  async function getModelList() {
    const raw = await post('/getmodellist');
    const data = parse(raw);
    const list = typeof data === 'string'
      ? data.split(/[\n,，]+/).map(s => s.trim()).filter(Boolean)
      : findList(data);
    if (!list) throw new Error('模型列表格式无法识别');
    const models = list.map(normalizeModel).filter(Boolean);
    if (!models.length) throw new Error('模型列表为空');
    return models;
  }

  QW.api = { chat, getModelName, getModelList };
})();