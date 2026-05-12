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
