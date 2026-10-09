<?php

declare(strict_types=1);

// 资源条目：列表 / 详情 / 删除 / 改状态，以及给客户端看的 item 结构。

/** @return array<string, mixed> */
function ugc_item_shape(array $row): array
{
    $tags = array_values(array_filter(array_map('trim', explode(',', (string) ($row['tags'] ?? '')))));
    $sha256 = (string) ($row['sha256'] ?? '');

    return [
        'id' => (string) ($row['id'] ?? ''),
        'name' => (string) ($row['title'] ?? ''),
        'kind' => (string) ($row['kind'] ?? 'other'),
        'type' => (string) ($row['type'] ?? 'model'),
        'description' => (string) ($row['description'] ?? ''),
        'tags' => $tags,
        'license' => (string) ($row['license'] ?? 'UNKNOWN'),
        'author' => [
            'id' => (string) ($row['uploader_id'] ?? ''),
            'username' => (string) ($row['uploader_name'] ?? ''),
        ],
        'size' => (int) ($row['file_size'] ?? 0),
        'sha256' => $sha256,
        'files' => (int) ($row['file_count'] ?? 1),
        'downloads' => (int) ($row['download_count'] ?? 0),
        'status' => (string) ($row['status'] ?? 'published'),
        'created_at' => ugc_iso((string) ($row['created_at'] ?? ugc_now())),
        'updated_at' => ugc_iso((string) ($row['updated_at'] ?? ugc_now())),
        'download_url' => '/api/items/' . (string) ($row['id'] ?? '') . '/download',
        'meta' => [
            'entry' => (string) ($row['entry_path'] ?? ''),
            'zip_sha256' => $sha256,
        ],
    ];
}

/** @return array<string, mixed> */
function ugc_item_row(int $id, bool $withAuthor = true): array
{
    $row = ugc_one($withAuthor
        ? 'SELECT r.*, u.username AS uploader_name FROM resources r LEFT JOIN users u ON u.id = r.uploader_id WHERE r.id = :id LIMIT 1'
        : 'SELECT * FROM resources WHERE id = :id LIMIT 1', ['id' => $id]);
    if ($row === null) {
        ugc_error(404, 'no_such_item', '资源不存在');
    }
    return $row;
}

/** 能不能看这条：作者本人、管理员、或已上架。 */
function ugc_item_visible(array $row, ?array $user): bool
{
    if ((string) $row['status'] === 'published') {
        return true;
    }
    if ($user === null) {
        return false;
    }
    return (int) $user['id'] === (int) $row['uploader_id'] || (string) $user['role'] === 'admin';
}

function ugc_items_index(): never
{
    ugc_require_method('GET');
    $user = ugc_current_user();

    $kind = ugc_text($_GET['kind'] ?? '', 16);
    $type = ugc_text($_GET['type'] ?? '', 16);
    $search = ugc_text($_GET['q'] ?? '', 60);
    $sort = ugc_text($_GET['sort'] ?? 'new', 8);
    $page = max(1, ugc_int($_GET['page'] ?? 1, 1));
    $pageSize = min(50, max(1, ugc_int($_GET['page_size'] ?? 20, 20)));
    $scope = ugc_text($_GET['scope'] ?? '', 8);
    $uploader = ugc_int($_GET['uploader'] ?? 0);

    $where = [];
    $params = [];
    if ($scope === 'any' && $user !== null && (string) $user['role'] === 'admin') {
        // 管理员看全部（含已下架/封禁）
    } elseif ($scope === 'mine' && $user !== null) {
        $where[] = 'r.uploader_id = :uploader';
        $params['uploader'] = (int) $user['id'];
    } elseif ($uploader > 0) {
        $where[] = 'r.uploader_id = :uploader';
        $where[] = 'r.status = :published';
        $params['uploader'] = $uploader;
        $params['published'] = 'published';
    } else {
        $where[] = 'r.status = :published';
        $params['published'] = 'published';
    }
    if ($kind !== '') {
        $where[] = 'r.kind = :kind';
        $params['kind'] = $kind;
    }
    if ($type !== '') {
        $where[] = 'r.type = :type';
        $params['type'] = $type;
    }
    if ($search !== '') {
        $where[] = '(r.title LIKE :kw_title OR r.description LIKE :kw_desc OR r.tags LIKE :kw_tags)';
        $like = '%' . str_replace(['\\', '%', '_'], ['\\\\', '\\%', '\\_'], $search) . '%';
        $params['kw_title'] = $like;
        $params['kw_desc'] = $like;
        $params['kw_tags'] = $like;
    }

    $clause = $where === [] ? '1 = 1' : implode(' AND ', $where);
    $order = $sort === 'hot' ? 'r.download_count DESC, r.id DESC' : 'r.id DESC';
    $total = (int) (ugc_one('SELECT COUNT(*) AS total FROM resources r WHERE ' . $clause, $params)['total'] ?? 0);
    $rows = ugc_all(
        'SELECT r.*, u.username AS uploader_name FROM resources r LEFT JOIN users u ON u.id = r.uploader_id
         WHERE ' . $clause . ' ORDER BY ' . $order . ' LIMIT ' . $pageSize . ' OFFSET ' . (($page - 1) * $pageSize),
        $params
    );

    ugc_send([
        'items' => array_map('ugc_item_shape', $rows),
        'total' => $total,
        'page' => $page,
        'page_size' => $pageSize,
    ]);
}

function ugc_items_show(string $id): never
{
    ugc_require_method('GET');
    $row = ugc_item_row((int) $id);
    if (!ugc_item_visible($row, ugc_current_user())) {
        ugc_error(403, 'forbidden', '这条资源还没上架');
    }
    ugc_send(['item' => ugc_item_shape($row)]);
}

function ugc_items_delete(string $id): never
{
    ugc_require_method('DELETE');
    $user = ugc_require_user();
    $row = ugc_item_row((int) $id, false);

    $isOwner = (int) $row['uploader_id'] === (int) $user['id'];
    if (!$isOwner && (string) $user['role'] !== 'admin') {
        ugc_error(403, 'forbidden', '只能删除自己上传的资源');
    }

    ugc_exec('DELETE FROM resources WHERE id = :id', ['id' => (int) $row['id']]);
    // 文件是按 sha256 命名、多个条目可能共用一份，没人再用它了才删盘上的文件
    $stillUsed = (int) (ugc_one('SELECT COUNT(*) AS total FROM resources WHERE file_path = :path', [
        'path' => (string) $row['file_path'],
    ])['total'] ?? 0);
    if ($stillUsed === 0) {
        $path = ugc_upload_absolute((string) $row['file_path']);
        if ($path !== null) {
            @unlink($path);
        }
    }
    ugc_log('删除资源', ['id' => (int) $row['id'], 'by' => (int) $user['id'], 'admin' => !$isOwner]);
    if (!headers_sent()) {
        http_response_code(204);
    }
    exit;
}

/** 上架 / 下架 / 封禁：作者只能在自己的资源上切换 published/hidden，封禁只有管理员能做。 */
function ugc_items_status(string $id): never
{
    ugc_require_method('POST');
    $user = ugc_require_user();
    $row = ugc_item_row((int) $id, false);
    $status = ugc_text(ugc_param('status'), 16);

    if (!in_array($status, ['published', 'hidden', 'blocked'], true)) {
        ugc_error(422, 'bad_field', 'status 只能是 published、hidden 或 blocked', ['field' => 'status']);
    }
    $isOwner = (int) $row['uploader_id'] === (int) $user['id'];
    $isAdmin = (string) $user['role'] === 'admin';
    if (!$isAdmin && !$isOwner) {
        ugc_error(403, 'forbidden', '只能管理自己上传的资源');
    }
    if ($status === 'blocked' && !$isAdmin) {
        ugc_error(403, 'forbidden', '只有管理员可以封禁资源');
    }

    ugc_exec('UPDATE resources SET status = :status, updated_at = :now WHERE id = :id', [
        'status' => $status,
        'now' => ugc_now(),
        'id' => (int) $row['id'],
    ]);
    ugc_log('修改资源状态', ['id' => (int) $row['id'], 'status' => $status, 'by' => (int) $user['id']]);
    ugc_send(['item' => ugc_item_shape(ugc_item_row((int) $row['id']))]);
}
