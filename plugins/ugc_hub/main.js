'use strict';

// UGC 素材站插件：所有操作都在「设置 → 插件 → UGC 素材站」这一页里完成，不碰右键菜单。
// 页面只有一条导航：里面用 section 分区（2–3 列栅格）+ map 状态映射排布，数据一变就重建。

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const ROOT = path.resolve(__dirname, '..', '..');
const DATA_DIR = path.join(ROOT, 'plugins', '.data');
const STATUS_FILE = path.join(DATA_DIR, 'ugc_hub-task.json');
const DEFAULT_SERVER = 'https://adp.cqjszx.cn';
const PAGE_KEY = 'ugc';
const PAGE_TITLE = 'UGC 素材站';

const MAX_LINES = 5;
const KINDS = [
    ['', '全部类型'],
    ['live2d', 'Live2D 模型'],
    ['static', '静态形象'],
    ['js', 'JS 插件'],
    ['zip', '压缩包插件'],
    ['other', '其它']
];
const LICENSES = ['CC0', 'CC-BY', 'CC-BY-SA', 'MIT', 'UNKNOWN'];

let host = null;

function ensureDataDir() {
    if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });
}

function readJobStatus() {
    if (!fs.existsSync(STATUS_FILE)) return null;
    try {
        return JSON.parse(fs.readFileSync(STATUS_FILE, 'utf8'));
    } catch (err) {
        return null;
    }
}

function writeJobStatus(patch) {
    ensureDataDir();
    const current = readJobStatus() || {};
    fs.writeFileSync(STATUS_FILE, JSON.stringify(Object.assign(current, patch)), 'utf8');
}

function stored(api, key, fallback) {
    const value = api.storageGet(key, fallback);
    return value === null || value === undefined ? fallback : value;
}

function setting(api, key, fallback) {
    const value = api.getSetting(key, fallback);
    return value === null || value === undefined || value === '' ? fallback : value;
}

function textSetting(api, key, fallback) {
    return String(setting(api, key, fallback) || '').trim();
}

function serverUrl(api) {
    return textSetting(api, 'server_url', DEFAULT_SERVER);
}

function token(api) {
    return String(stored(api, 'token', '') || '');
}

function items(api) {
    const list = stored(api, 'items', []);
    return Array.isArray(list) ? list : [];
}

function percent(status) {
    if (!status || !status.progress || !status.progress.total) return '';
    return Math.round((status.progress.done / status.progress.total) * 100) + '%';
}

function statusText(status) {
    if (!status) return '还没跑过任务';
    if (status.state === 'running') return (status.message || '进行中') + (percent(status) ? '（' + percent(status) + '）' : '');
    if (status.state === 'failed') return '失败 — ' + (status.message || '原因不明');
    return status.message || '已完成';
}

// 任务完成后把结果落进插件存储：列表、登录 token、上次上传提示
function syncStatus(api) {
    const status = readJobStatus();
    if (!status || status.state === 'running') return status;

    const consumed = String(stored(api, 'consumed', '') || '');
    const fingerprint = String(status.task_id || '') + ':' + String(status.updated_at || '');
    if (consumed === fingerprint) return status;

    const result = status.result || {};
    if (status.action === 'list' && status.state === 'done') {
        api.storageSet('items', Array.isArray(result.items) ? result.items : []);
        api.storageSet('items_total', Number(result.total) || 0);
        api.storageSet('items_at', Math.floor(Date.now() / 1000));
    }
    if ((status.action === 'login' || status.action === 'register') && status.state === 'done') {
        api.storageSet('token', String(result.token || ''));
        api.storageSet('username', String(result.username || ''));
    }
    if (status.action === 'logout' && status.state === 'done') {
        api.storageSet('token', '');
        api.storageSet('username', '');
    }
    if (status.action === 'upload') {
        api.storageSet('last_upload', status.state === 'done' ? status.message : '上传失败：' + (status.message || ''));
    }
    api.storageSet('consumed', fingerprint);
    return status;
}

function humanSize(size) {
    const value = Number(size) || 0;
    if (value >= 1048576) return (value / 1048576).toFixed(1) + ' MB';
    return Math.max(1, Math.round(value / 1024)) + ' KB';
}

function itemLabel(item) {
    return '#' + item.id + ' ' + (item.name || '未命名')
        + '（' + (item.kind || 'other') + '，' + humanSize(item.size) + '，下载 ' + (item.downloads || 0) + '）';
}

function previewLines(api) {
    const list = items(api);
    if (!list.length) return null;
    const lines = list.slice(0, MAX_LINES).map(function (item, index) {
        return (index + 1) + '. ' + itemLabel(item);
    });
    if (list.length > MAX_LINES) {
        lines.push('… 还有 ' + (list.length - MAX_LINES) + ' 条在下面的下拉框里');
    }
    return lines;
}

function pickOptions(api) {
    const list = items(api);
    if (!list.length) return [['', '（还没拉过列表，点「搜索 / 刷新」）']];
    return list.map(function (item) {
        return [String(item.id), itemLabel(item)];
    });
}

function whenText(api) {
    const at = Number(stored(api, 'items_at', 0)) || 0;
    return at ? new Date(at * 1000).toLocaleString() : null;
}

// 单页 + 分区：状态在最上面，下面是素材站 / 账号 / 查找 / 下载 / 上传 / 维护
function form(api, status) {
    const list = items(api);
    const uploadMessage = String(stored(api, 'last_upload', '') || '');

    return [
        { type: 'map', title: '状态', items: {
            '素材站': serverUrl(api),
            '账号': stored(api, 'username', '') || null,
            '本次任务': statusText(status),
            '素材列表': list.length ? list.length + ' 条（共 ' + (stored(api, 'items_total', list.length)) + ' 条），' + (whenText(api) || '刚刚刷新') : null,
            '上传结果': uploadMessage || null,
            '安装目录': textSetting(api, 'download_dir', 'resources/character'),
            '预览': previewLines(api)
        } },

        { type: 'section', title: '素材站', columns: 2, rows: [
            { type: 'text', key: 'server_url', label: '素材站地址', placeholder: DEFAULT_SERVER, span: 2 },
            { type: 'button', action: 'ping', text: '测试连接' },
            { type: 'button', action: 'refresh', text: '刷新素材列表' },
            { type: 'button', action: 'status', text: '查看当前进度' },
            { type: 'button', action: 'logout', text: '退出登录' }
        ] },

        { type: 'section', title: '账号', columns: 2, hint: '空服务器上第一个注册的账号会成为管理员', rows: [
            { type: 'text', key: 'username', label: '用户名' },
            { type: 'password', key: 'password', label: '密码', hint: '明文存在本机 configure.json，登录成功后插件只留 token' },
            { type: 'button', action: 'login', text: '登录' },
            { type: 'button', action: 'register', text: '注册新账号' },
            { type: 'button', action: 'clear_password', text: '清空密码框', span: 2 }
        ] },

        { type: 'section', title: '查找素材', columns: 3, rows: [
            { type: 'text', key: 'keyword', label: '关键词', placeholder: '留空就是全部', span: 2 },
            { type: 'select', key: 'browse_kind', label: '类型', options: KINDS },
            { type: 'number', key: 'page_size', label: '每页条数', min: 5, max: 50 },
            { type: 'select', key: 'sort', label: '排序', options: [['new', '最新上传'], ['hot', '下载最多']] },
            { type: 'button', action: 'search', text: '搜索 / 刷新' }
        ] },

        { type: 'section', title: '下载', columns: 2, hint: '多线程分片 + sha256 校验，解包到安装目录下的同名文件夹', rows: [
            { type: 'select', key: 'pick', label: '选择素材', options: pickOptions(api), span: 2 },
            { type: 'text', key: 'download_dir', label: '安装目录', hint: '相对仓库根目录', span: 2 },
            { type: 'text', key: 'install_name', label: '安装后的名字', placeholder: '留空就用素材名' },
            { type: 'switch', key: 'overwrite', label: '覆盖同名目录' },
            { type: 'number', key: 'threads', label: '线程数', min: 1, max: 8 },
            { type: 'number', key: 'timeout_seconds', label: '超时（秒）', min: 5, max: 300 },
            { type: 'switch', key: 'verify_sha256', label: '校验 SHA-256' },
            { type: 'switch', key: 'unzip_after_download', label: '下载后解包' },
            { type: 'switch', key: 'keep_zip', label: '保留压缩包' },
            { type: 'switch', key: 'notify_when_done', label: '完成时提示' },
            { type: 'button', action: 'download', text: '下载选中并安装', span: 2 }
        ] },

        { type: 'section', title: '上传', columns: 2, hint: '同一个文件重复上传不会占两份空间', rows: [
            { type: 'text', key: 'upload_path', label: '文件完整路径', placeholder: 'D:\\模型\\hiyori.zip', span: 2 },
            { type: 'text', key: 'upload_name', label: '显示名', placeholder: '留空就用文件名' },
            { type: 'select', key: 'upload_kind', label: '类型', options: [['auto', '自动判断'], ['live2d', 'Live2D 模型'], ['static', '静态形象'], ['js', 'JS 插件'], ['other', '其它']] },
            { type: 'select', key: 'upload_license', label: '授权', options: LICENSES },
            { type: 'text', key: 'upload_tags', label: '标签（逗号分隔）' },
            { type: 'text', key: 'upload_description', label: '说明', span: 2 },
            { type: 'button', action: 'upload', text: '开始上传', span: 2 }
        ] },

        { type: 'section', title: '维护', columns: 3, rows: [
            { type: 'button', action: 'clear_items', text: '清空本地列表缓存' },
            { type: 'button', action: 'clear_status', text: '清空任务状态' },
            { type: 'button', action: 'open_dir', text: '查看安装目录' },
            { type: 'hint', text: '任务都在后台跑：点「查看当前进度」刷新本页，跑完也会自动弹提示。node ' + process.version, span: 3 }
        ] }
    ];
}

// 会派活的按钮：点了就要重建页面（状态映射、列表可能都变了）
const JOB_ACTIONS = ['ping', 'refresh', 'search', 'status', 'logout', 'login', 'register', 'download', 'upload',
    'clear_items', 'clear_status', 'open_dir'];
// 这些设置项的当前值显示在「状态」映射里，改了要重画；其余输入框自己就显示着值，重画反而会抢焦点
const MIRRORED_KEYS = ['server_url', 'download_dir', 'threads', 'timeout_seconds', 'verify_sha256',
    'unzip_after_download', 'keep_zip', 'notify_when_done', 'page_size', 'sort', 'browse_kind'];

function needsRender(api, ctx) {
    const action = String(ctx.action || '');
    if (JOB_ACTIONS.indexOf(action) >= 0) return true;
    if (MIRRORED_KEYS.indexOf(String(ctx.key || '')) >= 0) return true;
    const status = readJobStatus();
    return !!status && String(stored(api, 'consumed', '') || '') !== String(status.task_id || '') + ':' + String(status.updated_at || '');
}

function render(api) {
    const status = syncStatus(api);
    api.addSettingsPage(PAGE_TITLE, form(api, status), PAGE_KEY, 10);
}

// 派活：写作业文件 + 起独立进程，页面立刻可用（宿主 hook 不能被网络卡住）
function startJob(api, action, payload) {
    if (!serverUrl(api)) {
        return '先填「素材站地址」';
    }
    if (['upload', 'logout'].indexOf(action) >= 0 && !token(api)) {
        return '先在「账号」分区登录';
    }
    ensureDataDir();
    const taskId = Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
    const jobFile = path.join(DATA_DIR, 'ugc_hub-job-' + taskId + '.json');
    fs.writeFileSync(jobFile, JSON.stringify(Object.assign({
        action: action,
        task_id: taskId,
        server_url: serverUrl(api),
        token: token(api),
        timeout_seconds: Number(setting(api, 'timeout_seconds', 30)) || 30,
        status_file: STATUS_FILE
    }, payload || {})), 'utf8');
    writeJobStatus({ action: action, task_id: taskId, state: 'running', message: '已开始', progress: { done: 0, total: 0 }, result: null });

    const child = spawn(process.execPath, [path.join(__dirname, 'ugc-worker.js'), jobFile], {
        detached: true,
        stdio: 'ignore',
        windowsHide: true
    });
    child.unref();
    return null;
}

function installDir(api, name) {
    const base = textSetting(api, 'download_dir', 'resources/character');
    const absolute = path.isAbsolute(base) ? base : path.join(ROOT, base);
    return { base: absolute, target: path.join(absolute, name) };
}

function safeName(raw) {
    return String(raw || '').replace(/[\\/:*?"<>|]/g, '_').trim();
}

function selectedItem(api) {
    const id = String(setting(api, 'pick', '') || '');
    const found = items(api).filter(function (item) { return String(item.id) === id; })[0];
    return { id: id, item: found || null };
}

function handle(api, action) {
    host = api;
    switch (action) {
        case 'ping':
            return startJob(api, 'ping') || '正在测试连接…';
        case 'refresh':
        case 'search': {
            const failure = startJob(api, 'list', {
                kind: String(setting(api, 'browse_kind', '') || ''),
                query: textSetting(api, 'keyword', ''),
                sort: String(setting(api, 'sort', 'new') || 'new'),
                page_size: Number(setting(api, 'page_size', 30)) || 30
            });
            return failure || '正在拉取素材列表…';
        }
        case 'status':
            return '任务：' + statusText(syncStatus(api));
        case 'logout': {
            api.storageSet('token', '');
            api.storageSet('username', '');
            const failure = startJob(api, 'logout');
            return failure ? '已清掉本机凭证（服务器那份下次联网再撤）' : '正在退出登录…';
        }
        case 'login':
        case 'register': {
            const username = textSetting(api, 'username', '');
            const password = String(api.getSetting('password', '') || '');
            if (!username || !password) {
                return '用户名和密码都要填';
            }
            return startJob(api, action, { username: username, password: password })
                || (action === 'login' ? '正在登录…' : '正在注册…');
        }
        case 'clear_password':
            api.setSetting('password', '');
            return '密码框已清空';
        case 'download': {
            const picked = selectedItem(api);
            if (!picked.id) {
                return '先在「下载」分区选一个素材';
            }
            const rawName = textSetting(api, 'install_name', '') || (picked.item && picked.item.name) || ('ugc-' + picked.id);
            const name = safeName(rawName) || ('ugc-' + picked.id);
            const dir = installDir(api, name);
            if (fs.existsSync(dir.target) && setting(api, 'overwrite', true) === false) {
                return '目录已存在（' + path.relative(ROOT, dir.target) + '）：要覆盖就把「覆盖同名目录」打开';
            }
            const unzip = setting(api, 'unzip_after_download', true) !== false;
            return startJob(api, 'download', {
                item_id: picked.id,
                dest: path.join(dir.base, name + '.zip'),
                unzip: unzip,
                keep_zip: setting(api, 'keep_zip', false) === true,
                unzip_dir: dir.target,
                threads: Number(setting(api, 'threads', 4)) || 4,
                verify_sha256: setting(api, 'verify_sha256', true) !== false
            }) || ('开始下载 #' + picked.id + ' → ' + path.relative(ROOT, unzip ? dir.target : path.join(dir.base, name + '.zip')));
        }
        case 'upload': {
            const raw = textSetting(api, 'upload_path', '');
            if (!raw) {
                return '先填要上传的文件完整路径';
            }
            const file = path.isAbsolute(raw) ? raw : path.join(ROOT, raw);
            if (!fs.existsSync(file) || !fs.statSync(file).isFile()) {
                return '找不到文件：' + file;
            }
            const chosen = String(setting(api, 'upload_kind', 'auto') || 'auto');
            const extension = path.extname(file).toLowerCase().replace('.', '');
            const kind = chosen === 'auto'
                ? (['js', 'mjs'].indexOf(extension) >= 0 ? 'js' : 'other')
                : chosen;
            return startJob(api, 'upload', {
                file: file,
                name: textSetting(api, 'upload_name', '') || path.basename(file),
                kind: kind,
                description: textSetting(api, 'upload_description', '') || '来自桌宠上传',
                tags: textSetting(api, 'upload_tags', ''),
                license: String(setting(api, 'upload_license', 'UNKNOWN') || 'UNKNOWN')
            }) || ('开始上传 ' + path.basename(file));
        }
        case 'clear_items':
            api.storageSet('items', []);
            api.storageSet('items_total', 0);
            api.storageSet('items_at', 0);
            return '本地列表缓存已清空';
        case 'clear_status':
            api.storageSet('consumed', '');
            api.storageSet('last_upload', '');
            if (fs.existsSync(STATUS_FILE)) fs.unlinkSync(STATUS_FILE);
            return '任务状态已清空';
        case 'open_dir': {
            const dir = installDir(api, '.');
            const target = fs.existsSync(dir.base) ? dir.base : ROOT;
            return '安装目录：' + path.relative(ROOT, target);
        }
        default:
            return null;
    }
}

module.exports = {
    manifest: { id: 'ugc_hub' },

    on_load(api) {
        host = api;
        render(api);
        api.log('素材站页面已就绪：' + serverUrl(api) + '（' + statusText(syncStatus(api)) + '）');
    },

    on_unload(api) {
        host = null;
        api.log('素材站插件已卸载，后台任务继续跑完');
    },

    // 页面上任何控件动一下都会走到这里：按钮派活；改完值只在需要时重画页面
    on_settings_action(api, ctx) {
        host = api;
        const message = handle(api, String(ctx.action || ctx.key || ''));
        if (needsRender(api, ctx)) {
            render(api);
        }
        return message || null;
    },

    // 宿主事件：任务跑完了就刷新页面并提示一声
    on_event(api, ctx) {
        host = api;
        const before = String(stored(api, 'consumed', '') || '');
        const status = syncStatus(api);
        const after = String(stored(api, 'consumed', '') || '');
        if (status && after !== before) {
            render(api);
            if (setting(api, 'notify_when_done', true) !== false) {
                api.notify('素材站：' + statusText(status), status.state === 'failed' ? 'error' : 'success', 4000);
            }
        }
        return null;
    }
};
