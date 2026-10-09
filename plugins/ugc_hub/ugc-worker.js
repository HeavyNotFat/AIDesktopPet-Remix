'use strict';

// 后台任务进程：联网都在这儿跑，进度写状态文件，插件页面随时读。
// 用法：node ugc-worker.js <作业文件>；作业文件是 JSON，字段见 README。

const fs = require('fs');
const path = require('path');
const ugc = require('./ugc.js');

const jobFile = process.argv[2];
if (!jobFile || !fs.existsSync(jobFile)) {
    process.exit(2);
}

const job = JSON.parse(fs.readFileSync(jobFile, 'utf8'));
const statusFile = job.status_file;
const client = ugc.createClient({
    baseUrl: job.server_url,
    token: job.token || '',
    timeoutMs: job.timeout_seconds ? job.timeout_seconds * 1000 : 30000
});

function writeStatus(patch) {
    const current = fs.existsSync(statusFile)
        ? JSON.parse(fs.readFileSync(statusFile, 'utf8'))
        : {};
    const next = Object.assign(current, patch, {
        task_id: job.task_id || '',
        action: job.action,
        updated_at: Math.floor(Date.now() / 1000)
    });
    fs.writeFileSync(statusFile, JSON.stringify(next), 'utf8');
}

function progress(done, total) {
    writeStatus({ state: 'running', progress: { done: done, total: total || 0 } });
}

async function runPing() {
    const payload = await client.health();
    writeStatus({
        state: 'done',
        message: '连上了：' + payload.name + ' ' + payload.version,
        result: { name: payload.name, version: payload.version }
    });
}

async function runMe() {
    const payload = await client.me();
    const user = payload.user;
    writeStatus({
        state: 'done',
        message: user ? '当前账号：' + user.username : '当前未登录',
        result: { user: user || null }
    });
}

async function runAuth(kind) {
    const payload = kind === 'register'
        ? await client.register(job.username, job.password)
        : await client.login(job.username, job.password);
    const user = payload.user || {};
    writeStatus({
        state: 'done',
        message: (kind === 'register' ? '注册并登录成功：' : '登录成功：') + (user.username || job.username),
        result: { token: payload.token || '', username: user.username || job.username, role: user.role || '' }
    });
}

async function runLogout() {
    await client.logout();
    writeStatus({ state: 'done', message: '已退出登录', result: { token: '' } });
}

async function runList() {
    const payload = await client.listItems({
        kind: job.kind || '',
        q: job.query || '',
        sort: job.sort || 'new',
        page_size: job.page_size || 30
    });
    const items = Array.isArray(payload.items) ? payload.items : [];
    writeStatus({
        state: 'done',
        message: items.length
            ? '共 ' + (payload.total || items.length) + ' 条，取回 ' + items.length + ' 条'
            : '没有符合条件的素材',
        result: {
            total: payload.total || items.length,
            items: items.map(function (item) {
                return {
                    id: String(item.id),
                    name: String(item.name || ''),
                    kind: String(item.kind || ''),
                    type: String(item.type || ''),
                    size: Number(item.size) || 0,
                    downloads: Number(item.downloads) || 0,
                    author: item.author ? String(item.author.username || '') : ''
                };
            })
        }
    });
}

async function runDownload() {
    const result = await client.downloadToFile({
        itemId: job.item_id,
        dest: job.dest,
        threads: job.threads,
        verify: job.verify_sha256 !== false,
        onProgress: progress
    });
    let installed = [];
    if (job.unzip) {
        writeStatus({ state: 'running', message: '下载完成，正在解包…' });
        installed = ugc.unzipTo(job.dest, job.unzip_dir, function (done, total) {
            progress(done, total);
        });
    }
    if (!job.keep_zip && fs.existsSync(job.dest)) {
        fs.unlinkSync(job.dest);
    }
    writeStatus({
        state: 'done',
        message: '下载完成：' + ugc.formatBytes(result.bytes)
            + (installed.length ? '，解包 ' + installed.length + ' 个文件到 ' + path.basename(job.unzip_dir || '') : '')
            + (job.keep_zip ? '（压缩包保留）' : ''),
        result: {
            bytes: result.bytes,
            sha256: result.sha256,
            filename: result.filename,
            installed: installed.length,
            dir: job.unzip_dir || '',
            kept_zip: !!job.keep_zip
        }
    });
}

async function runUpload() {
    const result = await client.uploadFile({
        file: job.file,
        name: job.name,
        kind: job.kind,
        description: job.description,
        tags: job.tags,
        license: job.license,
        onProgress: progress
    });
    const id = result.item && result.item.id ? result.item.id : '';
    writeStatus({
        state: 'done',
        message: result.duplicate
            ? '这份文件之前传过了（编号 ' + id + '）'
            : '上传成功（编号 ' + id + '，' + ugc.formatBytes(result.size) + '）',
        result: { item_id: id, duplicate: result.duplicate, sha256: result.sha256, size: result.size }
    });
}

async function main() {
    try {
        switch (job.action) {
            case 'ping':
                await runPing();
                break;
            case 'me':
                await runMe();
                break;
            case 'login':
            case 'register':
                await runAuth(job.action);
                break;
            case 'logout':
                await runLogout();
                break;
            case 'list':
                await runList();
                break;
            case 'download':
                await runDownload();
                break;
            case 'upload':
                await runUpload();
                break;
            default:
                throw new ugc.UgcError('不认识的任务：' + job.action, 0, 'bad_job');
        }
    } catch (error) {
        writeStatus({
            state: 'failed',
            message: ugc.describeError(error),
            error: { status: error.status || 0, code: error.code || '' }
        });
        process.exitCode = 1;
    } finally {
        try {
            fs.unlinkSync(jobFile);
        } catch (err) {
            /* 作业文件删不掉也无所谓 */
        }
    }
}

main();
