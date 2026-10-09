<?php

declare(strict_types=1);

// 全部配置都在这里；优先级：环境变量 > src/config.local.php > 本文件的默认值。

$config = [
    'app' => [
        'name' => 'ugc-hub',
        'version' => '2.0.0',
        'debug' => false,
    ],
    'db' => [
        'host' => '127.0.0.1',
        'port' => 3306,
        'database' => 'ugc',
        'username' => 'ugc',
        'password' => '',
    ],
    // 上传文件必须放在 web 根之外：默认落在项目的 storage/ 下
    'storage' => [
        'uploads' => dirname(__DIR__) . '/storage/uploads',
        'tmp' => dirname(__DIR__) . '/storage/tmp',
        'logs' => dirname(__DIR__) . '/storage/logs',
    ],
    'limits' => [
        'model_anonymous_per_hour' => 5,     // 未登录下模型：每小时上限，0 = 不限
        'plugin_anonymous_per_hour' => 0,    // 插件不限
        'uploads_per_hour' => 10,            // 每个用户每小时上传数
        'list_per_minute' => 120,            // 只是回显给客户端的参考值，不做强制
        'download_per_minute' => 120,
        'login_max_failures' => 5,           // 连续失败几次开始锁
        'login_lock_seconds' => 900,         // 首次锁多久（之后翻倍，上限 24 小时）
        'chunk_size' => 8388608,             // 分片上传的片大小
        'upload_session_ttl' => 86400,       // 上传会话有效期（秒）
        'concurrency' => 4,                  // 回显给客户端的并发下载上限
        'part_size' => 8388608,              // ?part=N 模式的片大小
        'part_max' => 64,
        'history_days' => 7,                 // 限流流水保留天数
    ],
    'upload' => [
        'max_bytes' => ['model' => 209715200, 'plugin' => 26214400],
        'max_entries' => 2000,
        'max_unzip_bytes' => 536870912,
        'max_ratio' => 200,
        'max_entry_bytes' => 33554432,
        'extensions' => [
            'model' => [
                'zip', '7z', 'rar', 'tar', 'gz',
                'json', 'moc3', 'model3', 'physics3', 'pose3', 'cdi3', 'exp3',
                'bin', 'safetensors', 'gguf', 'onnx', 'pt', 'pth', 'ckpt', 'npz',
                'png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'avif',
                'mp3', 'ogg', 'wav', 'm4a', 'flac',
            ],
            'plugin' => ['js', 'mjs', 'json', 'zip', '7z', 'rar'],
        ],
        // 这些后缀一律拒收（压缩包内也不允许出现）
        'forbidden' => [
            'php', 'php3', 'php4', 'php5', 'php7', 'phtml', 'phar', 'pht',
            'exe', 'com', 'scr', 'msi', 'bat', 'cmd', 'ps1', 'vbs', 'vbe', 'wsf', 'hta', 'jar',
            'sh', 'bash', 'zsh', 'py', 'pyc', 'rb', 'pl', 'cgi', 'lua',
            'jsp', 'jspx', 'asp', 'aspx', 'ashx', 'so', 'dll', 'dylib', 'jsx',
        ],
        'image_extensions' => ['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'avif'],
        // 压缩包内额外允许的"配套文件"（样式/说明等），黑名单优先级更高
        'archive_extra' => ['js', 'mjs', 'css', 'html', 'map', 'txt', 'md', 'ini', 'cfg', 'yaml', 'yml', 'csv', 'xml'],
    ],
];

$localFile = __DIR__ . '/config.local.php';
if (is_file($localFile)) {
    $local = require $localFile;
    if (is_array($local)) {
        $config = array_replace_recursive($config, $local);
    }
}

// 环境变量最后覆盖，部署时改环境变量就能生效（空值也算显式设置）
$environment = [
    'UGC_DB_HOST' => ['db', 'host', 'text'],
    'UGC_DB_PORT' => ['db', 'port', 'int'],
    'UGC_DB_NAME' => ['db', 'database', 'text'],
    'UGC_DB_USER' => ['db', 'username', 'text'],
    'UGC_DB_PASS' => ['db', 'password', 'text'],
    'UGC_DEBUG' => ['app', 'debug', 'bool'],
];
foreach ($environment as $name => [$section, $key, $kind]) {
    $value = getenv($name);
    if ($value === false || ($value === '' && $name !== 'UGC_DB_PASS')) {
        continue;
    }
    $config[$section][$key] = match ($kind) {
        'int' => (int) $value,
        'bool' => filter_var($value, FILTER_VALIDATE_BOOL),
        default => $value,
    };
}

return $config;
