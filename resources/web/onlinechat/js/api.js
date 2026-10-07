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
      const model = { label: String(label), value: String(value) };
      if (typeof item.vision === 'boolean') model.vision = item.vision;
      return model;
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

  async function chat(model, question, sessionId, signal, attachments) {
    const raw = await post('/chat', {
      model, question, session_id: sessionId || null, attachments: attachments || []
    }, signal);
    const data = parse(raw);
    if (typeof data === 'string') return data.trim() || '（空响应）';
    return pick(data, ANSWER_KEYS) || JSON.stringify(data, null, 2);
  }

  // 流式：后台按 SSE 推 delta，这里边收边回调；返回完整回答。
  async function chatStream(model, question, sessionId, signal, onDelta, attachments) {
    const res = await fetch(API_BASE + '/chat/stream', {
      method: 'POST',
      signal,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model, question, session_id: sessionId || null, attachments: attachments || []
      })
    });

    if (!res.ok) {
      const raw = await res.text();
      const detail = pick(parse(raw), ['detail', 'message', 'error']) || raw;
      throw new Error('HTTP ' + res.status + (detail ? '：' + String(detail).slice(0, 200) : ''));
    }
    if (!res.body || !res.body.getReader) throw new Error('当前浏览器不支持流式读取');

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let answer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let split;
      while ((split = buffer.indexOf('\n\n')) >= 0) {
        const frame = buffer.slice(0, split);
        buffer = buffer.slice(split + 2);

        const line = frame.split('\n').find(part => part.startsWith('data:'));
        if (!line) continue;

        let payload;
        try {
          payload = JSON.parse(line.slice(5).trim());
        } catch (e) {
          continue;
        }

        if (payload.type === 'delta' && payload.text) {
          answer += payload.text;
          if (onDelta) onDelta(payload.text);
        } else if (payload.type === 'error') {
          const error = new Error(payload.detail || '生成失败');
          error.partial = answer;
          error.retry = !!payload.retry;
          throw error;
        }
      }
    }

    return answer;
  }

  // 删除对话时让后台丢掉对应的 LLM 实例与上下文记忆。
  async function resetSession(sessionId) {
    if (!sessionId) return null;
    try {
      return await post('/reset', { session_id: sessionId });
    } catch (e) {
      return null;
    }
  }

  // 命中本地缓存时，把这一轮补记进服务端记忆（不调用模型）。
  async function recall(model, question, answer, sessionId) {
    try {
      return await post('/chat/recall', {
        model, question, answer, session_id: sessionId || null
      });
    } catch (e) {
      return null;
    }
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

  QW.api = { chat, chatStream, recall, resetSession, getModelName, getModelList };
})();