#!/usr/bin/env bash
# 一键装机脚本 — 交互生成 backend/.env
# 用法：./setup.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
ENV_PATH="${REPO_ROOT}/backend/.env"
EXAMPLE="${REPO_ROOT}/backend/.env.example"

if [[ ! -f "$EXAMPLE" ]]; then
  echo "❌ 找不到 ${EXAMPLE}，请确认你在仓库根目录运行。"
  exit 1
fi

if [[ -f "$ENV_PATH" ]]; then
  echo "⚠️  ${ENV_PATH} 已存在。"
  read -rp "覆盖它会丢失现有配置。确认覆盖？[y/N] " confirm
  if [[ "${confirm,,}" != "y" ]]; then
    echo "已中止。"
    exit 0
  fi
fi

command -v docker >/dev/null 2>&1 || {
  echo "❌ 需要 docker。请先安装：curl -fsSL https://get.docker.com | sudo sh"
  exit 1
}
command -v openssl >/dev/null 2>&1 || {
  echo "❌ 需要 openssl。请先安装：sudo apt install -y openssl"
  exit 1
}

echo "==> CryptoQuant 一键装机"
echo "回答 3 个问题，1 分钟内可启动。"
echo

read -rp "管理员邮箱（登录用，可填任意邮箱格式字符串）: " ADMIN_EMAIL
if [[ -z "$ADMIN_EMAIL" ]]; then
  echo "❌ 邮箱不能为空"
  exit 1
fi

read -rsp "管理员密码（≥8 位，输入时不显示）: " ADMIN_PASS
echo
if [[ "${#ADMIN_PASS}" -lt 8 ]]; then
  echo "❌ 密码至少 8 位"
  exit 1
fi
read -rsp "再次输入密码: " ADMIN_PASS2
echo
if [[ "$ADMIN_PASS" != "$ADMIN_PASS2" ]]; then
  echo "❌ 两次输入不一致"
  exit 1
fi

read -rp "你的域名（生产填如 quant.mydomain.com；本机测试直接回车默认 localhost）: " DOMAIN
DOMAIN="${DOMAIN:-localhost}"

echo
echo "==> 准备 backend 镜像（首次构建可能要几分钟）..."
docker compose build backend >/dev/null

# 先用 .env.example 作为 stub，让 docker compose 能读到 env_file
# 后面会被真正的 sed 替换覆盖
cp "$EXAMPLE" "$ENV_PATH"

echo "==> 生成密码哈希和密钥..."
HASH=$(printf '%s' "$ADMIN_PASS" | docker compose run --rm -T backend python -c "
import sys, bcrypt
pw = sys.stdin.read().encode()
print(bcrypt.hashpw(pw, bcrypt.gensalt()).decode())
")
SECRET_KEY=$(openssl rand -hex 32)
JWT_SECRET=$(openssl rand -hex 32)

# .env stub 已经从 example 拷出，下面 sed 在原地替换
sed -i "s|^ADMIN_USERNAME=.*|ADMIN_USERNAME=${ADMIN_EMAIL}|" "$ENV_PATH"
sed -i "s|^ADMIN_PASSWORD_HASH=.*|ADMIN_PASSWORD_HASH=${HASH}|" "$ENV_PATH"
sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET_KEY}|" "$ENV_PATH"
sed -i "s|^JWT_SECRET_KEY=.*|JWT_SECRET_KEY=${JWT_SECRET}|" "$ENV_PATH"
sed -i "s|^CORS_ORIGINS=.*|CORS_ORIGINS=http://localhost:8001,http://127.0.0.1:8001,https://${DOMAIN}|" "$ENV_PATH"

chmod 600 "$ENV_PATH"

echo
echo "✅ 已生成 ${ENV_PATH}"
echo
echo "下一步："
echo "  1. 启动：docker compose up -d --build"
echo "  2. 打开浏览器：http://localhost:8001  （生产：https://${DOMAIN}）"
echo "  3. 用刚才设的邮箱 + 密码登录"
echo "  4. 其他配置（交易所 API key / Telegram / SMTP / 风控阈值）登录后在「设置」抽屉里填，立即生效不用重启。"
