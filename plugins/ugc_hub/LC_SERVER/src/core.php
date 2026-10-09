<?php

declare(strict_types=1);

// 公共底座：配置、数据库、JSON 应答、请求取值、日志。

function ugc_config(?string $path = null, mixed $default = null): mixed
{
    static $config = null;
    if ($config === null) {
        $config = require __DIR__ . '/config.php';
    }
    if ($path === null) {
        return $config;
    }
    $value = $config;
    foreach (explode('.', $path) as $key) {
        if (!is_array($value) || !array_key_exists($key, $value)) {
            return $default;
        }
        $value = $value[$key];
    }
    return $value;
}

function ugc_db(): PDO
{
    static $pdo = null;
    if ($pdo instanceof PDO) {
        return $pdo;
    }

    $dsn = sprintf(
        'mysql:host=%s;port=%d;dbname=%s;charset=utf8mb4',
        (string) ugc_config('db.host'),
        (int) ugc_config('db.port'),
        (string) ugc_config('db.database')
    );

    try {
        $pdo = new PDO($dsn, (string) ugc_config('db.username'), (string) ugc_config('db.password'), [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_EMULATE_PREPARES => false,
        ]);
    } catch (PDOException $exception) {
        ugc_log('数据库连接失败', ['dsn' => $dsn, 'error' => $exception->getMessage()]);
        ugc_error(500, 'db_unavailable', '数据库暂时不可用，请稍后再试');
    }

    return $pdo;
}

/** @param array<string, mixed> $params */
function ugc_query(string $sql, array $params = []): PDOStatement
{
    try {
        $statement = ugc_db()->prepare($sql);
        $statement->execute($params);
        return $statement;
    } catch (PDOException $exception) {
        ugc_log('SQL 执行失败', ['error' => $exception->getMessage(), 'sql' => $sql]);
        ugc_error(500, 'db_error', '数据处理失败，请稍后再试');
    }
}

/** @param array<string, mixed> $params @return array<string, mixed>|null */
function ugc_one(string $sql, array $params = []): ?array
{
    $row = ugc_query($sql, $params)->fetch();
    return is_array($row) ? $row : null;
}

/** @param array<string, mixed> $params @return array<int, array<string, mixed>> */
function ugc_all(string $sql, array $params = []): array
{
    return ugc_query($sql, $params)->fetchAll();
}

/** @param array<string, mixed> $params */
function ugc_exec(string $sql, array $params = []): int
{
    return ugc_query($sql, $params)->rowCount();
}

/** @param array<string, mixed> $payload */
function ugc_send(array $payload, int $status = 200): never
{
    if (!headers_sent()) {
        http_response_code($status);
        header('Content-Type: application/json; charset=utf-8');
        header('Cache-Control: no-store');
        header('X-Content-Type-Options: nosniff');
    }
    echo json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}

/** @param array<string, mixed> $extra */
function ugc_error(int $status, string $code, string $message, array $extra = []): never
{
    if (!headers_sent()) {
        http_response_code($status);
    }
    ugc_send(['error' => array_merge(['code' => $code, 'message' => $message], $extra)], $status);
}

function ugc_log(string $message, array $context = []): void
{
    $directory = (string) ugc_config('storage.logs');
    if (!is_dir($directory)) {
        @mkdir($directory, 0755, true);
    }
    $line = sprintf(
        "[%s] %s%s\n",
        gmdate('Y-m-d H:i:s'),
        $message,
        $context === [] ? '' : ' ' . json_encode($context, JSON_UNESCAPED_UNICODE)
    );
    @file_put_contents($directory . '/app-' . gmdate('Y-m-d') . '.log', $line, FILE_APPEND | LOCK_EX);
}

/** @return array<string, mixed> */
function ugc_body(): array
{
    static $body = null;
    if ($body !== null) {
        return $body;
    }
    $raw = file_get_contents('php://input');
    if ($raw === false || trim($raw) === '') {
        return $body = [];
    }
    $decoded = json_decode($raw, true);
    if (!is_array($decoded)) {
        ugc_error(400, 'bad_field', '请求体不是合法 JSON');
    }
    return $body = $decoded;
}

function ugc_param(string $key, mixed $default = null): mixed
{
    $body = ugc_body();
    if (array_key_exists($key, $body)) {
        return $body[$key];
    }
    return $_GET[$key] ?? $default;
}

function ugc_text(mixed $value, int $maxLength = 255): string
{
    $text = is_scalar($value) ? trim((string) $value) : '';
    $text = str_replace(["\0", "\r"], '', $text);
    return mb_substr($text, 0, $maxLength);
}

function ugc_int(mixed $value, int $default = 0): int
{
    return is_numeric($value) ? (int) $value : $default;
}

function ugc_hex(int $bytes): string
{
    return bin2hex(random_bytes($bytes));
}

function ugc_now(): string
{
    return gmdate('Y-m-d H:i:s');
}

function ugc_iso(string $sqlTime): string
{
    $timestamp = strtotime($sqlTime . ' UTC');
    return gmdate('Y-m-d\TH:i:s\Z', $timestamp === false ? time() : $timestamp);
}

/** 只在配置了可信代理时才认 X-Forwarded-For，否则一律用 REMOTE_ADDR。 */
function ugc_ip(): string
{
    $ip = (string) ($_SERVER['REMOTE_ADDR'] ?? '0.0.0.0');
    return mb_substr($ip, 0, 45);
}

function ugc_method(): string
{
    return strtoupper((string) ($_SERVER['REQUEST_METHOD'] ?? 'GET'));
}

function ugc_path(): string
{
    $path = parse_url((string) ($_SERVER['REQUEST_URI'] ?? '/'), PHP_URL_PATH) ?: '/';
    return '/' . ltrim(preg_replace('#/+#', '/', $path) ?? '/', '/');
}

function ugc_require_method(string ...$methods): void
{
    if (!in_array(ugc_method(), $methods, true)) {
        if (!headers_sent()) {
            header('Allow: ' . implode(', ', $methods));
        }
        ugc_error(405, 'bad_method', '请求方法不被允许');
    }
}
