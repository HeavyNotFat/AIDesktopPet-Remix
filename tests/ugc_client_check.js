'use strict';

// 素材站客户端自检：直接调 ugc.js + 走 ugc-worker.js 后台任务，两条路都过一遍。
// 用法：UGC_BASE_URL=http://127.0.0.1:8801 UGC_FIXTURE_ZIP=xxx.zip node tests/ugc_client_check.js

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn } = require('child_process');
const ugc = require(path.resolve(__dirname, '..', 'plugins', 'ugc_hub', 'ugc.js'));

const baseUrl = String(process.env.UGC_BASE_URL || '').replace(/\/+$/, '');
const fixtureZip = String(process.env.UGC_FIXTURE_ZIP || '');
const username = process.env.UGC_USER || ('js' + Date.now().toString(36).slice(-6));

let passed = 0;
let failed = 0;

function check(name, ok, detail) {
    if (ok) {
        passed += 1;
        console.log('  ok   ' + name + (detail ? ' — ' + detail : ''));
        return;
    }
    failed += 1;
    console.log('  FAIL ' + name + (detail ? ' — ' + detail : ''));
}

function waitFor(predicate, timeoutMs) {
    const deadline = Date.now() + timeoutMs;
    return new Promise((resolve) => {
        const tick = () => {
            if (predicate()) return resolve(true);
            if (Date.now() > deadline) return resolve(false);
            setTimeout(tick, 150);
        };
        tick();
    });
}

async function runWorker(job, statusFile) {
    const jobFile = statusFile.replace(/\.json$/, '-job.json');
    fs.writeFileSync(jobFile, JSON.stringify(Object.assign({ status_file: statusFile }, job)), 'utf8');
    const child = spawn(process.execPath, [path.resolve(__dirname, '..', 'plugins', 'ugc_hub', 'ugc-worker.js'), jobFile], {
        stdio: 'ignore'
    });
    const finished = await new Promise((resolve) => child.on('exit', (code) => resolve(code)));
    return { code: finished, status: JSON.parse(fs.readFileSync(statusFile, 'utf8')) };
}

async function main() {
    if (!baseUrl) {
        console.log('  skip 没给 UGC_BASE_URL');
        process.exit(0);
    }
    // 工作目录可以外部指定（沙箱/CI 里临时目录不一定可写）
    const workDir = process.env.UGC_WORK_DIR
        ? fs.mkdtempSync(path.join(process.env.UGC_WORK_DIR, 'ugc-check-'))
        : fs.mkdtempSync(path.join(os.tmpdir(), 'ugc-check-'));
    const client = ugc.createClient({ baseUrl: baseUrl, timeoutMs: 20000 });

    const health = await client.health();
    check('健康检查', health.ok === true && !!health.name, health.name + ' ' + health.version);

    const opened = await client.register(username, 'CheckPass123');
    client.token = String(opened.token || '');
    check('注册拿到 token', client.token.length > 20 && opened.user.username === username);

    const uploaded = await client.uploadFile({
        file: fixtureZip,
        name: '自检模型',
        kind: 'live2d',
        description: '来自 ugc.js 自检',
        tags: '自检',
        license: 'CC0'
    });
    const itemId = uploaded.item && uploaded.item.id;
    check('三步分片上传成功', !!itemId, 'id=' + itemId + ' sha=' + String(uploaded.sha256).slice(0, 8));
    check('服务端认出了 live2d 入口', !!(uploaded.item && uploaded.item.meta && uploaded.item.meta.entry), uploaded.item ? uploaded.item.meta.entry : '');

    const list = await client.listItems({ kind: 'live2d', page_size: 10 });
    check('列表能查到刚上传的条目', Array.isArray(list.items) && list.items.some((entry) => String(entry.id) === String(itemId)), 'total=' + list.total);

    const head = await client.headDownload(itemId);
    check('HEAD 给出大小/摘要/并发上限', head.size === fs.statSync(fixtureZip).size && head.sha256.length === 64 && head.concurrencyLimit > 0,
        'size=' + head.size + ' 并发=' + head.concurrencyLimit);

    const zipTarget = path.join(workDir, 'downloaded.zip');
    const downloaded = await client.downloadToFile({ itemId: itemId, dest: zipTarget, threads: 4, verify: true });
    check('多线程下载并校验 sha256', downloaded.bytes === head.size && downloaded.sha256 === head.sha256, 'mode=' + (head.acceptRanges ? 'range' : 'plain'));

    const unpackDir = path.join(workDir, 'unpacked');
    const written = ugc.unzipTo(zipTarget, unpackDir);
    check('解包写出文件', written.length >= 3 && fs.existsSync(path.join(unpackDir, uploaded.item.meta.entry)),
        written.length + ' 个文件');

    const range = await ugc.request(baseUrl + '/api/items/' + itemId + '/download', {
        method: 'GET',
        headers: { Range: 'bytes=0-15', Authorization: 'Bearer ' + client.token }
    });
    check('Range 请求返回 206 与 16 字节', range.status === 206 && range.body.length === 16, 'HTTP ' + range.status);

    const statusFile = path.join(workDir, 'task.json');
    const listed = await runWorker({ action: 'list', server_url: baseUrl, token: client.token, kind: 'live2d' }, statusFile);
    check('后台 worker 列素材', listed.code === 0 && listed.status.state === 'done' && listed.status.result.items.length >= 1, listed.status.message);

    const workerDir = path.join(workDir, 'from-worker');
    const workerJob = await runWorker({
        action: 'download',
        server_url: baseUrl,
        token: client.token,
        item_id: itemId,
        dest: path.join(workDir, 'worker.zip'),
        unzip: true,
        unzip_dir: workerDir,
        threads: 4,
        verify_sha256: true
    }, statusFile);
    check('后台 worker 下载并解包', workerJob.code === 0 && workerJob.status.state === 'done' && workerJob.status.result.installed >= 3, workerJob.status.message);

    const failedJob = await runWorker({ action: 'download', server_url: baseUrl, item_id: '999999' }, statusFile);
    check('后台 worker 失败也会写状态', failedJob.status.state === 'failed' && failedJob.status.message.length > 0, failedJob.status.message);

    fs.rmSync(workDir, { recursive: true, force: true });
    console.log('\n客户端自检：通过 ' + passed + ' 项，失败 ' + failed + ' 项');
    process.exit(failed === 0 ? 0 : 1);
}

main().catch((error) => {
    console.log('  FAIL 自检异常：' + ugc.describeError(error));
    console.log('\n客户端自检：通过 ' + passed + ' 项，失败 ' + (failed + 1) + ' 项');
    process.exit(1);
});
