<?php

declare(strict_types=1);

// 限流流水：匿名下模型按 IP 记次数（插件不限），另带上传频率与清理。

/** @return array{limit: int, used: int, remaining: int, reset_at: int, limited: bool} */
function ugc_limit_status(string $type, ?array $user): array
{
    $limit = $user !== null ? 0 : (int) ugc_config('limits.' . $type . '_anonymous_per_hour', 0);
    $hourStart = gmdate('Y-m-d H:i:s', time() - 3600);
    $used = (int) (ugc_one(
        'SELECT COUNT(*) AS total FROM download_limits WHERE ip = :ip AND resource_type = :type AND created_at > :since',
        ['ip' => ugc_ip(), 'type' => $type, 'since' => $hourStart]
    )['total'] ?? 0);

    return [
        'limit' => $limit,
        'used' => $used,
        'remaining' => $limit === 0 ? PHP_INT_MAX : max(0, $limit - $used),
        'reset_at' => time() + 3600,
        'limited' => $limit > 0 && $used >= $limit,
    ];
}

function ugc_limit_record(string $type, ?array $user): void
{
    ugc_exec(
        'INSERT INTO download_limits (ip, resource_type, user_id, created_at) VALUES (:ip, :type, :user_id, :now)',
        [
            'ip' => ugc_ip(),
            'type' => $type,
            'user_id' => $user === null ? null : (int) $user['id'],
            'now' => ugc_now(),
        ]
    );
}

/** 上传频率：直接数最近一小时自己传了多少条，不用额外表。 */
function ugc_upload_quota_check(int $userId): void
{
    $limit = (int) ugc_config('limits.uploads_per_hour', 10);
    if ($limit <= 0) {
        return;
    }
    $used = (int) (ugc_one(
        'SELECT COUNT(*) AS total FROM resources WHERE uploader_id = :id AND created_at > :since',
        ['id' => $userId, 'since' => gmdate('Y-m-d H:i:s', time() - 3600)]
    )['total'] ?? 0);
    if ($used >= $limit) {
        ugc_error(429, 'rate_limited', '上传太频繁了，请稍后再试', ['retry_after' => 3600]);
    }
}

/** 顺手清掉过期的限流流水；1% 概率或 health 检查时调用。 */
function ugc_limit_cleanup(): void
{
    $days = (int) ugc_config('limits.history_days', 7);
    ugc_exec('DELETE FROM download_limits WHERE created_at <= :before', [
        'before' => gmdate('Y-m-d H:i:s', time() - $days * 86400),
    ]);
}
