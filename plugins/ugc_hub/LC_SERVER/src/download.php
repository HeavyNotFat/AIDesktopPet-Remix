<?php

declare(strict_types=1);

// 下载：整包 / Range / ?part=N，只按数据库里的路径取文件，绝不暴露真实路径。

function ugc_download(string $id): never
{
    ugc_require_method('GET', 'HEAD');
    $isHead = ugc_method() === 'HEAD';
    $user = ugc_current_user();
    $row = ugc_item_row((int) $id);
    if (!ugc_item_visible($row, $user)) {
        ugc_error(403, 'forbidden', '这条资源还没上架');
    }

    $path = ugc_upload_absolute((string) $row['file_path']);
    if ($path === null) {
        ugc_log('资源文件丢失', ['id' => (int) $row['id']]);
        ugc_error(410, 'file_missing', '文件已不存在，请联系上传者重新上传');
    }
    $size = (int) filesize($path);
    $type = (string) $row['type'];

    // 额度：未登录下模型才有上限（插件不限、登录用户不限）
    $status = ugc_limit_status($type, $user);
    if ($status['limited']) {
        if (!headers_sent()) {
            header('Retry-After: ' . max(1, $status['reset_at'] - time()));
        }
        ugc_error(429, 'rate_limited', '未登录用户模型下载已达每小时 ' . $status['limit'] . ' 次限制', [
            'retry_after' => max(1, $status['reset_at'] - time()),
        ]);
    }

    $range = ugc_download_range($size);
    $parts = max(1, min((int) ugc_config('limits.part_max', 64), (int) ceil($size / max(1, (int) ugc_config('limits.part_size', 8388608)))));
    $partSize = (int) ceil($size / $parts);
    $part = max(0, ugc_int($_GET['part'] ?? 0, 0));
    if ($part > 0) {
        if ($part > $parts) {
            ugc_error(404, 'no_such_part', '没有这一片');
        }
        $range = ['start' => ($part - 1) * $partSize, 'end' => min($size - 1, $part * $partSize - 1)];
    }

    // 计数口径：整包算一次；?part= 只在第 1 片算；Range 只在从 0 开始时算
    $shouldCount = $part > 0 ? $part === 1 : ($range === null || $range['start'] === 0);
    if (!$isHead && $shouldCount) {
        ugc_limit_record($type, $user);
        ugc_exec('UPDATE resources SET download_count = download_count + 1 WHERE id = :id', ['id' => (int) $row['id']]);
        if (random_int(1, 100) === 1) {
            ugc_limit_cleanup();
        }
    }

    ugc_download_headers($row, $size, $range, $parts, $partSize, $status);
    if ($isHead) {
        exit;
    }

    ugc_download_stream($path, $size, $range);
}

/** @return array{start: int, end: int}|null */
function ugc_download_range(int $size): ?array
{
    $header = (string) ($_SERVER['HTTP_RANGE'] ?? '');
    if (!preg_match('/^bytes=(\d*)-(\d*)$/', trim($header), $matches) || $size <= 0) {
        return null;
    }
    $start = $matches[1] === '' ? null : (int) $matches[1];
    $end = $matches[2] === '' ? null : (int) $matches[2];
    if ($start === null && $end === null) {
        return null;
    }
    if ($start === null) {
        $start = max(0, $size - (int) $end);
        $end = $size - 1;
    } else {
        $end = $end === null ? $size - 1 : min($end, $size - 1);
    }
    if ($start > $end || $start >= $size) {
        if (!headers_sent()) {
            header('Content-Range: bytes */' . $size);
        }
        ugc_error(416, 'bad_range', '请求的字节范围超出文件大小');
    }
    return ['start' => $start, 'end' => $end];
}

/** @param array<string, mixed> $row @param array{start: int, end: int}|null $range @param array<string, mixed> $status */
function ugc_download_headers(array $row, int $size, ?array $range, int $parts, int $partSize, array $status): void
{
    if (headers_sent()) {
        return;
    }
    $filename = (string) ($row['original_name'] ?? 'download');
    $ascii = preg_replace('/[^\x20-\x7E]/', '_', $filename) ?? 'download';
    $etag = '"' . substr((string) $row['sha256'], 0, 32) . '"';

    http_response_code($range === null ? 200 : 206);
    header('Content-Type: application/octet-stream');
    header('Content-Disposition: attachment; filename="' . str_replace('"', '', $ascii) . '"; filename*=UTF-8\'\'' . rawurlencode($filename));
    header('Content-Length: ' . ($range === null ? $size : $range['end'] - $range['start'] + 1));
    header('Accept-Ranges: bytes');
    header('ETag: ' . $etag);
    header('X-Item-SHA256: ' . (string) $row['sha256']);
    header('X-Part-Count: ' . $parts);
    header('X-Part-Size: ' . $partSize);
    header('X-Concurrency-Limit: ' . (int) ugc_config('limits.concurrency', 4));
    header('X-Concurrency-Remaining: ' . (int) ugc_config('limits.concurrency', 4));
    header('Cache-Control: no-store');
    header('X-Content-Type-Options: nosniff');
    if ($range !== null) {
        header(sprintf('Content-Range: bytes %d-%d/%d', $range['start'], $range['end'], $size));
    }
    if ($status['limit'] > 0) {
        header('X-RateLimit-Limit: ' . $status['limit']);
        header('X-RateLimit-Remaining: ' . max(0, $status['remaining'] - 1));
        header('X-RateLimit-Reset: ' . $status['reset_at']);
    }
}

/** @param array{start: int, end: int}|null $range */
function ugc_download_stream(string $path, int $size, ?array $range): never
{
    while (ob_get_level() > 0) {
        ob_end_clean();
    }
    $handle = fopen($path, 'rb');
    if ($handle === false) {
        exit;
    }
    if ($range === null) {
        fpassthru($handle);
    } else {
        fseek($handle, $range['start']);
        $remaining = $range['end'] - $range['start'] + 1;
        while ($remaining > 0 && !feof($handle)) {
            $chunk = fread($handle, (int) min(262144, $remaining));
            if ($chunk === false || $chunk === '') {
                break;
            }
            echo $chunk;
            $remaining -= strlen($chunk);
        }
    }
    fclose($handle);
    exit;
}
