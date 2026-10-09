<?php

declare(strict_types=1);

// 端到端验收：真 MySQL + php -S，覆盖上传/下载/限流/权限/危险文件。
// 用法：php tests/api-test.php

use UGCTest\Harness;
use UGCTest\Http;
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
require $root . '/tests/lib/Http.php';
require $root . '/tests/lib/ZipBuilder.php';

$config = require $root . '/src/config.php';
$settings = (array) $config['db'];
$harness = new Harness($root, getenv('UGC_TEST_DB') ?: ($settings['database'] . '_test'), $settings);

$pdo = null;
$http = null;

try {
    $harness->resetDatabase();
    $pdo = $harness->pdo();
    $harness->startServer();
    $http = new Http($harness->baseUrl());

    // 账号
    $harness->section('1) 健康检查与账号');
    $health = $http->request('GET', '/api/health');
    $harness->check('GET /api/health', $health['status'] === 200 && ($health['json']['ok'] ?? false) === true);
    $harness->check('health 回显并发上限', (int) ($health['json']['limits']['anonymous']['concurrency'] ?? 0) > 0);

    $anonymous = $http->request('GET', '/api/auth/me');
    $harness->check('匿名 me：user=null', $anonymous['status'] === 200 && $anonymous['json']['user'] === null);

    $register = $http->request('POST', '/api/auth/register', ['username' => 'alice', 'password' => 'AlicePass123']);
    $harness->check('注册返回 token 与用户', $register['status'] === 201 && strlen((string) $register['json']['token']) > 20);
    $token = (string) $register['json']['token'];
    $auth = ['Authorization' => 'Bearer ' . $token];
    $harness->check('第一个注册的人是管理员', ($register['json']['user']['role'] ?? '') === 'admin');

    $stored = (string) $pdo->query("SELECT api_token_hash FROM users WHERE username = 'alice'")->fetchColumn();
    $harness->check('库里只存 token 的 sha256', $stored === hash('sha256', $token) && $stored !== $token);

    $harness->check('重复用户名被拒', $http->request('POST', '/api/auth/register', ['username' => 'alice', 'password' => 'AlicePass123'])['status'] === 409);
    $harness->check('弱密码被拒', $http->request('POST', '/api/auth/register', ['username' => 'weakone', 'password' => '123456'])['status'] === 422);
    $harness->check('错密码登录被拒', $http->request('POST', '/api/auth/login', ['username' => 'alice', 'password' => 'nope-nope'])['status'] === 401);
    $login = $http->request('POST', '/api/auth/login', ['username' => 'alice', 'password' => 'AlicePass123']);
    $harness->check('登录换新 token', $login['status'] === 200 && strlen((string) $login['json']['token']) > 20);
    // 登录会换发新 token，后面的请求都用新的
    $token = (string) $login['json']['token'];
    $auth = ['Authorization' => 'Bearer ' . $token];
    $harness->check('无效 token 得到 401 bad_token', $http->request('GET', '/api/auth/me', null, ['Authorization' => 'Bearer ' . str_repeat('x', 43)])['status'] === 401);
    $harness->check('未登录不能上传', $http->request('POST', '/api/uploads', ['size' => 10, 'sha256' => str_repeat('a', 64), 'name' => 'x.zip'])['status'] === 401);

    // 上传：三步分片
    $harness->section('2) 三步分片上传');
    $zip = ZipBuilder::live2dPackage('Hiyori');
    $size = strlen($zip);
    $open = $http->request('POST', '/api/uploads', [
        'size' => $size,
        'sha256' => hash('sha256', $zip),
        'name' => 'hiyori.zip',
        'kind' => 'live2d',
    ], $auth);
    $harness->check('开会话', $open['status'] === 201 && isset($open['json']['upload_id']), 'HTTP ' . $open['status']);
    $uploadId = (string) $open['json']['upload_id'];

    $half = intdiv($size, 2);
    $first = $http->request('POST', '/api/uploads/' . $uploadId . '/chunk', null, $auth + [
        'Content-Range' => sprintf('bytes 0-%d/%d', $half - 1, $size),
    ], substr($zip, 0, $half));
    $harness->check('第一段写入', $first['status'] === 200 && (int) $first['json']['offset'] === $half);

    $outOfOrder = $http->request('POST', '/api/uploads/' . $uploadId . '/chunk', null, $auth + [
        'Content-Range' => sprintf('bytes %d-%d/%d', $half + 5, $size - 1, $size),
    ], substr($zip, $half + 5));
    $harness->check('乱序分片回 308 + 真实 offset', $outOfOrder['status'] === 308 && (int) $outOfOrder['json']['offset'] === $half);

    $second = $http->request('POST', '/api/uploads/' . $uploadId . '/chunk', null, $auth + [
        'Content-Range' => sprintf('bytes %d-%d/%d', $half, $size - 1, $size),
    ], substr($zip, $half));
    $harness->check('补齐后 offset 到尾部', (int) $second['json']['offset'] === $size);

    $complete = $http->request('POST', '/api/uploads/' . $uploadId . '/complete', [
        'name' => '日和（改）',
        'kind' => 'live2d',
        'description' => '第一行 <script>alert(1)</script>',
        'tags' => 'live2d,可爱',
        'license' => 'CC-BY',
    ], $auth);
    $harness->check('提交生成 item', $complete['status'] === 201 && isset($complete['json']['item']['id']), 'HTTP ' . $complete['status'] . ' ' . json_encode($complete['json'], JSON_UNESCAPED_UNICODE));
    $item = (array) $complete['json']['item'];
    $itemId = (string) $item['id'];
    $harness->check('识别为 live2d 且给出入口', ($item['kind'] ?? '') === 'live2d' && str_ends_with((string) $item['meta']['entry'], '.model3.json'), (string) $item['meta']['entry']);
    $harness->check('回显 sha256 与大小', ($item['sha256'] ?? '') === hash('sha256', $zip) && (int) $item['size'] === $size);

    $row = $pdo->query('SELECT * FROM resources WHERE id = ' . (int) $itemId)->fetch();
    $storedPath = $root . '/storage/uploads/' . (string) $row['file_path'];
    $harness->check('落在 storage/uploads 下且改了名', str_starts_with((string) $row['file_path'], 'model/') && basename((string) $row['file_path']) !== 'hiyori.zip', (string) $row['file_path']);
    $harness->check('磁盘文件大小一致', is_file($storedPath) && filesize($storedPath) === $size);
    $harness->check('上传目录禁止执行（.htaccess）', is_file($root . '/storage/uploads/.htaccess'));

    $duplicate = $http->request('POST', '/api/uploads', ['size' => $size, 'sha256' => hash('sha256', $zip), 'name' => 'hiyori.zip'], $auth);
    $secondId = (string) $duplicate['json']['upload_id'];
    $http->request('POST', '/api/uploads/' . $secondId . '/chunk', null, $auth + ['Content-Range' => sprintf('bytes 0-%d/%d', $size - 1, $size)], $zip);
    $again = $http->request('POST', '/api/uploads/' . $secondId . '/complete', ['name' => 'hiyori.zip', 'kind' => 'live2d'], $auth);
    $harness->check('同一份文件重复上传不新建条目', $again['status'] === 200 && ($again['json']['duplicate'] ?? false) === true && (string) $again['json']['item']['id'] === $itemId);

    $pluginBody = "module.exports = { on_load(api) {} };\n";
    $plugin = $http->request('POST', '/api/uploads', [
        'size' => strlen($pluginBody),
        'sha256' => hash('sha256', $pluginBody),
        'name' => 'hello.js',
        'kind' => 'plugin',
    ], $auth);
    $pluginId = (string) $plugin['json']['upload_id'];
    $http->request('POST', '/api/uploads/' . $pluginId . '/chunk', null, $auth + ['Content-Range' => sprintf('bytes 0-%d/%d', strlen($pluginBody) - 1, strlen($pluginBody))], $pluginBody);
    $pluginDone = $http->request('POST', '/api/uploads/' . $pluginId . '/complete', ['name' => 'hello.js', 'kind' => 'plugin'], $auth);
    $harness->check('插件上传成功且 type=plugin', ($pluginDone['json']['item']['type'] ?? '') === 'plugin', json_encode($pluginDone['json'], JSON_UNESCAPED_UNICODE));
    $pluginItemId = (string) ($pluginDone['json']['item']['id'] ?? '0');

    // 危险文件
    $harness->section('3) 危险文件一律拒收');
    $cases = ['evil.php' => ['<?php echo 1;', 415], 'evil.jsp' => ['<% out.print(1); %>', 415], 'evil.exe' => ["MZ\x90\x00", 415], 'evil.sh' => ["#!/bin/sh\n", 415], 'evil.php.zip' => ['PK', 415]];
    foreach ($cases as $name => [$content, $expected]) {
        $opened = $http->request('POST', '/api/uploads', ['size' => strlen($content), 'sha256' => hash('sha256', $content), 'name' => $name], $auth);
        $harness->check('拒绝 ' . $name, $opened['status'] === $expected, 'HTTP ' . $opened['status']);
    }
    foreach (['含 PHP 的 zip' => ZipBuilder::packageWithPhp(), '路径穿越 zip' => ZipBuilder::packageWithTraversal(), '假 zip' => 'not a zip at all'] as $label => $content) {
        $opened = $http->request('POST', '/api/uploads', ['size' => strlen($content), 'sha256' => hash('sha256', $content), 'name' => 'bundle.zip'], $auth);
        if ($opened['status'] !== 201) {
            $harness->check('拒绝 ' . $label, true, 'HTTP ' . $opened['status']);
            continue;
        }
        $id = (string) $opened['json']['upload_id'];
        $http->request('POST', '/api/uploads/' . $id . '/chunk', null, $auth + ['Content-Range' => sprintf('bytes 0-%d/%d', strlen($content) - 1, strlen($content))], $content);
        $done = $http->request('POST', '/api/uploads/' . $id . '/complete', ['name' => 'bundle.zip'], $auth);
        $harness->check('拒绝 ' . $label, in_array($done['status'], [400, 415, 422], true), 'HTTP ' . $done['status'] . ' ' . ($done['json']['error']['message'] ?? ''));
    }
    $files = array_filter(glob($root . '/storage/uploads/*/*/*') ?: [], static fn (string $file): bool => basename($file) !== '.htaccess');
    $harness->check('危险文件没有落盘', count($files) === 2, count($files) . ' 个文件');

    // 列表与详情
    $harness->section('4) 列表与详情');
    $list = $http->request('GET', '/api/items');
    $harness->check('匿名列表可用', $list['status'] === 200 && (int) $list['json']['total'] === 2);
    $harness->check('按 kind 过滤', (int) $http->request('GET', '/api/items?kind=live2d')['json']['total'] === 1);
    $harness->check('关键词搜索', (int) $http->request('GET', '/api/items?q=' . rawurlencode('日和'))['json']['total'] === 1);
    $detail = $http->request('GET', '/api/items/' . $itemId);
    $harness->check('详情字段齐全', $detail['status'] === 200 && ($detail['json']['item']['author']['username'] ?? '') === 'alice');
    $harness->check('详情不含物理路径', !str_contains($detail['body'], 'storage/uploads') && !str_contains($detail['body'], $root));
    $harness->check('不存在的资源 404', $http->request('GET', '/api/items/999999')['status'] === 404);
    $harness->check('穿越形式的 id 404', in_array($http->request('GET', '/api/items/..%2f..%2fetc%2fpasswd')['status'], [404, 400], true));
    $harness->check('注入字符串不炸', $http->request('GET', '/api/items?q=' . rawurlencode("' OR 1=1 -- "))['status'] === 200);

    // 下载与限流
    $harness->section('5) 下载与未登录限流');
    $anonymousHttp = new Http($harness->baseUrl());
    $head = $anonymousHttp->request('HEAD', '/api/items/' . $itemId . '/download');
    $harness->check('HEAD 给出长度/摘要/并发上限', (int) $head['headers']['content-length'] === $size && ($head['headers']['x-item-sha256'] ?? '') === hash('sha256', $zip) && (int) ($head['headers']['x-concurrency-limit'] ?? 0) > 0);
    $harness->check('HEAD 不计数', (int) $pdo->query('SELECT download_count FROM resources WHERE id = ' . (int) $itemId)->fetchColumn() === 0);

    for ($i = 1; $i <= 5; $i++) {
        $download = $anonymousHttp->request('GET', '/api/items/' . $itemId . '/download');
        if ($download['status'] !== 200) {
            break;
        }
    }
    $harness->check('匿名前 5 次下载模型成功', $download['status'] === 200 && strlen($download['body']) === $size, 'HTTP ' . $download['status']);
    $limited = $anonymousHttp->request('GET', '/api/items/' . $itemId . '/download');
    $harness->check('第 6 次 429', $limited['status'] === 429, 'HTTP ' . $limited['status']);
    $harness->check('429 文案与 Retry-After', ($limited['json']['error']['message'] ?? '') === '未登录用户模型下载已达每小时 5 次限制' && isset($limited['headers']['retry-after']), (string) ($limited['json']['error']['message'] ?? ''));

    for ($i = 0; $i < 8; $i++) {
        $pluginDownload = $anonymousHttp->request('GET', '/api/items/' . $pluginItemId . '/download');
        if ($pluginDownload['status'] !== 200) {
            break;
        }
    }
    $harness->check('插件对匿名不限流（连下 8 次）', $pluginDownload['status'] === 200);
    $harness->check('下载次数已累计', (int) $pdo->query('SELECT download_count FROM resources WHERE id = ' . (int) $itemId)->fetchColumn() === 5);
    $harness->check('限流流水已记录', (int) $pdo->query('SELECT COUNT(*) FROM download_limits')->fetchColumn() === 13);

    for ($i = 0; $i < 6; $i++) {
        $mineDownload = $http->request('GET', '/api/items/' . $itemId . '/download', null, $auth);
        if ($mineDownload['status'] !== 200) {
            break;
        }
    }
    $harness->check('登录用户下载模型不限流（连下 6 次）', $mineDownload['status'] === 200 && strlen($mineDownload['body']) === $size);

    $range = $http->request('GET', '/api/items/' . $itemId . '/download', null, $auth + ['Range' => 'bytes=0-1023']);
    $harness->check('Range 请求 206 + Content-Range', $range['status'] === 206 && ($range['headers']['content-range'] ?? '') === sprintf('bytes 0-1023/%d', $size) && strlen($range['body']) === 1024);
    $part = $http->request('GET', '/api/items/' . $itemId . '/download?part=1', null, $auth);
    $harness->check('part 模式可用', in_array($part['status'], [200, 206], true) && strlen($part['body']) === (int) ($part['headers']['x-part-size'] ?? -1));
    $harness->check('越界分片 404', $http->request('GET', '/api/items/' . $itemId . '/download?part=99', null, $auth)['status'] === 404);

    // 权限
    $harness->section('6) 权限：只能管理自己的，管理员能下架');
    $bob = new Http($harness->baseUrl());
    $bobRegister = $bob->request('POST', '/api/auth/register', ['username' => 'bob', 'password' => 'BobPass1234']);
    $harness->check('第二个用户注册成功', $bobRegister['status'] === 201 && ($bobRegister['json']['user']['role'] ?? '') === 'user', 'HTTP ' . $bobRegister['status'] . ' ' . json_encode($bobRegister['json'], JSON_UNESCAPED_UNICODE));
    $bobAuth = ['Authorization' => 'Bearer ' . (string) $bobRegister['json']['token']];

    $stealDelete = $bob->request('DELETE', '/api/items/' . $itemId, null, $bobAuth);
    $harness->check('别人不能删我的资源', $stealDelete['status'] === 403, 'HTTP ' . $stealDelete['status'] . ' ' . $stealDelete['body']);
    $stealStatus = $bob->request('POST', '/api/items/' . $itemId . '/status', ['status' => 'hidden'], $bobAuth);
    $harness->check('别人不能改我的状态', $stealStatus['status'] === 403, 'HTTP ' . $stealStatus['status'] . ' ' . $stealStatus['body']);

    // bob 是普通用户：他自己传一条，验证"作者能下架、但不能封禁"
    $bobBody = "module.exports = { name: 'bob-plugin' };\n";
    $bobOpen = $bob->request('POST', '/api/uploads', ['size' => strlen($bobBody), 'sha256' => hash('sha256', $bobBody), 'name' => 'bob.js'], $bobAuth);
    $bobUploadId = (string) $bobOpen['json']['upload_id'];
    $bob->request('POST', '/api/uploads/' . $bobUploadId . '/chunk', null, $bobAuth + ['Content-Range' => sprintf('bytes 0-%d/%d', strlen($bobBody) - 1, strlen($bobBody))], $bobBody);
    $bobItemId = (string) $bob->request('POST', '/api/uploads/' . $bobUploadId . '/complete', ['name' => 'bob 的插件', 'kind' => 'plugin'], $bobAuth)['json']['item']['id'];

    $bobBlock = $bob->request('POST', '/api/items/' . $bobItemId . '/status', ['status' => 'blocked'], $bobAuth);
    $harness->check('普通用户不能封禁（连自己的也不行）', $bobBlock['status'] === 403, 'HTTP ' . $bobBlock['status'] . ' ' . $bobBlock['body']);
    $bobHide = $bob->request('POST', '/api/items/' . $bobItemId . '/status', ['status' => 'hidden'], $bobAuth);
    $harness->check('作者可以下架自己的资源', $bobHide['status'] === 200 && ($bobHide['json']['item']['status'] ?? '') === 'hidden', 'HTTP ' . $bobHide['status']);

    // alice 是第一个注册的用户（管理员）：能封禁别人的，也能删别人的
    $adminBlock = $http->request('POST', '/api/items/' . $bobItemId . '/status', ['status' => 'blocked'], $auth);
    $harness->check('管理员能封禁别人的资源', $adminBlock['status'] === 200 && ($adminBlock['json']['item']['status'] ?? '') === 'blocked', 'HTTP ' . $adminBlock['status'] . ' ' . $adminBlock['body']);
    $adminDelete = $http->request('DELETE', '/api/items/' . $bobItemId, null, $auth);
    $harness->check('管理员能删别人的资源', $adminDelete['status'] === 204, 'HTTP ' . $adminDelete['status']);

    $hide = $http->request('POST', '/api/items/' . $itemId . '/status', ['status' => 'hidden'], $auth);
    $harness->check('下架自己的资源', $hide['status'] === 200 && ($hide['json']['item']['status'] ?? '') === 'hidden', 'HTTP ' . $hide['status'] . ' ' . $hide['body']);
    $hiddenView = $anonymousHttp->request('GET', '/api/items/' . $itemId);
    $harness->check('下架后匿名看不到', $hiddenView['status'] === 403, 'HTTP ' . $hiddenView['status']);
    $harness->check('作者自己仍能看到', $http->request('GET', '/api/items/' . $itemId, null, $auth)['status'] === 200);
    $adminHide = $http->request('POST', '/api/items/' . $itemId . '/status', ['status' => 'published'], $auth);
    $harness->check('重新上架', ($adminHide['json']['item']['status'] ?? '') === 'published', 'HTTP ' . $adminHide['status'] . ' ' . $adminHide['body']);

    // 收尾
    $harness->section('7) 删除与清理');
    $pluginFile = $root . '/storage/' . (string) $pdo->query('SELECT file_path FROM resources WHERE id = ' . (int) $pluginItemId)->fetchColumn();
    $delete = $http->request('DELETE', '/api/items/' . $pluginItemId, null, $auth);
    $harness->check('作者删除资源 204', $delete['status'] === 204, 'HTTP ' . $delete['status'] . ' ' . $delete['body']);
    clearstatcache(true, $pluginFile);
    $harness->check('物理文件一起删掉', !is_file($pluginFile), $pluginFile);
    $harness->check('重复删除 404', $http->request('DELETE', '/api/items/' . $pluginItemId, null, $auth)['status'] === 404);
    $harness->check('登出后 token 失效', $http->request('POST', '/api/auth/logout', null, $auth)['status'] === 200 && $http->request('GET', '/api/auth/me', null, $auth)['status'] === 401);
} catch (Throwable $throwable) {
    printf("\n测试中断：%s @ %s:%d\n", $throwable->getMessage(), $throwable->getFile(), $throwable->getLine());
    $harness->failed++;
    $harness->failures[] = '测试中断：' . $throwable->getMessage();
} finally {
    $harness->stopServer();
}

exit($harness->summary());
