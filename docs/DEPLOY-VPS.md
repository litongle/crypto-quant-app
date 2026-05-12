# VPS 部署指南（单用户量化系统）

> 适用：1 核 1G 以上的 Linux VPS（Ubuntu 22.04+ / Debian 12+）。预计 30 分钟完成。

## 前置准备

- 一台 VPS，且 SSH 可登录
- 一个域名，且 A 记录已指向 VPS IP
- 自己的交易所 API key（合约权限）

## 1. 装 Docker + Compose

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# 重新登录后生效
```

## 2. 克隆仓库

```bash
git clone https://github.com/litongle/crypto-quant-app.git
cd crypto-quant-app
```

## 3. 一键装机

```bash
./setup.sh
```

回答 3 个问题（管理员邮箱 / 密码 / 域名）即可。脚本自动：
- bcrypt 哈希密码
- openssl 生成 `SECRET_KEY` / `JWT_SECRET_KEY`
- 填好 `CORS_ORIGINS` 包含你的域名
- 写到 `backend/.env`（权限 600）

其余可热改的配置（**Telegram / SMTP / 风控**）启动后在前端「设置」抽屉里填，保存即时生效。

## 4. 启动后端

```bash
docker compose up -d --build
docker compose logs -f backend
# 看到 "已创建 admin: <你的邮箱>" 即成功
# 按 Ctrl+C 退出日志（不会停服务）
```

此时 `127.0.0.1:8000` 已经在服务，但还没暴露公网。

## 5. 配置 Caddy 反向代理（自动 HTTPS）

```bash
sudo apt install -y caddy
sudo cp deploy/Caddyfile.example /etc/caddy/Caddyfile
sudo sed -i 's/your-domain.example.com/你的域名/' /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Caddy 会自动签发 Let's Encrypt 证书。10 秒后访问 `https://你的域名` 应看到登录页。

## 6. 配置防火墙

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

**关键**：Postgres（5432）和 Redis（6379）由 docker-compose 绑定到 `127.0.0.1`，不会暴露公网；后端的 8000 同样不要直接暴露，全部走 Caddy。

## 7. 验证

- 浏览器打开 `https://你的域名`
- 用 `.env` 里的 `ADMIN_USERNAME` + 步骤 3 输入的明文密码登录
- 进设置抽屉，填交易所 API key
- 在策略页启动 RSI 分层策略，观察事件流

## 日常维护

```bash
# 看日志
docker compose logs -f backend

# 升级
git pull
docker compose up -d --build
docker compose run --rm backend alembic upgrade head

# 重启
docker compose restart backend

# 改 admin 密码（重跑 setup.sh 会覆盖整个 .env；只想换密码用下面这条单行）：
docker compose run --rm backend python -m scripts.generate_admin_hash
# 把新的 ADMIN_PASSWORD_HASH 写回 .env，再 docker compose restart backend
```

## 备份

```bash
# Postgres 数据
docker compose exec postgres pg_dump -U postgres crypto_quant > backup_$(date +%F).sql

# 整卷打包
docker run --rm -v crypto-quant-app_postgres_data:/data -v $PWD:/backup alpine \
  tar czf /backup/pg_data_$(date +%F).tar.gz /data
```

## 给朋友自部署

把整个仓库源码 + 本文档发给他，他按上述 7 步走即可。每个人有独立 VPS、独立 admin、独立交易所 key —— 互不影响。

---

## 附录：在前端配置告警通道（无需重启）

> 强烈建议配上。合约 7×24 跑，没告警 = 出事第二天才发现。
> 已接入的告警事件：策略自停、策略崩溃、策略信号、止损/止盈触发、大额成交。

登录后右上角设置图标 → 设置抽屉：

### 通知通道（Telegram）

1. 手机 Telegram 搜 `@BotFather`，发 `/newbot` 创建 bot 拿 token
2. 给 bot 发任意一条消息触发对话（让 bot 能拿到 chat）
3. 浏览器访问 `https://api.telegram.org/bot<token>/getUpdates`，找到 `"chat":{"id":...}`
4. 设置抽屉 → 通知通道 → 填 token + chat_id → **保存** → 点「发送测试通知」验证

### 邮箱 SMTP

主流邮箱参数：

| 邮箱 | Host | 端口 | 使用 SSL/TLS | 授权码获取 |
|---|---|---|---|---|
| QQ | `smtp.qq.com` | 465 | ✅ 勾选 | 设置 → 账号 → POP3/SMTP → 开启 |
| 网易 163 | `smtp.163.com` | 465 | ✅ 勾选 | 设置 → POP3/SMTP/IMAP → 开启 → 客户端授权密码 |
| Gmail | `smtp.gmail.com` | 465 | ✅ 勾选 | Google 账号 → 安全性 → 应用专用密码（先开 2FA） |
| 自建/企业 | 看自家邮箱配置 | 465 / 587 | 465=勾 / 587=不勾 | — |

设置抽屉 → 邮箱 SMTP → 按上表填 host + 端口 + 用户名 + 授权码（**不是登录密码**） + 收件人 → **保存** → 点「发送测试邮件」验证。

两个通道可同时启用，互不冲突；保存即时生效，不用重启。

### 排错

- **Telegram 收不到** → token / chat_id 填错；或没给 bot 发过消息（拿不到 chat）
- **SMTP 连接被拒** → 端口/SSL 不对：QQ/163 用 465 + 勾选；某些企业邮箱用 587 + 不勾选
- **SMTP 535 认证失败** → 密码用了登录密码而非授权码；或邮箱后台 SMTP 未开启
- **邮件没到/进垃圾箱** → 发件人是 QQ 邮箱时，建议把收件人加入白名单
