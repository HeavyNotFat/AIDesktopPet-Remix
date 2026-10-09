<?php

declare(strict_types=1);

// 三步分片上传：开会话 → 传分片（Content-Range）→ 提交；会话状态存 storage/tmp 的 JSON。
// 顺带做全部文件校验：扩展名、魔数、压缩包条目，确认不是可执行/伪装文件。

function ugc_upload_open(): never
{
    ugc_require_method('POST');
    $user = ugc_require_user();

    $size = ugc_int(ugc_param('size'), 0);
    $sha256 = strtolower(ugc_text(ugc_param('sha256'), 64));
    $name = ugc_text(ugc_param('name'), 120);
    $kind = ugc_text(ugc_param('kind'), 16);

    $maxBytes = max(
        (int) ugc_config('upload.max_bytes.model', 209715200),
        (int) ugc_config('upload.max_bytes.plugin', 26214400)
    );
    if ($size <= 0 || $size > $maxBytes) {
        ugc_error(413, 'payload_too_large', '文件大小超出上限');
    }
    if (!preg_match('/^[0-9a-f]{64}$/', $sha256)) {
        ugc_error(422, 'bad_field', 'sha256 必须是 64 位十六进制', ['field' => 'sha256']);
    }
    if ($name === '') {
        ugc_error(422, 'bad_field', '缺少文件名字段 name', ['field' => 'name']);
    }
    if (($problem = ugc_extension_problem($name, '')) !== null) {
        ugc_error(415, 'unsupported_media_type', $problem);
    }
    ugc_upload_quota_check((int) $user['id']);

    $id = 'up_' . ugc_hex(12);
    $tempPath = ugc_upload_temp_path($id);
    if (@file_put_contents($tempPath, '') === false) {
        ugc_error(500, 'storage_error', '服务器无法写入临时目录');
    }

    ugc_upload_session_save($id, [
        'id' => $id,
        'user_id' => (int) $user['id'],
        'size' => $size,
        'sha256' => $sha256,
        'name' => $name,
        'kind' => $kind,
        'offset' => 0,
        'temp_path' => $tempPath,
        'created_at' => time(),
    ]);

    ugc_send([
        'upload_id' => $id,
        'offset' => 0,
        'chunk_size' => (int) ugc_config('limits.chunk_size', 8388608),
        'expires_at' => gmdate('Y-m-d\TH:i:s\Z', time() + (int) ugc_config('limits.upload_session_ttl', 86400)),
    ], 201);
}

function ugc_upload_chunk(string $id): never
{
    ugc_require_method('POST');
    $session = ugc_upload_session($id);

    $range = (string) ($_SERVER['HTTP_CONTENT_RANGE'] ?? '');
    if (!preg_match('/^bytes\s+(\d+)-(\d+)\/(\d+)$/', trim($range), $matches)) {
        ugc_error(400, 'bad_range', '缺少或无法解析 Content-Range');
    }
    $start = (int) $matches[1];
    $end = (int) $matches[2];
    $total = (int) $matches[3];

    if ($total !== (int) $session['size'] || $end < $start) {
        ugc_error(400, 'bad_range', 'Content-Range 与上传会话不匹配');
    }

    $offset = (int) $session['offset'];
    // 乱序/重发的分片：告诉客户端当前真实进度，让它从这里接着传
    if ($start !== $offset) {
        ugc_send(['offset' => $offset, 'expected' => $offset], 308);
    }

    $handle = fopen((string) $session['temp_path'], 'ab');
    if ($handle === false) {
        ugc_error(500, 'storage_error', '服务器无法写入临时文件');
    }
    $stream = fopen('php://input', 'rb');
    $written = 0;
    $expected = $end - $start + 1;
    if ($stream !== false) {
        while (!feof($stream)) {
            $chunk = fread($stream, 262144);
            if ($chunk === false || $chunk === '') {
                break;
            }
            $written += strlen($chunk);
            fwrite($handle, $chunk);
        }
        fclose($stream);
    }
    fclose($handle);

    if ($written !== $expected) {
        // 字节数对不上就回退，让客户端把这一段重发
        ugc_upload_truncate((string) $session['temp_path'], $offset);
        ugc_error(400, 'bad_chunk', '这一段字节数和 Content-Range 对不上');
    }

    $session['offset'] = $offset + $written;
    ugc_upload_session_save($id, $session);
    ugc_send(['offset' => (int) $session['offset'], 'received' => $written]);
}

function ugc_upload_complete(string $id): never
{
    ugc_require_method('POST');
    $session = ugc_upload_session($id);

    if ((int) $session['offset'] !== (int) $session['size']) {
        ugc_error(409, 'upload_incomplete', '文件还没传完', ['offset' => (int) $session['offset']]);
    }

    $tempPath = (string) $session['temp_path'];
    if (hash_file('sha256', $tempPath) !== (string) $session['sha256']) {
        ugc_upload_session_delete($id, true);
        ugc_error(422, 'sha256_mismatch', '文件校验失败，请重新上传');
    }

    $user = ugc_require_user();
    if ((int) $session['user_id'] !== (int) $user['id']) {
        ugc_error(403, 'forbidden', '这不是你的上传会话');
    }

    // 开会话时传的 name 是原始文件名；提交时传的 name 是展示标题
    $originalName = (string) $session['name'];
    $title = ugc_text(ugc_param('name', $originalName), 120) ?: $originalName;
    $kind = ugc_text(ugc_param('kind', $session['kind']), 16);
    $description = ugc_text(ugc_param('description'), 5000);
    $tags = ugc_text(ugc_param('tags'), 200);
    $license = ugc_text(ugc_param('license', 'UNKNOWN'), 32) ?: 'UNKNOWN';

    // 同一份文件重复上传：直接回已有条目，不新建也不重复占盘
    $duplicate = ugc_one(
        'SELECT * FROM resources WHERE uploader_id = :id AND sha256 = :sha LIMIT 1',
        ['id' => (int) $user['id'], 'sha' => (string) $session['sha256']]
    );
    if ($duplicate !== null) {
        ugc_upload_session_delete($id, true);
        ugc_send(['item' => ugc_item_shape(ugc_item_row((int) $duplicate['id'])), 'duplicate' => true], 200);
    }

    $info = ugc_validate_file($tempPath, $originalName, $kind);
    $type = $info['type'];
    $target = ugc_upload_move($tempPath, $type, (string) $session['sha256'], (string) $info['ext']);

    ugc_exec(
        'INSERT INTO resources
            (title, description, type, kind, tags, license, file_name, original_name, file_path, file_size,
             sha256, entry_path, file_count, uploader_id, download_count, status, created_at, updated_at)
         VALUES
            (:title, :description, :type, :kind, :tags, :license, :file_name, :original_name, :file_path, :file_size,
             :sha256, :entry_path, :file_count, :uploader_id, 0, :status, :created_at, :updated_at)',
        [
            'title' => $title,
            'description' => $description,
            'type' => $type,
            'kind' => $info['kind'],
            'tags' => $tags,
            'license' => $license,
            'file_name' => basename($target),
            'original_name' => $originalName,
            'file_path' => ugc_upload_relative($target),
            'file_size' => (int) $session['size'],
            'sha256' => (string) $session['sha256'],
            'entry_path' => $info['entry'],
            'file_count' => $info['files'],
            'uploader_id' => (int) $user['id'],
            'status' => 'published',
            'created_at' => ugc_now(),
            'updated_at' => ugc_now(),
        ]
    );
    $newId = (int) ugc_db()->lastInsertId();
    ugc_upload_session_delete($id);

    ugc_send(['item' => ugc_item_shape(ugc_item_row($newId))], 201);
}

// ---------------------------------------------------------------- 会话状态

function ugc_upload_session_path(string $id): string
{
    $tmp = (string) ugc_config('storage.tmp');
    if (!is_dir($tmp)) {
        @mkdir($tmp, 0755, true);
    }
    return $tmp . '/upload-' . preg_replace('/[^A-Za-z0-9_]/', '', $id) . '.json';
}

function ugc_upload_temp_path(string $id): string
{
    $directory = (string) ugc_config('storage.tmp') . '/parts';
    if (!is_dir($directory)) {
        @mkdir($directory, 0755, true);
    }
    return $directory . '/' . preg_replace('/[^A-Za-z0-9_]/', '', $id) . '.part';
}

/** @param array<string, mixed> $session */
function ugc_upload_session_save(string $id, array $session): void
{
    @file_put_contents(ugc_upload_session_path($id), (string) json_encode($session), LOCK_EX);
}

/** @return array<string, mixed> */
function ugc_upload_session(string $id): array
{
    $user = ugc_require_user();
    $path = ugc_upload_session_path($id);
    $session = is_file($path) ? json_decode((string) file_get_contents($path), true) : null;
    if (!is_array($session)) {
        ugc_error(404, 'no_such_upload', '上传会话不存在或已过期');
    }
    $ttl = (int) ugc_config('limits.upload_session_ttl', 86400);
    if ((int) $session['created_at'] + $ttl < time()) {
        ugc_upload_session_delete($id, true);
        ugc_error(404, 'no_such_upload', '上传会话已过期，请重新开始');
    }
    if ((int) $session['user_id'] !== (int) $user['id']) {
        ugc_error(403, 'forbidden', '这不是你的上传会话');
    }
    return $session;
}

function ugc_upload_session_delete(string $id, bool $withTemp = false): void
{
    $path = ugc_upload_session_path($id);
    if ($withTemp && is_file($path)) {
        $session = json_decode((string) file_get_contents($path), true);
        if (is_array($session) && is_file((string) $session['temp_path'])) {
            @unlink((string) $session['temp_path']);
        }
    }
    @unlink($path);
}

function ugc_upload_truncate(string $path, int $size): void
{
    $handle = fopen($path, 'r+b');
    if ($handle !== false) {
        ftruncate($handle, $size);
        fclose($handle);
    }
}

/** 过期会话顺手清掉（每次开会话时做一次，不做定时任务也不会有垃圾堆积）。 */
function ugc_upload_purge_expired(): void
{
    $tmp = (string) ugc_config('storage.tmp');
    $ttl = (int) ugc_config('limits.upload_session_ttl', 86400);
    foreach (glob($tmp . '/upload-*.json') ?: [] as $file) {
        $session = json_decode((string) file_get_contents($file), true);
        if (!is_array($session) || (int) ($session['created_at'] ?? 0) + $ttl < time()) {
            if (is_array($session) && is_file((string) ($session['temp_path'] ?? ''))) {
                @unlink((string) $session['temp_path']);
            }
            @unlink($file);
        }
    }
}

// ---------------------------------------------------------------- 文件校验

/** 后缀是否允许（$type 为空表示还不知道类型，只要不在黑名单就放过）。 */
function ugc_extension_problem(string $name, string $type): ?string
{
    $chain = array_values(array_filter(explode('.', strtolower($name))));
    if ($chain === []) {
        return '文件没有扩展名';
    }
    $forbidden = (array) ugc_config('upload.forbidden', []);
    $allowed = array_merge(
        (array) ugc_config('upload.extensions.model', []),
        (array) ugc_config('upload.extensions.plugin', []),
        (array) ugc_config('upload.archive_extra', [])
    );
    foreach ($chain as $index => $extension) {
        if ($index === 0) {
            continue;
        }
        if (in_array($extension, $forbidden, true)) {
            return '不允许上传 ' . $extension . ' 文件';
        }
        if ($type !== '' && $index === count($chain) - 1) {
            $wanted = (array) ugc_config('upload.extensions.' . $type, []);
            if (!in_array($extension, $wanted, true)) {
                return '这种类型（' . $extension . '）不在允许列表里';
            }
        }
        if ($type === '' && !in_array($extension, $allowed, true)) {
            return '这种类型（' . $extension . '）不在允许列表里';
        }
    }
    return null;
}

/** 看内容定类型：返回 type/kind/entry/files/ext（ext 用于落盘命名）。 */
function ugc_validate_file(string $path, string $name, string $kindHint): array
{
    $extension = strtolower(pathinfo($name, PATHINFO_EXTENSION));
    $head = (string) file_get_contents($path, false, null, 0, 4096);
    $isZip = str_starts_with($head, "PK\x03\x04") || str_starts_with($head, "PK\x05\x06") || str_starts_with($head, "PK\x07\x08");
    $is7z = str_starts_with($head, "7z\xBC\xAF\x27\x1C");
    $isRar = str_starts_with($head, "Rar!\x1A\x07");
    // 客户端开会话时传的往往是展示名（没有扩展名），所以类型主要看 kind 和内容
    $type = in_array($extension, ['js', 'mjs'], true) || in_array($kindHint, ['plugin', 'js'], true) ? 'plugin' : 'model';

    if (($problem = ugc_extension_problem($name, $extension === '' ? '' : $type)) !== null) {
        ugc_error(415, 'unsupported_media_type', $problem);
    }
    // 扩展名说是压缩包、内容却不是：直接拒收
    if (in_array($extension, ['zip', '7z', 'rar'], true) && !($isZip || $is7z || $isRar)) {
        ugc_error(415, 'bad_archive', '文件内容不像压缩包，扩展名对不上');
    }
    $size = (int) filesize($path);
    if ($size > (int) ugc_config('upload.max_bytes.' . $type, 0)) {
        ugc_error(413, 'payload_too_large', $type === 'plugin' ? '插件超过大小上限' : '模型超过大小上限');
    }

    $info = [
        'type' => $type,
        'kind' => $kindHint !== '' ? $kindHint : 'other',
        'entry' => '',
        'files' => 1,
        'ext' => $extension,
    ];

    if ($isZip) {
        $archive = ugc_inspect_zip($path, $type);
        $info['files'] = $archive['files'];
        $info['entry'] = $archive['entry'];
        $info['ext'] = $extension === '' ? 'zip' : $extension;
        if ($kindHint === '' || $kindHint === 'other') {
            $info['kind'] = $archive['kind'];
        }
        if ($archive['kind'] === 'plugin') {
            $info['type'] = 'plugin';
        }
        return $info;
    }

    if ($is7z || $isRar) {
        $info['ext'] = $extension === '' ? ($is7z ? '7z' : 'rar') : $extension;
        return $info;
    }

    if ($extension === '') {
        ugc_error(415, 'unsupported_media_type', '文件没有扩展名，内容也不是压缩包，无法确认类型');
    }
    if (in_array($extension, ['js', 'mjs', 'json'], true) || $type === 'plugin') {
        if (preg_match('/<\?php|<\?=|<%|<jsp|#!\//i', $head)) {
            ugc_error(415, 'unsupported_media_type', '文件里含有服务端脚本标记');
        }
    }
    if ($extension === 'json' && json_decode((string) file_get_contents($path), true) === null) {
        ugc_error(422, 'bad_json', 'JSON 文件解析失败');
    }
    return $info;
}

/** 只读 ZIP 中央目录，不解压；返回条目数、入口文件和推断出的 kind。 */
function ugc_inspect_zip(string $path, string $type): array
{
    $size = (int) filesize($path);
    $handle = fopen($path, 'rb');
    if ($handle === false) {
        ugc_error(500, 'storage_error', '读不了上传的压缩包');
    }
    $tailLength = min($size, 66000);
    fseek($handle, $size - $tailLength);
    $tail = (string) fread($handle, $tailLength);
    $eocd = strrpos($tail, "PK\x05\x06");
    if ($eocd === false) {
        fclose($handle);
        ugc_error(415, 'bad_zip', '这不是一个合法的 zip 压缩包');
    }
    $footer = unpack('vdisk/vcddisk/vcount/vtotal/Vsize/Voffset', substr($tail, $eocd + 4, 18));
    $count = (int) ($footer['total'] ?? 0);
    if ($count <= 0 || $count > (int) ugc_config('upload.max_entries', 2000)) {
        fclose($handle);
        ugc_error(400, 'bad_entry', '压缩包里的文件数量不正常');
    }

    fseek($handle, (int) $footer['offset']);
    $buffer = (string) fread($handle, (int) $footer['size']);
    fclose($handle);

    $forbidden = (array) ugc_config('upload.forbidden', []);
    $allowed = array_merge(
        (array) ugc_config('upload.extensions.model', []),
        (array) ugc_config('upload.archive_extra', [])
    );
    $images = (array) ugc_config('upload.image_extensions', []);
    $totalUncompressed = 0;
    $files = 0;
    $entry = '';
    $moc3 = [];
    $images_ = 0;
    $hasScript = false;
    $cursor = 0;

    while ($cursor + 46 <= strlen($buffer)) {
        if (substr($buffer, $cursor, 4) !== "PK\x01\x02") {
            ugc_error(400, 'bad_entry', '压缩包中央目录损坏');
        }
        $header = unpack(
            'vmade/vneed/vflags/vmethod/vtime/vdate/Vcrc/Vcompressed/Vuncompressed'
            . '/vnamelen/vextralen/vcommentlen/vdisk/vinternal/Vexternal/Voffset',
            substr($buffer, $cursor + 4, 42)
        );
        $nameLength = (int) $header['namelen'];
        $name = substr($buffer, $cursor + 46, $nameLength);
        $cursor += 46 + $nameLength + (int) $header['extralen'] + (int) $header['commentlen'];

        if (str_ends_with($name, '/')) {
            continue;
        }
        if (preg_match('#(^/|^[A-Za-z]:|\\\\|(^|/)\.\.(/|$))#', $name)) {
            ugc_error(400, 'bad_entry', '压缩包里有非法路径：' . mb_substr($name, 0, 60));
        }
        if ((int) $header['uncompressed'] > (int) ugc_config('upload.max_entry_bytes', 33554432)) {
            ugc_error(400, 'bad_entry', '压缩包里有超大文件：' . mb_substr($name, 0, 60));
        }
        if (in_array((int) $header['method'], [0, 8], true) === false) {
            ugc_error(400, 'bad_entry', '压缩方式不支持：' . mb_substr($name, 0, 60));
        }
        $chain = array_values(array_filter(explode('.', strtolower($name))));
        foreach ($chain as $index => $extension) {
            if ($index === 0) {
                continue;
            }
            if (in_array($extension, $forbidden, true)) {
                ugc_error(400, 'bad_entry', '压缩包里有禁止的文件类型：' . mb_substr($name, 0, 60));
            }
        }
        $extension = strtolower(pathinfo($name, PATHINFO_EXTENSION));
        if (in_array($extension, ['zip', '7z', 'rar', 'tar', 'gz'], true)) {
            ugc_error(400, 'bad_entry', '压缩包里不允许再套压缩包：' . mb_substr($name, 0, 60));
        }
        if (!in_array($extension, $allowed, true)) {
            ugc_error(400, 'bad_entry', '压缩包里有不在白名单里的类型：' . mb_substr($name, 0, 60));
        }

        $files++;
        $totalUncompressed += (int) $header['uncompressed'];
        if (in_array($extension, $images, true)) {
            $images_++;
        }
        if (in_array($extension, ['js', 'mjs'], true)) {
            $hasScript = true;
        }
        if (str_ends_with(strtolower($name), '.model3.json') && $entry === '') {
            $entry = $name;
        }
        if ($extension === 'moc3') {
            $moc3[] = preg_replace('/\.moc3$/i', '', $name);
        }
    }

    if ($totalUncompressed > (int) ugc_config('upload.max_unzip_bytes', 536870912)) {
        ugc_error(400, 'unzip_too_large', '压缩包解压后太大了');
    }
    if ($size > 0 && $totalUncompressed > $size * (int) ugc_config('upload.max_ratio', 200)) {
        ugc_error(400, 'ratio_too_high', '压缩比异常，疑似压缩炸弹');
    }

    $kind = 'other';
    if ($entry !== '') {
        $stem = preg_replace('/\.model3\.json$/i', '', $entry);
        if ($moc3 === [] || in_array($stem, $moc3, true)) {
            $kind = 'live2d';
        }
    } elseif ($hasScript && $images_ === 0) {
        $kind = 'plugin';
    } elseif ($images_ > 0) {
        $kind = 'static';
    }

    return ['files' => $files, 'entry' => $entry, 'kind' => $kind];
}

// ---------------------------------------------------------------- 落盘

function ugc_upload_move(string $tempPath, string $type, string $sha256, string $extension): string
{
    $extension = preg_replace('/[^a-z0-9]/', '', strtolower($extension)) ?: 'bin';
    $directory = sprintf('%s/%s/%s', ugc_config('storage.uploads'), $type, substr($sha256, 0, 2));
    if (!is_dir($directory) && !@mkdir($directory, 0755, true)) {
        ugc_error(500, 'storage_error', '服务器无法创建上传目录');
    }
    ugc_ensure_upload_guard((string) ugc_config('storage.uploads'));

    $target = sprintf('%s/%s.%s', $directory, substr($sha256, 0, 32), $extension);
    // 路径是按 sha256 算的：内容一样就已经在盘上了，直接留用
    if (is_file($target)) {
        @unlink($tempPath);
        return $target;
    }
    if (!@rename($tempPath, $target)) {
        if (!@copy($tempPath, $target)) {
            ugc_error(500, 'storage_error', '保存上传文件失败');
        }
        @unlink($tempPath);
    }
    @chmod($target, 0640);
    return $target;
}

function ugc_upload_relative(string $absolutePath): string
{
    $base = rtrim((string) ugc_config('storage.uploads'), '/');
    return ltrim(str_replace($base, '', $absolutePath), '/');
}

function ugc_upload_absolute(string $relativePath): ?string
{
    $base = realpath((string) ugc_config('storage.uploads'));
    $target = realpath(rtrim((string) ugc_config('storage.uploads'), '/') . '/' . ltrim($relativePath, '/'));
    if ($base === false || $target === false || !str_starts_with($target, $base . DIRECTORY_SEPARATOR)) {
        return null;
    }
    return is_file($target) ? $target : null;
}

/** 上传目录每次用到就补一份禁止执行/访问的 .htaccess（Nginx 请自行 deny）。 */
function ugc_ensure_upload_guard(string $directory): void
{
    $file = rtrim($directory, '/') . '/.htaccess';
    if (is_file($file)) {
        return;
    }
    @file_put_contents($file, "php_flag engine off\nRemoveHandler .php .phtml .phar .cgi .pl .py .asp .aspx .jsp .sh\n<IfModule mod_authz_core.c>\n    Require all denied\n</IfModule>\n<IfModule !mod_authz_core.c>\n    Order allow,deny\n    Deny from all\n</IfModule>\nOptions -ExecCGI -Indexes\n");
}
