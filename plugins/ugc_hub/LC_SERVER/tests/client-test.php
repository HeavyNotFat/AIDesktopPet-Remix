<?php

declare(strict_types=1);

// 用真实桌面插件客户端（ugc_hub 的 client.js）跑一遍本站：健康检查→注册→三步上传→列表→多线程下载。
// 需要 node 与 client.js，缺哪个就跳过。用法：php tests/client-test.php
// 环境变量：UGC_CLIENT_PATH 指定 client.js 路径，ADP_NODE 指定 node 可执行文件。

use UGCTest\Harness;
use UGCTest\ZipBuilder;

if (!extension_loaded('pdo_mysql')) {
    $process = proc_open([
        PHP_BINARY,
        '-d', 'extension_dir=' . ini_get('extension_dir'),
        '-d', 'extension=pdo_mysql',
        __FILE__,
    ], [0 => STDIN, 1 => STDOUT, 2 => STDERR], $pipes);
    exit(is_resource($process) ? proc_close($process) : 1);
}

$root = dirname(__DIR__);
require $root . '/tests/lib/Harness.php';
require $root . '/tests/lib/ZipBuilder.php';

$config = require $root . '/src/config.php';
$settings = (array) $config['db'];
$harness = new Harness($root, getenv('UGC_TEST_DB') ?: ($settings['database'] . '_test'), $settings);

$node = trim((string) (getenv('ADP_NODE') ?: (shell_exec('where node 2>NUL') ?: '')));
$node = $node === '' ? '' : trim(explode("\n", str_replace("\r", "", $node))[0]);
$clientPath = (string) (getenv('UGC_CLIENT_PATH')
    ?: 'D:\Desktop\PyCharmProjects\Projects\ADPRemix\.tmp\e2e\plugins\ugc_hub\client.js');

if ($node === '' || !is_file($clientPath)) {
    printf("跳过：%s\n", $node === '' ? '没找到 node' : '没找到 client.js（' . $clientPath . '）');
    exit(0);
}

// 客户端下载走匿名通道，所以先把限流流水清空，保证额度是满的
$harness->resetDatabase();
$harness->pdo()->exec('DELETE FROM download_limits');
$harness->startServer();

$fixture = $root . '/storage/tmp/fixture-live2d.zip';
file_put_contents($fixture, ZipBuilder::live2dPackage('ClientModel'));

$command = sprintf(
    '%s %s',
    escapeshellarg($node),
    escapeshellarg($root . '/tests/client-e2e.js')
);
$environment = [
    'UGC_BASE_URL' => $harness->baseUrl(),
    'UGC_CLIENT_PATH' => $clientPath,
    'UGC_FIXTURE_ZIP' => $fixture,
];

if (stripos(PHP_OS_FAMILY, 'Windows') !== false) {
    $prefix = '';
    foreach ($environment as $name => $value) {
        $prefix .= sprintf('set "%s=%s" && ', $name, $value);
    }
    exec('cmd /c "' . $prefix . $command . '" 2>&1', $output, $code);
} else {
    $prefix = '';
    foreach ($environment as $name => $value) {
        $prefix .= $name . '=' . escapeshellarg($value) . ' ';
    }
    exec($prefix . $command . ' 2>&1', $output, $code);
}

foreach ($output as $line) {
    printf("  %s\n", $line);
}
$harness->stopServer();
@unlink($fixture);

exit($code === 0 ? 0 : 1);
