<?php

declare(strict_types=1);

// 生成一个结构合法的 Live2D 测试包，给手工联调或客户端兼容性测试用。
// 用法：php tests/make-fixture.php [输出路径]

require __DIR__ . '/lib/ZipBuilder.php';

$target = $argv[1] ?? (dirname(__DIR__) . '/storage/tmp/fixture-live2d.zip');
$directory = dirname($target);
if (!is_dir($directory)) {
    mkdir($directory, 0755, true);
}
file_put_contents($target, UGCTest\ZipBuilder::live2dPackage('ClientModel'));
echo $target . PHP_EOL;
