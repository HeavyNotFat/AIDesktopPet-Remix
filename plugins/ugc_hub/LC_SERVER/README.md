# ugc-hub 后端（桌宠的资源站）

桌宠上传 / 下载「模型」和「插件」用的一个很小的 PHP 后端：**8 个 PHP 文件、3 张表、纯 JSON API**，
没有框架、没有网页界面、没有会话 cookie（纯 Bearer token，所以也不存在 CSRF 面）。

功能就是桌宠需要的那几件事：

* 注册 / 登录 / 登出（bcrypt 存密码，token 只存 sha256 摘要，默认 30 天）
* 上传模型与插件（三步分片、可续传；扩展名 + 文件头 + 压缩包条目三重校验）
* 列表 / 详情 / 下载（支持 `Range` 与 `?part=N`，多线程下载友好）
* 未登录下**模型**每小时 5 次（IP 维度，超了 429），插件不限、登录用户不限
* 作者能改自己资源的上架/下架，管理员能封禁和删除任何资源

## 接口一览

| 方法 | 路径 | 说明 |
|:--|:--|:--|
| GET | `/api/health` | 存活检查，回显并发/额度参考值（不碰数据库） |
| POST | `/api/auth/register` | `{username, password, email?}` → `{token, expires_at, user}`；**第一个注册的人是管理员** |
| POST | `/api/auth/login` | `{username, password}` → 同上 |
| POST | `/api/auth/logout` | 需要 token，作废当前 token |
| GET | `/api/auth/me` | 匿名可调（`user: null`）；带了无效 token 回 401 `bad_token` |
| GET | `/api/items` | `kind/type/q/sort=new|hot/page/page_size/uploader/scope=mine|any` |
| GET | `/api/items/{id}` | 详情 |
| DELETE | `/api/items/{id}` | 作者或管理员；文件也一起删 |
| POST | `/api/items/{id}/status` | `{status: published|hidden|blocked}`；作者只能切 published/hidden，封禁仅管理员 |
| POST | `/api/uploads` | 开会话 `{size, sha256, name, kind?}` → `{upload_id, offset, chunk_size, expires_at}` |
| POST | `/api/uploads/{id}/chunk` | 带 `Content-Range: bytes a-b/total`，写原始字节；乱序回 **308 + 真实 offset** |
| POST | `/api/uploads/{id}/complete` | `{name, kind, description?, tags?, license?}` → `{item}`；同一份文件重复传回已有条目 + `duplicate: true` |
| GET/HEAD | `/api/items/{id}/download` | 整包 / `Range: bytes=` / `?part=N`；HEAD 不计数也不占额度 |

鉴权：`Authorization: Bearer <token>`。错误一律是 `{"error":{"code","message"}}`，429 额外带
`Retry-After` 头与 `retry_after` 字段。下载响应带 `X-Item-SHA256`、`X-Part-Count`、`X-Part-Size`、
`X-Concurrency-Limit`，客户端可以直接用来分片与校验。

## 部署

前置：PHP 8.1+（要 `pdo_mysql`）、MySQL 5.7+

配置：
location ^~ /api/ { try_files $uri /public/index.php?$query_string; }
location ^~ /src/     { deny all; }
location ^~ /storage/ { deny all; }
location ^~ /tests/   { deny all; }
location ^~ /sql/     { deny all; }



**站点根指到 `public/`**（推荐，最干净）：

* Nginx：`root /www/wwwroot/ugc/public;` + 常规 PHP location + `try_files $uri /index.php?$query_string;`
* Apache：`DocumentRoot /www/wwwroot/ugc/public`，并确认 `AllowOverride All`（`public/.htaccess` 里就是 rewrite 规则）
* 宝塔：网站目录填项目目录、**运行目录选 `/public`**

如果只能把站点根放在项目目录上，项目根的 `.htaccess` 已经写好了：转发到 `public/`，并把
`src|sql|tests|storage|config` 全部 403（Nginx 需要自己写等价规则）。

**上传文件不要放进 web 根**：默认落在 `storage/uploads/`，目录里会自动补一份禁止执行的 `.htaccess`
（Nginx 请自行加 `location ^~ /storage/ { deny all; }`）。PHP 的 `upload_max_filesize` / `post_max_size`
要大于 `src/config.php` 里的 `upload.max_bytes`。

自检：

```bash
php -d extension=pdo_mysql tests/api-test.php     # 68 项验收：账号/上传/下载/限流/权限/危险文件
php tests/client-test.php                         # 用真实桌面插件客户端跑 13 项兼容测试
php -d extension=pdo_mysql tests/make-fixture.php # 生成一个 Live2D 测试包，手工联调用
```
