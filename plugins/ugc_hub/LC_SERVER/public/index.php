<?php

declare(strict_types=1);

// 唯一对外入口：把 /api/* 分发到各模块。路径都按站点根算，客户端直接请求 /api/xxx 即可。

ini_set('display_errors', '0');
error_reporting(E_ALL);

require dirname(__DIR__) . '/src/core.php';
require dirname(__DIR__) . '/src/limits.php';
require dirname(__DIR__) . '/src/auth.php';
require dirname(__DIR__) . '/src/uploads.php';
require dirname(__DIR__) . '/src/items.php';
require dirname(__DIR__) . '/src/download.php';

set_exception_handler(static function (Throwable $error): void {
    ugc_log('未捕获异常', ['type' => $error::class, 'message' => $error->getMessage()]);
    if (headers_sent()) {
        exit;
    }
    $detail = ugc_config('app.debug') ? ['detail' => $error->getMessage()] : [];
    ugc_error(500, 'server_error', '服务器开小差了，请稍后再试', $detail);
});

function ugc_health(): never
{
    ugc_require_method('GET');
    $concurrency = (int) ugc_config('limits.concurrency', 4);
    ugc_send([
        'ok' => true,
        'name' => (string) ugc_config('app.name', 'ugc-hub'),
        'version' => (string) ugc_config('app.version', '2.0.0'),
        'time' => gmdate('Y-m-d\TH:i:s\Z'),
        'limits' => [
            'anonymous' => [
                'rate_per_minute' => (int) ugc_config('limits.list_per_minute', 120),
                'download_per_minute' => (int) ugc_config('limits.download_per_minute', 120),
                'concurrency' => $concurrency,
                'download_concurrency' => $concurrency,
            ],
            'user' => [
                'rate_per_minute' => (int) ugc_config('limits.list_per_minute', 120) * 5,
                'download_per_minute' => (int) ugc_config('limits.download_per_minute', 120) * 5,
                'concurrency' => $concurrency * 4,
                'download_concurrency' => $concurrency * 4,
            ],
            'current' => ['rate' => 0, 'download' => 0, 'concurrency' => 0],
            'model_anonymous_per_hour' => (int) ugc_config('limits.model_anonymous_per_hour', 5),
        ],
    ]);
}

$path = ugc_path();
$method = ugc_method();

if ($path === '/api/health') {
    ugc_health();
}
if ($path === '/api/auth/register') {
    ugc_auth_register();
}
if ($path === '/api/auth/login') {
    ugc_auth_login();
}
if ($path === '/api/auth/logout') {
    ugc_auth_logout();
}
if ($path === '/api/auth/me') {
    ugc_auth_me();
}
if ($path === '/api/items') {
    ugc_items_index();
}
if ($path === '/api/uploads') {
    ugc_upload_purge_expired();
    ugc_upload_open();
}
if (preg_match('#^/api/uploads/([A-Za-z0-9_]+)/(chunk|complete)$#', $path, $matches)) {
    $matches[2] === 'chunk' ? ugc_upload_chunk($matches[1]) : ugc_upload_complete($matches[1]);
}
if (preg_match('#^/api/items/(\d{1,10})$#', $path, $matches)) {
    if ($method === 'DELETE') {
        ugc_items_delete($matches[1]);
    }
    ugc_items_show($matches[1]);
}
if (preg_match('#^/api/items/(\d{1,10})/status$#', $path, $matches)) {
    ugc_items_status($matches[1]);
}
if (preg_match('#^/api/items/(\d{1,10})/download$#', $path, $matches)) {
    ugc_download($matches[1]);
}

ugc_error(404, 'no_such_route', '接口不存在');