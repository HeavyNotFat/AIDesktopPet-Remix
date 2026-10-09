'use strict';

// JavaScript 插件运行时：stdin 收 JSON 行，stdout 回 JSON 行，同步读写。

const fs = require('fs');
const path = require('path');

let buffer = Buffer.alloc(0);
let apiSeq = 0;
let plugin = null;
let api = null;

function writeLine(obj) {
  fs.writeSync(1, JSON.stringify(obj) + '\n');
}

function readLine() {
  for (;;) {
    const index = buffer.indexOf(10);
    if (index >= 0) {
      const line = buffer.slice(0, index).toString('utf8');
      buffer = buffer.slice(index + 1);
      return line;
    }
    const chunk = Buffer.alloc(1 << 16);
    let read = 0;
    try {
      read = fs.readSync(0, chunk, 0, chunk.length, null);
    } catch (err) {
      if (err.code === 'EAGAIN') continue;
      if (err.code === 'EOF') return null;
      throw err;
    }
    if (read === 0) return null;
    buffer = Buffer.concat([buffer, chunk.slice(0, read)]);
  }
}

function callApi(method, ...args) {
  const id = ++apiSeq;
  writeLine({type: 'api', id: id, method: method, args: args});
  for (;;) {
    const line = readLine();
    if (line === null) throw new Error('宿主已断开');
    if (!line.trim()) continue;
    const message = JSON.parse(line);
    if (message.type !== 'api_result' || message.id !== id) continue;
    if (message.error) throw new Error(message.error);
    return message.result;
  }
}

function buildApi() {
  return {
    id: plugin.id,
    name: plugin.name || plugin.id,
    version: plugin.version || '0.1.0',
    path: plugin.path,

    log: (...args) => callApi('log', args.map(String).join(' ')),
    notify: (text, level, timeout) => callApi('notify', String(text), level || 'info', timeout || 2600),

    getSetting: (key, fallback) => callApi('get_setting', key, fallback === undefined ? null : fallback),
    setSetting: (key, value) => callApi('set_setting', key, value),
    settings: () => callApi('settings'),

    storageGet: (key, fallback) => callApi('storage_get', key, fallback === undefined ? null : fallback),
    storageSet: (key, value) => callApi('storage_set', key, value),
    storageAll: () => callApi('storage_all'),

    addMenuItem: (label, action) => callApi('add_menu_item', String(label), action || null),
    addSettingsPage: (title, form, key, order) => callApi(
      'add_settings_page', String(title), form || null, null, key || null,
      order === undefined ? 100 : order
    ),
    removeSettingsPage: key => callApi('remove_settings_page', key === undefined ? null : key),
    settingsPages: () => callApi('settings_pages'),
    refreshSettingsPage: key => callApi('refresh_settings_page', key === undefined ? null : key),
    registerCommand: (name, help) => callApi('register_command', String(name), help || ''),
    appendSystemPrompt: text => callApi('append_system_prompt', String(text)),
    clearSystemPrompt: () => callApi('clear_system_prompt'),
    sendToChat: (text, role) => callApi('send_to_chat', String(text), role || 'assistant'),

    playMotion: (name, index) => callApi('play_motion', String(name), index || 0),
    playExpression: name => callApi('play_expression', String(name)),
    motions: () => callApi('motions'),
    expressions: () => callApi('expressions')
  };
}

function invoke(hook, payload) {
  if (!plugin || typeof plugin[hook] !== 'function') return null;
  return plugin[hook](api, payload === undefined ? null : payload);
}

function main() {
  const entry = process.argv[2];
  if (!entry) {
    writeLine({type: 'fatal', error: '缺少入口文件参数'});
    return 1;
  }

  try {
    plugin = require(path.resolve(entry));
  } catch (err) {
    writeLine({type: 'fatal', error: '加载失败：' + (err && err.message ? err.message : String(err))});
    return 1;
  }

  if (!plugin || (typeof plugin !== 'object' && typeof plugin !== 'function')) {
    writeLine({type: 'fatal', error: '插件必须用 module.exports 导出对象'});
    return 1;
  }

  const meta = plugin.manifest || {};
  api = buildApi();
  writeLine({type: 'ready', id: meta.id || null});

  for (;;) {
    let line;
    try {
      line = readLine();
    } catch (err) {
      writeLine({type: 'fatal', error: '读取失败：' + String(err && err.message)});
      return 1;
    }
    if (line === null) break;
    if (!line.trim()) continue;

    let message;
    try {
      message = JSON.parse(line);
    } catch (err) {
      continue;
    }

    if (message.type === 'exit') break;
    if (message.type !== 'hook') continue;

    let value = null;
    let error = null;
    try {
      value = invoke(message.hook, message.payload);
    } catch (err) {
      error = (err && err.stack) ? String(err.stack) : String(err);
    }
    writeLine({type: 'result', id: message.id, value: value === undefined ? null : value, error: error});
  }

  return 0;
}

process.exitCode = main();
