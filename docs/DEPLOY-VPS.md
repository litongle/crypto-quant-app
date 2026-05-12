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

## 3. 配置 `.env`

```bash
cp backend/.env.example backend/.env

# 生成 ADMIN_PASSWORD_HASH（交互输入密码两次，会输出一行 ADMIN_PASSWORD_HASH=...）
docker compose run --rm backend python -m scripts.generate_admin_hash

# 编辑 backend/.env：
#   - ADMIN_USERNAME       = 你的登录邮箱
#   - ADMIN_PASSWORD_HASH  = 上面命令输出的哈希
#   - SECRET_KEY           = openssl rand -hex 32 生成
#   - JWT_SECRET_KEY       = openssl rand -hex 32 生成
#   - CORS_ORIGINS         = 加上 https://你的域名
```

## 4. 启动后端

```bash
docker compose up -d --build
docker compose logs -f backend
# 看到 "已创建 admin: <你的邮箱>" 即成功
# 按 Ctrl+C 退出日志（不会停服务）
```

此时 `127.0.0.1:8001` 已经在服务，但还没暴露公网。

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

**关键**：Postgres（5432）和 Redis（6379）由 docker-compose 绑定到 `127.0.0.1`，不会暴露公网；后端的 8001 同样不要直接暴露，全部走 Caddy。

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

# 改 admin 密码：
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

## 附录：配置 Telegram 告警（5 分钟）

> 强烈建议配上。合约 7×24 跑，没告警 = 出事第二天才发现。
> 已接入的告警事件：策略自停、策略崩溃、策略信号、止损/止盈触发、大额成交。

### 1. 创建 bot 拿 token

1. 手机 Telegram 搜 `@BotFather`，发 `/start`，再发 `/newbot`
2. 按提示输入 bot 名字（任意）+ 用户名（必须以 `bot` 结尾，如 `my_quant_alert_bot`）
3. BotFather 回复一段消息，里面有一行：`HTTP API: 123456789:ABCdefGhIJK...` —— **这就是 token，复制下来**

### 2. 拿到你的 chat_id

1. 在 Telegram 搜你刚创建的 bot，按 **Start** 发一条消息（任意内容，如 `hi`）
2. 浏览器打开（把 `<token>` 替换成上一步的 token）：
   ```
   https://api.telegram.org/bot<token>/getUpdates
   ```
3. 返回的 JSON 里找 `"chat":{"id":123456789,...}` —— **123456789 就是你的 chat_id**

### 3. 填到 `.env`

```bash
# 编辑 backend/.env：
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJK...
TELEGRAM_CHAT_ID=123456789

# 重启后端
docker compose restart backend
```

### 4. 验证

启动后端日志里搜「告警」无报错即正常。如果想立刻试一下推送是否到位：

```bash
# 容器内手动触发一条告警
docker compose exec backend python -c "
import asyncio
from app.services.notification_service import notify_risk_alert
asyncio.run(notify_risk_alert(
    alert_type='测试',
    message='如果你看到这条 = Telegram 配置成功',
    metrics={'source': 'manual_test'},
))
"
```

手机 Telegram 应该秒收到。收不到 → 检查 token / chat_id 是否填错、bot 是否被你 Start 过。

---

## 附录：配置邮箱告警（5 分钟）

> 国内 VPS 无梯子时的兜底通道。可与 Telegram 同时启用，互相不冲突。
> 密码用「邮箱的 SMTP 授权码」**不是登录密码**。

### 主流邮箱 SMTP 参数

| 邮箱 | SMTP_HOST | 端口 | SMTP_USE_TLS | 授权码获取 |
|---|---|---|---|---|
| QQ 邮箱 | `smtp.qq.com` | 465 | `true` | 设置 → 账号 → POP3/SMTP → 开启 → 生成授权码 |
| 网易 163 | `smtp.163.com` | 465 | `true` | 设置 → POP3/SMTP/IMAP → 开启 → 客户端授权密码 |
| Gmail | `smtp.gmail.com` | 465 | `true` | Google 账号 → 安全性 → 应用专用密码（需先开 2FA） |
| 自建/企业 | 看自家邮箱配置 | 通常 465 或 587 | 465=true / 587=false | — |

### 配置步骤

1. 按上表去邮箱后台开 SMTP 服务，拿到**授权码**（不是登录密码）
2. 编辑 `backend/.env`：
   ```bash
   SMTP_HOST=smtp.qq.com
   SMTP_PORT=465
   SMTP_USERNAME=your_account@qq.com
   SMTP_PASSWORD=auth_code_from_step_1
   SMTP_FROM=                              # 留空则用 SMTP_USERNAME
   SMTP_TO=your_personal@example.com       # 收件人，发到自己就行
   SMTP_USE_TLS=true
   ```
3. 重启：`docker compose restart backend`
4. 测试（同 Telegram 那条命令，邮箱与 Telegram 共用同一发送出口）：
   ```bash
   docker compose exec backend python -c "
   import asyncio
   from app.services.notification_service import notify_risk_alert
   asyncio.run(notify_risk_alert(
       alert_type='测试',
       message='如果你收到这封邮件 = SMTP 配置成功',
       metrics={'source': 'manual_test'},
   ))
   "
   ```
5. 几秒内邮箱应收到主题为 `[CryptoQuant] 风控告警 | 测试` 的邮件。

### 排错

- **连接被拒** → 端口/SSL 不对：QQ/163 用 465 + `SMTP_USE_TLS=true`；某些企业邮箱用 587 + `SMTP_USE_TLS=false`
- **535 认证失败** → 密码用了登录密码而非授权码；或邮箱后台 SMTP 未开启
- **邮件没到/进垃圾箱** → 发件人是 QQ 邮箱时，建议把 `SMTP_TO` 加入收件方白名单，避免被识别为陌生邮件
