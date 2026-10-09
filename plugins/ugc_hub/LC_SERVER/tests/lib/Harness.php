<?php

declare(strict_types=1);

namespace UGCTest;

use PDO;
use RuntimeException;

/**
 * 测试环境：准备独立数据库、拉起 php -S、提供 HTTP 客户端与断言。
 */
final class Harness
{
    public int $passed = 0;
    public int $failed = 0;

    /** @var array<int, string> */
    public array $failures = [];

    private int $port;
    private $server = null;
    private array $pipes = [];

    public function __construct(
        private string $root,
        public readonly string $database,
        private array $dbSettings,
    ) {
        $this->port = 18080 + random_int(0, 400);
    }

    public function pdo(): PDO
    {
        $dsn = sprintf(
            'mysql:host=%s;port=%d;dbname=%s;charset=utf8mb4',
            $this->dbSettings['host'],
            (int) $this->dbSettings['port'],
            $this->database
        );
        return new PDO($dsn, (string) $this->dbSettings['username'], (string) $this->dbSettings['password'], [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        ]);
    }

    /** 删库重建 + 建表，并把上次跑测试留下的上传/临时文件清掉。 */
    public function resetDatabase(): void
    {
        $admin = new PDO(
            sprintf('mysql:host=%s;port=%d;charset=utf8mb4', $this->dbSettings['host'], (int) $this->dbSettings['port']),
            (string) $this->dbSettings['username'],
            (string) $this->dbSettings['password'],
            [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]
        );
        $quoted = '`' . str_replace('`', '', $this->database) . '`';
        $admin->exec('DROP DATABASE IF EXISTS ' . $quoted);
        $admin->exec('CREATE DATABASE ' . $quoted . ' CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci');

        $pdo = $this->pdo();
        foreach (self::statements($this->root . '/sql/schema.sql') as $statement) {
            $pdo->exec($statement);
        }

        foreach (['/storage/uploads', '/storage/tmp'] as $directory) {
            foreach (glob($this->root . $directory . '/*/*/*') ?: [] as $file) {
                @unlink($file);
            }
            foreach (glob($this->root . $directory . '/*') ?: [] as $file) {
                is_file($file) && !in_array(basename($file), ['.htaccess', 'index.html'], true) && @unlink($file);
            }
        }
    }

    /** @return array<int, string> */
    private static function statements(string $path): array
    {
        $lines = preg_split('/\R/', (string) file_get_contents($path)) ?: [];
        $clean = [];
        foreach ($lines as $line) {
            $trimmed = ltrim($line);
            if ($trimmed === '' || str_starts_with($trimmed, '--') || str_starts_with($trimmed, '#')) {
                continue;
            }
            $clean[] = $line;
        }
        $statements = [];
        foreach (explode(';', implode("\n", $clean)) as $statement) {
            if (trim($statement) !== '') {
                $statements[] = trim($statement);
            }
        }
        return $statements;
    }

    public function baseUrl(): string
    {
        return 'http://127.0.0.1:' . $this->port;
    }

    /** 命令行 PHP 可能没开 pdo_mysql，这里统一带上扩展参数。 */
    public function phpCommand(string $script): string
    {
        return escapeshellarg(PHP_BINARY)
            . ' -d ' . escapeshellarg('extension_dir=' . ini_get('extension_dir'))
            . ' -d extension=pdo_mysql '
            . escapeshellarg($script);
    }

    public function startServer(): void
    {
        if ($this->server !== null) {
            return;
        }

        $extensionDir = ini_get('extension_dir');
        $command = [
            PHP_BINARY,
            '-d', 'extension_dir=' . $extensionDir,
            '-d', 'extension=pdo_mysql',
            '-d', 'upload_max_filesize=210M',
            '-d', 'post_max_size=212M',
            '-d', 'display_errors=0',
            '-d', 'error_reporting=E_ALL',
            '-S', '127.0.0.1:' . $this->port,
            '-t', $this->root . '/public',
            $this->root . '/public/index.php',
        ];

        $env = getenv();
        $env = array_merge(is_array($env) ? $env : [], [
            'UGC_DB_HOST' => (string) $this->dbSettings['host'],
            'UGC_DB_PORT' => (string) $this->dbSettings['port'],
            'UGC_DB_NAME' => $this->database,
            'UGC_DB_USER' => (string) $this->dbSettings['username'],
            'UGC_DB_PASS' => (string) $this->dbSettings['password'],
        ]);

        $this->server = proc_open($command, [
            0 => ['pipe', 'r'],
            1 => ['file', $this->root . '/storage/logs/test-server.out.log', 'a'],
            2 => ['file', $this->root . '/storage/logs/test-server.err.log', 'a'],
        ], $this->pipes, $this->root, $env);

        if (!is_resource($this->server)) {
            throw new RuntimeException('起不了 php -S');
        }

        $deadline = microtime(true) + 15;
        while (microtime(true) < $deadline) {
            $socket = @fsockopen('127.0.0.1', $this->port, $code, $message, 0.3);
            if (is_resource($socket)) {
                fclose($socket);
                return;
            }
            usleep(120000);
        }
        throw new RuntimeException('等待测试服务器就绪超时');
    }

    public function stopServer(): void
    {
        if (!is_resource($this->server)) {
            return;
        }
        foreach ($this->pipes as $pipe) {
            if (is_resource($pipe)) {
                fclose($pipe);
            }
        }
        proc_terminate($this->server, 9);
        proc_close($this->server);
        $this->server = null;
    }

    public function check(string $name, bool $condition, string $detail = ''): void
    {
        if ($condition) {
            $this->passed++;
            printf("  ok   %s%s\n", $name, $detail === '' ? '' : ' — ' . $detail);
            return;
        }
        $this->failed++;
        $this->failures[] = $name . ($detail === '' ? '' : ' — ' . $detail);
        printf("  FAIL %s%s\n", $name, $detail === '' ? '' : ' — ' . $detail);
    }

    public function section(string $title): void
    {
        printf("\n== %s ==\n", $title);
    }

    public function summary(): int
    {
        printf("\n通过 %d 项，失败 %d 项\n", $this->passed, $this->failed);
        foreach ($this->failures as $failure) {
            printf("  - %s\n", $failure);
        }
        if ($this->failed > 0) {
            $this->dumpLogs();
        }
        return $this->failed === 0 ? 0 : 1;
    }

    /** 失败时把服务端日志尾部打出来，省得靠猜。 */
    private function dumpLogs(): void
    {
        foreach ([$this->root . '/storage/logs/test-server.err.log', $this->root . '/storage/logs/app-' . gmdate('Y-m-d') . '.log'] as $path) {
            if (!is_file($path)) {
                continue;
            }
            $lines = array_slice(file($path, FILE_IGNORE_NEW_LINES) ?: [], -12);
            if ($lines === []) {
                continue;
            }
            printf("\n--- %s（最后 %d 行）---\n", basename($path), count($lines));
            foreach ($lines as $line) {
                printf("  %s\n", mb_substr($line, 0, 400));
            }
        }
    }
}
