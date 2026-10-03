(function () {
  const { STORE_KEY, MODEL_KEY } = QW.config;

  function readChats() {
    try {
      const v = JSON.parse(localStorage.getItem(STORE_KEY));
      return Array.isArray(v) ? v : [];
    } catch (e) {
      return [];
    }
  }

  const state = {
    chats: readChats(),
    currentId: null,
    pending: null,
    model: null,
    models: []
  };

  function saveChats() {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(state.chats));
    } catch (e) {}
  }

  function loadSavedModel() {
    try {
      return localStorage.getItem(MODEL_KEY);
    } catch (e) {
      return null;
    }
  }

  function saveModel() {
    try {
      localStorage.setItem(MODEL_KEY, state.model);
    } catch (e) {}
  }

  function uid() {
    return Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
  }

  function currentChat() {
    return state.chats.find(c => c.id === state.currentId) || null;
  }

  function createChat(question) {
    const chat = {
      id: uid(),
      title: question.length > 24 ? question.slice(0, 24) + '…' : question,
      messages: [],
      updated: Date.now()
    };
    state.chats.unshift(chat);
    state.currentId = chat.id;
    return chat;
  }

  function removeChat(id) {
    state.chats = state.chats.filter(c => c.id !== id);
    if (state.currentId === id) state.currentId = null;
    saveChats();
  }

  QW.store = { state, saveChats, loadSavedModel, saveModel, currentChat, createChat, removeChat };
})();
