'use strict';

// 素材站客户端：HTTP 请求、分片下载、三步上传、zip 解包。不依赖宿主 API，能单独用 node 跑。

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const zlib = require('zlib');
const http = require('http');
const https = require('https');

const DEFAULT_TIMEOUT = 30000;
const RANGE_CHUNK = 4 * 1024 * 1024;

class UgcError extends Error {
    constructor(message, status, code, extra) {
        super(message);
        this.name = 'UgcError';
        this.status = status || 0;
        this.code = code || '';
        this.extra = extra || {};
    }
}

function joinUrl(baseUrl, apiPath) {
    const base = String(baseUrl || '').trim().replace(/\/+$/, '');
    if (!/^https?:\/\//.test(base)) return '';
    return base + apiPath;
}

// 发一个 HTTP 请求，返回 {status, headers, body}；body 为 null 表示已经流式交给回调
function request(url, options) {
    const opts = options || {};
    const timeoutMs = Number(opts.timeoutMs) > 0 ? Number(opts.timeoutMs) : DEFAULT_TIMEOUT;
    return new Promise((resolve, reject) => {
        let target;
        try {
            target = new URL(url);
        } catch (err) {
            reject(new UgcError('素材站地址不对：' + url, 0, 'bad_url'));
            return;
        }
        const transport = target.protocol === 'https:' ? https : http;
        const headers = Object.assign({ Accept: 'application/json' }, opts.headers || {});
        if (opts.body && headers['Content-Length'] === undefined) {
            headers['Content-Length'] = Buffer.byteLength(opts.body);
        }
        const req = transport.request({
            protocol: target.protocol,
            hostname: target.hostname,
            port: target.port || (target.protocol === 'https:' ? 443 : 80),
            path: target.pathname + target.search,
            method: opts.method || 'GET',
            headers: headers,
            timeout: timeoutMs
        }, (res) => {
            const status = res.statusCode || 0;
            const location = res.headers.location;
            if (status >= 300 && status < 400 && location && (opts.redirects || 0) < 3) {
                res.resume();
                request(new URL(location, url).toString(), Object.assign({}, opts, {
                    redirects: (opts.redirects || 0) + 1
                })).then(resolve, reject);
                return;
            }
            const chunks = [];
            res.on('data', (chunk) => chunks.push(chunk));
            res.on('end', () => resolve({
                status: status,
                headers: res.headers,
                body: Buffer.concat(chunks)
            }));
            res.on('error', reject);
        });
        req.on('timeout', () => req.destroy(new UgcError('请求超时（' + timeoutMs + ' 毫秒）', 0, 'timeout', { transient: true })));
        req.on('error', (err) => reject(err instanceof UgcError ? err : new UgcError('连不上素材站：' + err.message, 0, 'network', { transient: true })));
        if (opts.body) req.write(opts.body);
        req.end();
    });
}

function errorFromResponse(response) {
    let code = '';
    let message = '';
    let extra = {};
    try {
        const payload = JSON.parse(response.body.toString('utf8'));
        if (payload && payload.error) {
            code = String(payload.error.code || '');
            message = String(payload.error.message || '');
            extra = payload.error;
        }
    } catch (err) {
        message = '';
    }
    if (!message) message = '素材站返回 ' + response.status;
    return new UgcError(message, response.status, code || 'http_' + response.status, extra);
}

async function callApi(client, method, apiPath, options) {
    const opts = options || {};
    const url = joinUrl(client.baseUrl, apiPath);
    if (!url) throw new UgcError('还没有配置素材站地址', 0, 'no_server');
    const headers = Object.assign({}, opts.headers || {});
    if (client.token && opts.auth !== false) headers.Authorization = 'Bearer ' + client.token;
    let body = null;
    if (opts.json !== undefined) {
        body = Buffer.from(JSON.stringify(opts.json), 'utf8');
        headers['Content-Type'] = 'application/json';
    } else if (opts.body) {
        body = opts.body;
    }
    const response = await request(url, {
        method: method,
        headers: headers,
        body: body,
        timeoutMs: opts.timeoutMs || client.timeoutMs
    });
    if (response.status >= 400) throw errorFromResponse(response);
    if (opts.raw) return response;
    if (!response.body.length) return {};
    try {
        return JSON.parse(response.body.toString('utf8'));
    } catch (err) {
        throw new UgcError('素材站返回的不是 JSON', response.status, 'bad_json');
    }
}

function createClient(options) {
    const opts = options || {};
    const client = {
        baseUrl: String(opts.baseUrl || '').trim(),
        token: String(opts.token || ''),
        timeoutMs: Number(opts.timeoutMs) > 0 ? Number(opts.timeoutMs) : DEFAULT_TIMEOUT
    };
    client.health = () => callApi(client, 'GET', '/api/health', { auth: false });
    client.me = () => callApi(client, 'GET', '/api/auth/me', { auth: !!client.token });
    client.login = (username, password) => callApi(client, 'POST', '/api/auth/login', {
        auth: false,
        json: { username: username, password: password }
    });
    client.register = (username, password) => callApi(client, 'POST', '/api/auth/register', {
        auth: false,
        json: { username: username, password: password }
    });
    client.logout = () => callApi(client, 'POST', '/api/auth/logout', { json: {} });
    client.listItems = (params) => {
        const query = new URLSearchParams();
        const source = params || {};
        ['kind', 'type', 'q', 'sort', 'page', 'page_size'].forEach((key) => {
            if (source[key] !== undefined && source[key] !== '' && source[key] !== null) {
                query.set(key, String(source[key]));
            }
        });
        const suffix = query.toString();
        return callApi(client, 'GET', '/api/items' + (suffix ? '?' + suffix : ''), {});
    };
    client.getItem = (id) => callApi(client, 'GET', '/api/items/' + encodeURIComponent(String(id)), {});
    client.headDownload = async (id) => {
        const response = await callApi(client, 'HEAD', '/api/items/' + encodeURIComponent(String(id)) + '/download', { raw: true });
        return {
            size: Number(response.headers['content-length']) || 0,
            sha256: String(response.headers['x-item-sha256'] || ''),
            acceptRanges: String(response.headers['accept-ranges'] || '').toLowerCase() === 'bytes',
            partCount: Number(response.headers['x-part-count']) || 1,
            partSize: Number(response.headers['x-part-size']) || 0,
            concurrencyLimit: Number(response.headers['x-concurrency-limit']) || 0,
            filename: decodeFilename(response.headers['content-disposition'] || '')
        };
    };
    client.downloadToFile = (params) => downloadToFile(client, params || {});
    client.uploadFile = (params) => uploadFile(client, params || {});
    return client;
}

function decodeFilename(header) {
    const star = /filename\*=UTF-8''([^;]+)/i.exec(header);
    if (star) {
        try {
            return decodeURIComponent(star[1].trim());
        } catch (err) {
            return star[1].trim();
        }
    }
    const plain = /filename="?([^";]+)"?/i.exec(header);
    return plain ? plain[1].trim() : '';
}

function sha256File(file, onProgress) {
    return new Promise((resolve, reject) => {
        const total = fs.statSync(file).size;
        const hash = crypto.createHash('sha256');
        const stream = fs.createReadStream(file, { highWaterMark: 1 << 20 });
        let done = 0;
        stream.on('data', (chunk) => {
            hash.update(chunk);
            done += chunk.length;
            if (onProgress) onProgress(done, total);
        });
        stream.on('end', () => resolve(hash.digest('hex')));
        stream.on('error', reject);
    });
}

// 多线程分片下载：服务端支持 Range 就并行拉，否则老实整包下
async function downloadToFile(client, params) {
    const itemId = params.itemId;
    const dest = params.dest;
    const threads = Math.max(1, Math.min(8, Number(params.threads) || 4));
    const report = params.onProgress || function () { };
    const head = await client.headDownload(itemId);
    if (!head.size) throw new UgcError('素材站没给出文件大小，没法下载', 0, 'no_length');
    fs.mkdirSync(path.dirname(dest), { recursive: true });

    if (!head.acceptRanges || head.size <= RANGE_CHUNK) {
        const response = await callApi(client, 'GET', '/api/items/' + encodeURIComponent(String(itemId)) + '/download', { raw: true });
        fs.writeFileSync(dest, response.body);
        report(response.body.length, head.size);
        return finishDownload(dest, head, params, response.body.length);
    }

    const fd = fs.openSync(dest, 'w+');
    try {
        fs.ftruncateSync(fd, head.size);
        const ranges = [];
        for (let start = 0; start < head.size; start += RANGE_CHUNK) {
            ranges.push([start, Math.min(head.size - 1, start + RANGE_CHUNK - 1)]);
        }
        let next = 0;
        let done = 0;
        const url = joinUrl(client.baseUrl, '/api/items/' + encodeURIComponent(String(itemId)) + '/download');
        const worker = async () => {
            for (;;) {
                const index = next++;
                if (index >= ranges.length) return;
                const range = ranges[index];
                const response = await request(url, {
                    method: 'GET',
                    headers: { Range: 'bytes=' + range[0] + '-' + range[1] },
                    timeoutMs: client.timeoutMs
                });
                if (response.status === 429 || response.status >= 400) throw errorFromResponse(response);
                // 服务端忽略了 Range：整包回来了，直接落盘收工
                if (response.status === 200 && response.body.length === head.size) {
                    fs.writeSync(fd, response.body, 0, response.body.length, 0);
                    done = head.size;
                    report(done, head.size);
                    next = ranges.length;
                    return;
                }
                fs.writeSync(fd, response.body, 0, response.body.length, range[0]);
                done += response.body.length;
                report(Math.min(done, head.size), head.size);
            }
        };
        const workers = [];
        for (let i = 0; i < Math.min(threads, ranges.length); i += 1) workers.push(worker());
        await Promise.all(workers);
    } finally {
        fs.closeSync(fd);
    }
    return finishDownload(dest, head, params, head.size);
}

function finishDownload(dest, head, params, bytes) {
    const verify = params.verify !== false && head.sha256;
    const actual = verify ? crypto.createHash('sha256').update(fs.readFileSync(dest)).digest('hex') : '';
    if (verify && actual !== head.sha256) {
        throw new UgcError('下载的文件校验失败（sha256 对不上）', 0, 'sha256_mismatch');
    }
    return { bytes: bytes, sha256: actual || head.sha256, filename: head.filename, dest: dest };
}

// 三步分片上传：开会话 → 逐片 POST（Content-Range）→ 提交
async function uploadFile(client, params) {
    const file = params.file;
    const report = params.onProgress || function () { };
    const stat = fs.statSync(file);
    const total = stat.size;
    const sha256 = await sha256File(file, (done) => report(Math.floor(done / 2), total * 2));
    const displayName = String(params.name || path.basename(file));
    const kind = String(params.kind || 'other');

    const opened = await callApi(client, 'POST', '/api/uploads', {
        json: { size: total, sha256: sha256, name: displayName, kind: kind }
    });
    const uploadId = String(opened.upload_id || '');
    if (!uploadId) throw new UgcError('素材站没有返回 upload_id', 0, 'bad_upload');
    let offset = Number(opened.offset) || 0;
    const chunkSize = Number(opened.chunk_size) > 0 ? Number(opened.chunk_size) : RANGE_CHUNK;
    const fd = fs.openSync(file, 'r');
    try {
        while (offset < total) {
            const end = Math.min(total - 1, offset + chunkSize - 1);
            const buffer = Buffer.alloc(end - offset + 1);
            fs.readSync(fd, buffer, 0, buffer.length, offset);
            const response = await callApi(client, 'POST', '/api/uploads/' + encodeURIComponent(uploadId) + '/chunk', {
                body: buffer,
                headers: { 'Content-Range': 'bytes ' + offset + '-' + end + '/' + total },
                raw: true
            });
            if (response.status === 308) {
                const payload = JSON.parse(response.body.toString('utf8'));
                offset = Number(payload.offset) || 0;
                continue;
            }
            const payload = JSON.parse(response.body.toString('utf8'));
            offset = Number(payload.offset) || end + 1;
            report(total + offset, total * 2);
        }
    } finally {
        fs.closeSync(fd);
    }

    const completed = await callApi(client, 'POST', '/api/uploads/' + encodeURIComponent(uploadId) + '/complete', {
        json: {
            name: displayName,
            kind: kind,
            description: String(params.description || ''),
            tags: String(params.tags || ''),
            license: String(params.license || 'UNKNOWN')
        }
    });
    return { item: completed.item || null, duplicate: !!completed.duplicate, sha256: sha256, size: total };
}

// ---------------------------------------------------------------- zip 解包

function readZipEntries(zipPath) {
    const size = fs.statSync(zipPath).size;
    const fd = fs.openSync(zipPath, 'r');
    try {
        const tailLength = Math.min(size, 66000);
        const tail = Buffer.alloc(tailLength);
        fs.readSync(fd, tail, 0, tailLength, size - tailLength);
        const eocd = tail.lastIndexOf(Buffer.from([0x50, 0x4b, 0x05, 0x06]));
        if (eocd < 0) throw new UgcError('这个文件不是合法的 zip', 0, 'bad_zip');
        const count = tail.readUInt16LE(eocd + 10);
        const cdSize = tail.readUInt32LE(eocd + 12);
        const cdOffset = tail.readUInt32LE(eocd + 16);
        const directory = Buffer.alloc(cdSize);
        fs.readSync(fd, directory, 0, cdSize, cdOffset);

        const entries = [];
        let cursor = 0;
        for (let i = 0; i < count && cursor + 46 <= directory.length; i += 1) {
            if (directory.readUInt32LE(cursor) !== 0x02014b50) break;
            const method = directory.readUInt16LE(cursor + 10);
            const compressedSize = directory.readUInt32LE(cursor + 20);
            const uncompressedSize = directory.readUInt32LE(cursor + 24);
            const nameLength = directory.readUInt16LE(cursor + 28);
            const extraLength = directory.readUInt16LE(cursor + 30);
            const commentLength = directory.readUInt16LE(cursor + 32);
            const localOffset = directory.readUInt32LE(cursor + 42);
            const name = directory.slice(cursor + 46, cursor + 46 + nameLength).toString('utf8');
            cursor += 46 + nameLength + extraLength + commentLength;

            if (!name || name.endsWith('/')) continue;
            if (name.startsWith('/') || /^[A-Za-z]:/.test(name) || name.includes('\\') || name.split('/').includes('..')) {
                throw new UgcError('压缩包里有不安全的路径：' + name, 0, 'bad_entry');
            }
            const localHeader = Buffer.alloc(30);
            fs.readSync(fd, localHeader, 0, 30, localOffset);
            const localNameLength = localHeader.readUInt16LE(26);
            const localExtraLength = localHeader.readUInt16LE(28);
            entries.push({
                name: name,
                method: method,
                compressedSize: compressedSize,
                uncompressedSize: uncompressedSize,
                dataOffset: localOffset + 30 + localNameLength + localExtraLength
            });
        }
        return { fd: fd, entries: entries };
    } catch (err) {
        fs.closeSync(fd);
        throw err;
    }
}

function unzipTo(zipPath, destDir, onProgress) {
    const report = onProgress || function () { };
    const archive = readZipEntries(zipPath);
    const written = [];
    try {
        archive.entries.forEach((entry, index) => {
            const chunk = Buffer.alloc(entry.compressedSize);
            if (entry.compressedSize > 0) {
                fs.readSync(archive.fd, chunk, 0, entry.compressedSize, entry.dataOffset);
            }
            let data;
            if (entry.method === 0) {
                data = chunk;
            } else if (entry.method === 8) {
                data = zlib.inflateRawSync(chunk);
            } else {
                throw new UgcError('压缩方式不支持：' + entry.name, 0, 'bad_method');
            }
            const target = path.join(destDir, entry.name);
            fs.mkdirSync(path.dirname(target), { recursive: true });
            fs.writeFileSync(target, data);
            written.push(entry.name);
            report(index + 1, archive.entries.length);
        });
    } finally {
        fs.closeSync(archive.fd);
    }
    return written;
}

function formatBytes(bytes) {
    const value = Number(bytes) || 0;
    if (value < 1024) return value + ' B';
    if (value < 1024 * 1024) return (value / 1024).toFixed(1) + ' KB';
    if (value < 1024 * 1024 * 1024) return (value / 1024 / 1024).toFixed(1) + ' MB';
    return (value / 1024 / 1024 / 1024).toFixed(2) + ' GB';
}

function describeError(error) {
    if (!error) return '未知错误';
    const status = error.status ? '（HTTP ' + error.status + '）' : '';
    return String(error.message || error) + status;
}

module.exports = {
    UgcError,
    createClient,
    request,
    callApi,
    joinUrl,
    sha256File,
    downloadToFile,
    uploadFile,
    unzipTo,
    readZipEntries,
    formatBytes,
    describeError,
    RANGE_CHUNK
};
