window.QW = window.QW || {};

QW.config = {
  API_BASE: 'http://127.0.0.1:52493/api',
  DEFAULT_NAME: '',
  MOBILE_QUERY: '(max-width:760px)',
  STORE_KEY: 'adp-remix.onlinechat.chats',
  MODEL_KEY: 'adp-remix.onlinechat.model',
  CACHE_KEY: 'adp-remix.onlinechat.cache',
  // 回答本地缓存：存活秒数（0 = 不过期）与条数上限
  CACHE_TTL: 7 * 24 * 3600,
  CACHE_MAX: 200,
  // 附件：一次最多几个、单个最大多少
  MAX_ATTACHMENTS: 6,
  MAX_ATTACHMENT_BYTES: 8 * 1024 * 1024
};
