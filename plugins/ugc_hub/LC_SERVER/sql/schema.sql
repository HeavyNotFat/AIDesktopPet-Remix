-- UGC 后端建表脚本（MySQL 5.7+）：三张表，够用就好
-- 用法：mysql -u ugc -p ugc < sql/schema.sql

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS users (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    username VARCHAR(32) NOT NULL,
    email VARCHAR(120) NOT NULL DEFAULT '',
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('user', 'admin') NOT NULL DEFAULT 'user',
    status ENUM('active', 'banned') NOT NULL DEFAULT 'active',
    api_token_hash CHAR(64) NULL DEFAULT NULL,
    token_expires_at DATETIME NULL DEFAULT NULL,
    last_login_at DATETIME NULL DEFAULT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uniq_username (username),
    KEY idx_token (api_token_hash)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS resources (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(120) NOT NULL,
    description TEXT NULL,
    type ENUM('model', 'plugin') NOT NULL DEFAULT 'model',
    kind VARCHAR(16) NOT NULL DEFAULT 'other',
    tags VARCHAR(200) NOT NULL DEFAULT '',
    license VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
    file_name VARCHAR(80) NOT NULL,
    original_name VARCHAR(160) NOT NULL,
    file_path VARCHAR(255) NOT NULL,
    file_size BIGINT UNSIGNED NOT NULL DEFAULT 0,
    sha256 CHAR(64) NOT NULL,
    entry_path VARCHAR(255) NOT NULL DEFAULT '',
    file_count INT UNSIGNED NOT NULL DEFAULT 1,
    uploader_id INT UNSIGNED NOT NULL,
    download_count INT UNSIGNED NOT NULL DEFAULT 0,
    status ENUM('published', 'hidden', 'blocked') NOT NULL DEFAULT 'published',
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    KEY idx_list (status, type, kind, id),
    KEY idx_uploader (uploader_id, created_at),
    KEY idx_sha (uploader_id, sha256),
    CONSTRAINT fk_resources_uploader FOREIGN KEY (uploader_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- 只记"谁在什么时候下过什么"，用来自查未登录用户的每小时额度
CREATE TABLE IF NOT EXISTS download_limits (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    ip VARCHAR(45) NOT NULL,
    resource_type ENUM('model', 'plugin') NOT NULL,
    user_id INT UNSIGNED NULL DEFAULT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    KEY idx_window (ip, resource_type, created_at)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;