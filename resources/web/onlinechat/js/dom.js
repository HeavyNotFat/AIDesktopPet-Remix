(function () {
  const $ = id => document.getElementById(id);

  QW.dom = {
    app: $('app'),
    sidebar: $('sidebar'),
    scrim: $('scrim'),
    history: $('history'),
    searchBtn: $('searchBtn'),
    searchBox: $('searchBox'),
    searchInput: $('searchInput'),
    collapseBtn: $('collapseBtn'),
    cacheBtn: $('cacheBtn'),
    expandBtn: $('expandBtn'),
    newChatBtn: $('newChatBtn'),
    hello: $('hello'),
    helloName: $('helloName'),
    stage: $('stage'),
    messages: $('messages'),
    inner: $('messagesInner'),
    input: $('input'),
    attachBtn: $('attachBtn'),
    attachInput: $('attachInput'),
    attachBar: $('attachBar'),
    modelBtn: $('modelBtn'),
    modelLabel: $('modelLabel'),
    modelMenu: $('modelMenu'),
    sendBtn: $('sendBtn')
  };
})();