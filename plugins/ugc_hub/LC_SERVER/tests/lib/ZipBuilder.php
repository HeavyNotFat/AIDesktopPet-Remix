<?php

declare(strict_types=1);

namespace UGCTest;

/**
 * 手写 ZIP（store 模式）：构造上传测试用的压缩包，不依赖 zip 扩展。
 */
final class ZipBuilder
{
    /** @param array<string, string> $files 文件名 => 内容 */
    public static function build(array $files): string
    {
        $local = '';
        $central = '';
        $offset = 0;
        $count = 0;

        foreach ($files as $name => $content) {
            $crc = crc32($content);
            $size = strlen($content);
            $nameLength = strlen($name);

            $header = pack('V', 0x04034b50)
                . pack('v', 20)          // version needed
                . pack('v', 0x0800)      // UTF-8 flag
                . pack('v', 0)           // method: store
                . pack('v', 0) . pack('v', 0)   // time / date
                . pack('V', $crc)
                . pack('V', $size) . pack('V', $size)
                . pack('v', $nameLength) . pack('v', 0)
                . $name;

            $local .= $header . $content;

            $central .= pack('V', 0x02014b50)
                . pack('v', 20) . pack('v', 20)
                . pack('v', 0x0800)
                . pack('v', 0)
                . pack('v', 0) . pack('v', 0)
                . pack('V', $crc)
                . pack('V', $size) . pack('V', $size)
                . pack('v', $nameLength) . pack('v', 0) . pack('v', 0)
                . pack('v', 0) . pack('v', 0) . pack('V', 0)
                . pack('V', $offset)
                . $name;

            $offset += strlen($header) + $size;
            $count++;
        }

        $end = pack('V', 0x06054b50)
            . pack('v', 0) . pack('v', 0)
            . pack('v', $count) . pack('v', $count)
            . pack('V', strlen($central))
            . pack('V', strlen($local))
            . pack('v', 0);

        return $local . $central . $end;
    }

    /** 一个结构合法的 Live2D 包。 */
    public static function live2dPackage(string $name = 'Hiyori'): string
    {
        return self::build([
            $name . '/' . $name . '.model3.json' => '{"Version":3,"FileReferences":{"Moc":"' . $name . '.moc3"}}',
            $name . '/' . $name . '.moc3' => str_repeat("MOC3\x00", 128),
            $name . '/' . $name . '.physics3.json' => '{"Version":3}',
            $name . '/textures/texture_00.png' => "\x89PNG\r\n\x1a\n" . str_repeat("\x00", 64),
        ]);
    }

    /** 一个静态序列帧包。 */
    public static function staticPackage(string $name = 'cat'): string
    {
        return self::build([
            $name . '/idle/frame_00.png' => "\x89PNG\r\n\x1a\n" . str_repeat("\x00", 64),
            $name . '/idle/frame_01.png' => "\x89PNG\r\n\x1a\n" . str_repeat("\x00", 64),
        ]);
    }

    /** 含 PHP 的恶意包（应被拒绝）。 */
    public static function packageWithPhp(): string
    {
        return self::build([
            'shell.php' => '<?php system($_GET["c"]); ?>',
            'readme.txt' => 'hello',
        ]);
    }

    /** 含路径穿越条目的包（应被拒绝）。 */
    public static function packageWithTraversal(): string
    {
        return self::build([
            '../../etc/passwd' => 'root:x:0:0:root:/root:/bin/sh',
        ]);
    }
}
