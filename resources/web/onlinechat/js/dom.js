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
    expandBtn: $('expandBtn'),
    newChatBtn: $('newChatBtn'),
    hello: $('hello'),
    helloName: $('helloName'),
    stage: $('stage'),
    messages: $('messages'),
    inner: $('messagesInner'),
    input: $('input'),
    modelBtn: $('modelBtn'),
    modelLabel: $('modelLabel'),
    modelMenu: $('modelMenu'),
    sendBtn: $('sendBtn')
  };
})();