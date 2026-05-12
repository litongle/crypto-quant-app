# 单用户 + VPS 化部署改造设计

> **状态**：已实施（commit 链 d4142e5..6db4896，2026-05-13）
> **背景**：本项目定位「个人自用 + 给朋友源码自部署」，前端形态在 [2026-05-09-frontend-restructure-design.md](./2026-05-09-frontend-restructure-design.md) 中已收敛；本 spec 配套清理后端 SaaS 残留 + 补 VPS 部署文档。

## 0. 一句话目标

把后端从「多用户 + 安装向导 + 审计平台」收敛为「单用户 admin + VPS 部署 + 自用量化系统」，并补齐 Caddy 反向代理部署文档。

## 1. 现状（改造前）

后端保留了大量个人自用场景用不到的 SaaS 残留：

| 文件 | 行数 | 角色 |
|---|---|---|
| `app/api/v1/setup.py` | 229 | 安装向导路由（status/env-defaults/complete） |
| `app/web/static/setup.html` | 511 | 安装向导前端页 |
| `app/api/v1/users.py` | 48 | 审计日志查询 |
| `app/api/audit_middleware.py` | 88 | 审计中间件 |
| `app/services/audit_service.py` | 102 | 审计服务 |
| `app/services/totp_service.py` | 93 | TOTP/2FA 服务 |
| `app/models/audit.py` | 63 | AuditLog 模型 |
| `app/web/static/js/security.js` | 334 | 2FA + 审计 UI |
| `app/api/v1/auth.py` 内 7 个端点 | — | register、login-2fa、2fa/* |

## 2. 关键决策（brainstorming 阶段对齐）

| 决策点 | 选择 | 否决方案 | 理由 |
|---|---|---|---|
| 认证 | 单用户 admin + JWT 应用登录 | 无登录靠反代 BasicAuth；保留 TOTP | 合约场景必须有一层访问控制；TOTP 维护负担与自用价值不匹配 |
| 节奏 | 一个 PR 一次性砍完 | 分阶段 | 文件间耦合强，分阶段会有较长的「中间炸状态」 |
| 数据库 | 强制 PG（删 SQLite fallback） | 保留 SQLite 兼容 | docker-compose 已经内置 PG，再保留 SQLite 是多余分支 |
| 反向代理 | Caddy v2（自动 HTTPS） | Nginx + certbot | 个人项目更友好，Let's Encrypt 自动续期 |
| 单用户存储 | 保留 `users` 表 + 启动种子 user_id=1 | 删 User 模型 | ExchangeAccount/StrategyInstance 都有 user_id 外键，全删要动整个数据模型 |

## 3. 实施分解（与 [plans/2026-05-13-single-user-vps-migration.md](../plans/2026-05-13-single-user-vps-migration.md) 一一对应）

| Task | 内容 | Commit |
|---|---|---|
| 1 | 新增 `ADMIN_USERNAME`/`ADMIN_PASSWORD_HASH` 配置 + `scripts/generate_admin_hash.py` | d4142e5 |
| 2 | `app/main.py::seed_admin()`，lifespan 中调用，幂等同步 email/hash | 583459c |
| 3+4 | AuthService 与 auth.py 收敛单用户（合并以避免中间炸状态） | 1491874 |
| 5 | 删除 `totp_service.py` + User 模型 totp/superuser 字段 | 34a155f |
| 6 | 删除审计中间件/service/模型/users 路由；事件流重写不再依赖 AuditLog | addc823 |
| 7 | 删除安装向导（API + setup.html + 根路径跳转） | e9b75a4 |
| 8 | 前端 index.html 删注册/2FA 块；api.js 删 register/2FA 方法；删 security.js | ce4d484 |
| 9 | Alembic 迁移 0011 drop audit_logs/totp/superuser | b7532da |
| 10 | `docs/DEPLOY-VPS.md` + `deploy/Caddyfile.example` + README | 6db4896 |
| 11 | 归档 spec + 全量回归 | （本 commit） |

## 4. 副作用与权衡

- **事件流降级**：原本聚合 audit_logs / signals / auto_pause 三种源，现只剩 signals + auto_pause。「订单提交/风险告警/错误」类事件在事件流中消失。
  - 若将来需要回补：建议新增 `strategy_event` 表由 strategy_runner 主动写入（而不是 middleware 被动捕获），避免再次引入审计中间件那种「自己审计自己」的反模式。
- **登录侧 robust 性**：单用户场景下，admin 密码改了之后 .env 中的 `ADMIN_PASSWORD_HASH` 必须同步更新；启动时 seed_admin 会自动把 .env 中的 hash 写回 users 表。
- **多用户库的兼容**：seed_admin 检测到 `len(users) > 1` 时会 warning 并保留第一条；不会删除其他用户记录（避免误删数据）。

## 5. 验证矩阵

- **回归**：`docker compose run --rm backend pytest` → 602 测试通过
- **Alembic**：`alembic upgrade head` → `downgrade -1` → `upgrade head` 三轮成功
- **端到端**：手工浏览器验证（plan Task 11 步骤 4）— 用户侧执行

## 6. 风险与回滚

| 风险 | 缓解 |
|---|---|
| `.env` 没填 `ADMIN_PASSWORD_HASH` 直接重启 | `seed_admin` 仅 warning，不创建用户；登录会失败但系统不崩溃 |
| 已存在多用户的库迁移后丢失访问 | `seed_admin` 仅同步第一条记录；其余用户保留但需手动清理 |
| Alembic 0011 在生产 PG 上失败 | downgrade 已验证可逆；线上前在 dump 上预演 |
| Caddy 配置错误导致 HTTPS 失败 | DEPLOY-VPS.md 文档明确「先验证 http 内网联通，再上 Caddy」 |
