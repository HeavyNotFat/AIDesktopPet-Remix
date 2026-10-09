'use strict';

// 用真实桌面插件客户端（client.js）跑一遍兼容层：健康检查 → 注册 → 上传 → 列表 → 下载校验 → 删除。
// 用法：node tests/compat/client-e2e.js
// 环境变量：UGC_BASE_URL、UGC_CLIENT_PATH、UGC_FIXTURE_ZIP、UGC_USER、UGC_PASS

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const baseUrl = String(process.env.UGC_BASE_URL || 'http://127.0.0.1:8801').replace(/\/+$/, '');
const clientPath = process.env.UGC_CLIENT_PATH || '';
const fixtureZip = process.env.UGC_FIXTURE_ZIP || '';
const username = process.env.UGC_USER || ('client' + Date.now().toString().slice(-6));
const password = process.env.UGC_PASS || 'ClientPass123';

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

function sha256FileSync(file) {
    return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
}

async function main() {
    if (!clientPath || !fs.existsSync(clientPath)) {
        console.log('  skip 没找到桌面客户端 client.js（UGC_CLIENT_PATH=' + clientPath + '）');
        process.exit(0);
    }
    const {UgcClient} = require(path.resolve(clientPath));
    const client = new UgcClient({baseUrl: baseUrl, timeoutMs: 30000, log: () => {}});

    const health = await client.health();
    check('health 返回 ok/name/version/limits', health.ok === true && !!health.name && !!health.limits,
        health.name + ' ' + health.version);

    const anonymous = await client.me();
    check('匿名 me：user=null 且回显额度', anonymous.user === null && anonymous.anonymous === true);

    const registered = await client.register(username, password);
    check('注册返回 token 与用户', typeof registered.token === 'string' && registered.token.length > 20
        && registered.user && registered.user.username === username);
    client.setToken(registered.token);

    const mine = await client.me();
    check('带 token 的 me 认得出用户', mine.user && mine.user.username === username && mine.anonymous === false);
    const concurrency = Number(mine.limits && (mine.limits.concurrency
        || (mine.limits.user && mine.limits.user.concurrency)
        || (mine.limits.anonymous && mine.limits.anonymous.concurrency))) || 0;
    check('me 回显下载并发上限', concurrency > 0, 'concurrency=' + concurrency);

    const invalidToken = new UgcClient({baseUrl: baseUrl, token: 'x'.repeat(43), timeoutMs: 15000});
    let badTokenCode = '';
    try {
        await invalidToken.me();
    } catch (error) {
        badTokenCode = (error.code || '') + '/' + (error.status || '');
    }
    check('无效 token 得到 401 bad_token', badTokenCode === 'bad_token/401', badTokenCode);

    const size = fs.statSync(fixtureZip).size;
    const uploaded = await client.uploadFile({
        file: fixtureZip,
        name: 'Client 模型',
        kind: 'live2d',
        description: '来自真实客户端的兼容性测试',
        tags: 'live2d client',
        license: 'CC0',
        maxBytes: 209715200,
        onLog: () => {},
    });
    const item = uploaded.item || uploaded;
    check('三步式上传成功', !!item && !!item.id, 'id=' + (item && item.id));
    check('Item 带 sha256 与 meta.entry', !!(item && item.sha256 && item.meta
        && String(item.meta.entry || '').endsWith('.model3.json')),
        item && item.meta ? String(item.meta.entry) : '');

    const list = await client.listItems({kind: 'live2d', page_size: 10});
    check('列表接口可用且包含刚上传的条目',
        Array.isArray(list.items) && list.items.some((entry) => String(entry.id) === String(item.id)),
        'total=' + list.total);

    const detail = await client.getItem(item.id);
    check('详情接口字段齐全', detail.item && detail.item.size === size && detail.item.author.username === username);

    const head = await client.headDownload(item.id);
    check('HEAD 给出长度/并发上限/摘要',
        head.size === size && Number(head.concurrencyLimit) > 0 && head.sha256 === sha256FileSync(fixtureZip),
        'size=' + head.size + ' concurrency=' + head.concurrencyLimit);

    const dest = fixtureZip + '.downloaded';
    const download = await client.downloadToFile({itemId: item.id, dest: dest, parts: 4, onLog: () => {}});
    const downloadedSha = sha256FileSync(dest);
    check('多线程下载并校验 sha256',
        download.bytes === size && downloadedSha === sha256FileSync(fixtureZip),
        'bytes=' + download.bytes + ' mode=' + download.mode);
    fs.unlinkSync(dest);

    // 匿名连下 8 次模型：额度用完时必须拿到 429（协议 §3）
    let limited = 0;
    const partFile = fixtureZip + '.anon-part';
    const anonymousClient = new UgcClient({baseUrl: baseUrl, timeoutMs: 15000});
    for (let i = 0; i < 8; i += 1) {
        try {
            await anonymousClient.downloadRange({itemId: item.id, start: 0, end: 15, file: partFile});
        } catch (error) {
            if (error.status === 429) {
                limited = 429;
                break;
            }
            throw error;
        }
    }
    fs.rmSync(partFile, {force: true});
    check('匿名下载模型超量后拿到 429', limited === 429, 'HTTP ' + limited);

    console.log('\n客户端兼容性：通过 ' + passed + ' 项，失败 ' + failed + ' 项');
    process.exit(failed === 0 ? 0 : 1);
}

main().catch((error) => {
    console.log('  FAIL 客户端流程异常：' + (error && error.message ? error.message : String(error)));
    console.log('\n客户端兼容性：通过 ' + passed + ' 项，失败 ' + (failed + 1) + ' 项');
    process.exit(1);
});
