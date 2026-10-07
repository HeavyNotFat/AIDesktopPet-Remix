window.QW = window.QW || {};

QW.config = {
  API_BASE: 'http://127.0.0.1:52493/api',
  DEFAULT_NAME: '',
  MOBILE_QUERY: '(max-width:760px)',
  STORE_KEY: 'adp-remix.onlinechat.chats',
  MODEL_KEY: 'adp-remix.onlinechat.model',
  CACHE_KEY: 'adp-remix.onlinechat.cache',
  // 回答本地缓存：存活时间（秒，0 = 不过期）与条数上限
  CACHE_TTL: 7 * 24 * 3600,
  CACHE_MAX: 200
};
