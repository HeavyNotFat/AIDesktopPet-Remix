<?php

declare(strict_types=1);

// 账号与 token：注册/登录/登出/me，Bearer token 鉴权（纯 token，不用 cookie 所以没有 CSRF 面）。

function ugc_token_new(): string
{
    return rtrim(strtr(base64_encode(random_bytes(32)), '+/', '-_'), '=');
}

function ugc_token_hash(string $token): string
{
    return hash('sha256', $token);
}

/** @return array<string, mixed>|null */
function ugc_current_user(): ?array
{
    static $user = null;
    static $loaded = false;
    if ($loaded) {
        return $user;
    }
    $loaded = true;

    $header = (string) ($_SERVER['HTTP_AUTHORIZATION'] ?? '');
    if (!preg_match('/^Bearer\s+([A-Za-z0-9\-_]{20,200})$/', $header, $matches)) {
        return $user = null;
    }

    $row = ugc_one(
        'SELECT * FROM users WHERE api_token_hash = :hash AND token_expires_at > :now LIMIT 1',
        ['hash' => ugc_token_hash($matches[1]), 'now' => ugc_now()]
    );
    if ($row === null || (string) $row['status'] !== 'active') {
        return $user = null;
    }
    return $user = $row;
}

/** @return array<string, mixed> */
function ugc_require_user(): array
{
    $user = ugc_current_user();
    if ($user === null) {
        ugc_error(401, 'bad_token', '登录状态已失效，请重新登录');
    }
    return $user;
}

/** @return array<string, mixed> */
function ugc_require_admin(): array
{
    $user = ugc_require_user();
    if ((string) $user['role'] !== 'admin') {
        ugc_error(403, 'forbidden', '需要管理员权限');
    }
    return $user;
}

/** @return array<string, mixed> */
function ugc_user_shape(array $row): array
{
    return [
        'id' => (string) $row['id'],
        'username' => (string) $row['username'],
        'role' => (string) $row['role'],
    ];
}

function ugc_password_problem(string $password): ?string
{
    $length = strlen($password);
    if ($length < 8 || $length > 72) {
        return '密码长度要在 8–72 个字符之间';
    }
    $kinds = 0;
    foreach (['/[a-z]/', '/[A-Z]/', '/[0-9]/', '/[^A-Za-z0-9]/'] as $pattern) {
        if (preg_match($pattern, $password)) {
            $kinds++;
        }
    }
    if ($kinds < 2) {
        return '密码要包含大小写字母、数字、符号中的至少两类';
    }
    return null;
}

function ugc_username_problem(string $username): ?string
{
    if (!preg_match('/^[A-Za-z0-9][A-Za-z0-9_.\-]{2,31}$/', $username)) {
        return '用户名 3–32 位，只能用字母、数字、下划线、点和横线，且以字母或数字开头';
    }
    if (in_array(strtolower($username), ['admin', 'root', 'system', 'ugc', 'administrator'], true)) {
        return '这个用户名被保留了，换一个';
    }
    return null;
}

/** 登录防爆破：按 IP + 用户名记失败次数，锁定时间指数退避，状态存在 storage/tmp 下。 */
function ugc_login_throttle(string $ip, string $username): void
{
    $state = ugc_throttle_state($ip, $username);
    if ($state['locked_until'] > time()) {
        ugc_error(429, 'rate_limited', '尝试过于频繁，请稍后再试', ['retry_after' => $state['locked_until'] - time()]);
    }
}

function ugc_login_failed(string $ip, string $username): void
{
    $path = ugc_throttle_path($ip, $username);
    $state = ugc_throttle_state($ip, $username);
    $max = (int) ugc_config('limits.login_max_failures', 5);
    $base = (int) ugc_config('limits.login_lock_seconds', 900);
    $state['failures'] = $state['failures'] + 1;
    if ($state['failures'] >= $max) {
        $rounds = $state['failures'] - $max;
        $state['locked_until'] = time() + min($base * (2 ** $rounds), 86400);
    }
    @file_put_contents($path, (string) json_encode($state), LOCK_EX);
}

function ugc_login_ok(string $ip, string $username): void
{
    @unlink(ugc_throttle_path($ip, $username));
}

function ugc_throttle_path(string $ip, string $username): string
{
    $tmp = (string) ugc_config('storage.tmp');
    if (!is_dir($tmp)) {
        @mkdir($tmp, 0755, true);
    }
    return sprintf('%s/login-%s.json', $tmp, hash('sha256', $ip . '|' . strtolower($username)));
}

/** @return array{failures: int, locked_until: int} */
function ugc_throttle_state(string $ip, string $username): array
{
    $path = ugc_throttle_path($ip, $username);
    $state = is_file($path) ? json_decode((string) file_get_contents($path), true) : null;
    if (!is_array($state) || ($state['updated_at'] ?? 0) < time() - 86400) {
        $state = [];
    }
    return [
        'failures' => (int) ($state['failures'] ?? 0),
        'locked_until' => (int) ($state['locked_until'] ?? 0),
        'updated_at' => time(),
    ];
}

/** @return array<string, mixed> */
function ugc_issue_token(array $user): array
{
    $token = ugc_token_new();
    $ttl = 30 * 86400;
    ugc_exec(
        'UPDATE users SET api_token_hash = :hash, token_expires_at = :expires, last_login_at = :login_at, updated_at = :updated_at WHERE id = :id',
        [
            'hash' => ugc_token_hash($token),
            'expires' => gmdate('Y-m-d H:i:s', time() + $ttl),
            'login_at' => ugc_now(),
            'updated_at' => ugc_now(),
            'id' => (int) $user['id'],
        ]
    );
    return ['token' => $token, 'expires_at' => gmdate('Y-m-d\TH:i:s\Z', time() + $ttl), 'user' => ugc_user_shape($user)];
}

function ugc_auth_register(): never
{
    ugc_require_method('POST');
    $username = ugc_text(ugc_param('username', ugc_param('name')), 32);
    $password = (string) ugc_param('password', '');
    $email = ugc_text(ugc_param('email'), 120);

    if (($problem = ugc_username_problem($username)) !== null) {
        ugc_error(422, 'bad_field', $problem, ['field' => 'username']);
    }
    if (($problem = ugc_password_problem($password)) !== null) {
        ugc_error(422, 'bad_field', $problem, ['field' => 'password']);
    }
    if ($email !== '' && !filter_var($email, FILTER_VALIDATE_EMAIL)) {
        ugc_error(422, 'bad_field', '邮箱格式不对', ['field' => 'email']);
    }
    if (ugc_one('SELECT id FROM users WHERE username = :username', ['username' => $username]) !== null) {
        ugc_error(409, 'username_taken', '这个用户名已经被用了');
    }
    if ($email !== '' && ugc_one('SELECT id FROM users WHERE email = :email', ['email' => $email]) !== null) {
        ugc_error(409, 'email_taken', '这个邮箱已经注册过了');
    }

    // 第一个注册的人自动成为管理员，省得再单独建号
    $count = (int) (ugc_one('SELECT COUNT(*) AS total FROM users')['total'] ?? 0);
    $role = $count === 0 ? 'admin' : 'user';

    ugc_exec(
        'INSERT INTO users (username, email, password_hash, role, status, created_at, updated_at)
         VALUES (:username, :email, :hash, :role, :status, :created_at, :updated_at)',
        [
            'username' => $username,
            'email' => $email,
            'hash' => password_hash($password, PASSWORD_BCRYPT, ['cost' => 12]),
            'role' => $role,
            'status' => 'active',
            'created_at' => ugc_now(),
            'updated_at' => ugc_now(),
        ]
    );
    $user = ugc_one('SELECT * FROM users WHERE id = :id', ['id' => (int) ugc_db()->lastInsertId()]);

    ugc_send(ugc_issue_token($user ?? []), 201);
}

function ugc_auth_login(): never
{
    ugc_require_method('POST');
    $username = ugc_text(ugc_param('username', ugc_param('name')), 32);
    $password = (string) ugc_param('password', '');
    $ip = ugc_ip();

    ugc_login_throttle($ip, $username);

    $user = ugc_one(
        'SELECT * FROM users WHERE username = :name OR email = :email LIMIT 1',
        ['name' => $username, 'email' => $username]
    );

    if ($user === null || !password_verify($password, (string) $user['password_hash'])) {
        ugc_login_failed($ip, $username);
        ugc_error(401, 'bad_credentials', '用户名或密码不正确');
    }
    if ((string) $user['status'] !== 'active') {
        ugc_error(403, 'banned', '账号已被停用');
    }

    ugc_login_ok($ip, $username);
    if (password_needs_rehash((string) $user['password_hash'], PASSWORD_BCRYPT, ['cost' => 12])) {
        ugc_exec('UPDATE users SET password_hash = :hash WHERE id = :id', [
            'hash' => password_hash($password, PASSWORD_BCRYPT, ['cost' => 12]),
            'id' => (int) $user['id'],
        ]);
    }

    ugc_send(ugc_issue_token($user), 200);
}

function ugc_auth_logout(): never
{
    ugc_require_method('POST');
    $user = ugc_require_user();
    ugc_exec('UPDATE users SET api_token_hash = NULL, token_expires_at = NULL WHERE id = :id', ['id' => (int) $user['id']]);
    ugc_send(['ok' => true]);
}

function ugc_auth_me(): never
{
    ugc_require_method('GET');
    $user = ugc_current_user();
    // 带了 token 但认不出来：明确回 401，客户端据此清掉本地 token
    if ($user === null && (string) ($_SERVER['HTTP_AUTHORIZATION'] ?? '') !== '') {
        ugc_error(401, 'bad_token', '登录状态已失效，请重新登录');
    }

    $limits = ugc_limit_status('model', $user);
    $concurrency = (int) ugc_config('limits.concurrency', 4);
    $anonymousTier = [
        'rate_per_minute' => (int) ugc_config('limits.list_per_minute', 120),
        'download_per_minute' => (int) ugc_config('limits.download_per_minute', 120),
        'concurrency' => $concurrency,
        'download_concurrency' => $concurrency,
    ];
    $userTier = [
        'rate_per_minute' => (int) ugc_config('limits.list_per_minute', 120) * 5,
        'download_per_minute' => (int) ugc_config('limits.download_per_minute', 120) * 5,
        'concurrency' => $concurrency * 4,
        'download_concurrency' => $concurrency * 4,
    ];

    ugc_send([
        'user' => $user === null ? null : ugc_user_shape($user),
        'anonymous' => $user === null,
        // 登录用户把 user 档放前面：客户端是按顺序找第一个并发值的
        'limits' => $user === null
            ? ['anonymous' => $anonymousTier, 'user' => $userTier, 'current' => ['rate' => 0, 'download' => 0, 'concurrency' => 0]]
            : ['user' => $userTier, 'anonymous' => $anonymousTier, 'current' => ['rate' => 0, 'download' => 0, 'concurrency' => 0]],
        'quota' => [
            'model_anonymous_per_hour' => $limits['limit'],
            'model_downloads_used' => $limits['used'],
            'model_downloads_remaining' => $limits['remaining'],
            'reset_at' => $limits['reset_at'],
        ],
    ]);
}
