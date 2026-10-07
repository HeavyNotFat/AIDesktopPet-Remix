(function () {
  const { dom } = QW;
  const { state } = QW.store;
  const { DEFAULT_NAME } = QW.config;

  function refresh() {
    QW.render.history(openChat, deleteChat);
    QW.render.messages();
    QW.render.sendButton();
  }

  function openChat(id) {
    state.currentId = id;
    refresh();
    QW.sidebar.collapseOnMobile();
    dom.input.focus();
  }

  function newChat() {
    state.currentId = null;
    refresh();
    QW.sidebar.collapseOnMobile();
    dom.input.focus();
  }

  function deleteChat(id) {
    if (state.pending && state.pending.chatId === id) state.pending.controller.abort();
    QW.store.removeChat(id);
    // 顺手释放后台该会话独占的 LLM 实例
    QW.api.resetSession(id);
    refresh();
  }

  function pushCached(chat, entry, model, question) {
    chat.messages.push({ role: 'assistant', content: entry.answer, cached: true });
    chat.updated = Date.now();
    QW.store.saveChats();
    refresh();
    // 缓存命中不调模型，但得把这一轮补进服务端记忆，否则追问会断上下文
    QW.api.recall(model, question, entry.answer, chat.id);
  }

  async function send() {
    const question = dom.input.value.trim();
    if (!question || state.pending || !state.model) return;

    const model = state.model;
    const chat = QW.store.currentChat() || QW.store.createChat(question);
    chat.messages.push({ role: 'user', content: question });
    chat.updated = Date.now();
    QW.store.saveChats();

    dom.input.value = '';
    QW.render.autosize();

    const cached = QW.cache.get(model, question);
    if (cached) {
      pushCached(chat, cached, model, question);
      return;
    }

    const controller = new AbortController();
    state.pending = { chatId: chat.id, controller, text: '', node: null };
    refresh();

    let streamed = '';
    try {
      streamed = await QW.api.chatStream(model, question, chat.id, controller.signal, chunk => {
        streamed += chunk;
        QW.render.streamChunk(chunk);
      });
      if (streamed) {
        chat.messages.push({ role: 'assistant', content: streamed });
        QW.cache.put(model, question, streamed);
      }
    } catch (e) {
      const partial = e.partial || streamed;
      if (e.name === 'AbortError') {
        // 用户点了停止：把已经收到的部分留下来，别白等一场
        if (partial) chat.messages.push({ role: 'assistant', content: partial, stopped: true });
      } else {
        if (partial) chat.messages.push({ role: 'assistant', content: partial, stopped: true });
        chat.messages.push({
          role: 'assistant',
          error: true,
          content: '请求失败：' + e.message + '\n请确认后台服务正在运行。'
        });
      }
    } finally {
      state.pending = null;
      if (state.chats.includes(chat)) {
        chat.updated = Date.now();
        QW.store.saveChats();
      }
      refresh();
    }
  }

  function clearCache() {
    const removed = QW.cache.clear();
    dom.cacheBtn.title = removed ? '已清除 ' + removed + ' 条本地缓存' : '本地缓存本来就是空的';
    dom.cacheBtn.classList.add('flash');
    setTimeout(() => dom.cacheBtn.classList.remove('flash'), 600);
  }

  async function loadGreeting() {
    try {
      const name = await QW.api.getModelName();
      QW.render.greeting(name || DEFAULT_NAME);
    } catch (e) {
      QW.render.greeting(DEFAULT_NAME);
    }
  }

  async function loadModels() {
    QW.modelPicker.showLoading();
    try {
      const models = await QW.api.getModelList();
      const saved = QW.store.loadSavedModel();
      state.models = models;
      state.model = models.some(m => m.value === saved) ? saved : models[0].value;
      QW.modelPicker.render();
    } catch (e) {
      state.models = [];
      state.model = null;
      QW.modelPicker.showError(e.message);
    }
    QW.render.sendButton();
  }

  function bind() {
    dom.input.addEventListener('input', () => {
      QW.render.autosize();
      QW.render.sendButton();
    });

    dom.input.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
        e.preventDefault();
        send();
      }
    });

    dom.sendBtn.addEventListener('click', () => {
      if (state.pending) state.pending.controller.abort();
      else send();
    });

    dom.newChatBtn.addEventListener('click', newChat);
    dom.cacheBtn.addEventListener('click', clearCache);
  }

  function init() {
    QW.sidebar.init({ onSearch: () => QW.render.history(openChat, deleteChat) });
    QW.modelPicker.init({ onRetry: loadModels, onSelect: () => QW.render.sendButton() });
    bind();
    refresh();
    loadGreeting();
    loadModels();
    dom.input.focus();
  }

  init();
})();
