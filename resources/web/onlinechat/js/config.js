window.QW = window.QW || {};

QW.config = {
  API_BASE: 'http://127.0.0.1:52493/api',
  DEFAULT_NAME: '',
  MOBILE_QUERY: '(max-width:760px)',
  // localStorage 键：store.js 依赖它们，缺了会退化成都读写 "undefined" 这一个键。
  STORE_KEY: 'adp-remix.onlinechat.chats',
  MODEL_KEY: 'adp-remix.onlinechat.model'
};
