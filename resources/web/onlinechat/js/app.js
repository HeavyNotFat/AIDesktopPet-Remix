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
    refresh();
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

    const controller = new AbortController();
    state.pending = { chatId: chat.id, controller };
    refresh();

    try {
      const answer = await QW.api.chat(model, question, controller.signal);
      chat.messages.push({ role: 'assistant', content: answer });
    } catch (e) {
      if (e.name !== 'AbortError') {
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