#!/usr/bin/env bash
# PostgreSQL 备份脚本 — 保留最近 7 天，支持本地 + S3 上传
set -euo pipefail

# 配置（可通过环境变量覆盖）
DB_URL="${DATABASE_URL:-postgresql://postgres:postgres@localhost:5432/crypto_quant}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
S3_BUCKET="${S3_BUCKET:-}"
AWS_REGION="${AWS_REGION:-ap-northeast-1}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILENAME="crypto_quant_${TIMESTAMP}.sql.gz"
LOCAL_PATH="${BACKUP_DIR}/${FILENAME}"

mkdir -p "${BACKUP_DIR}"

echo "[backup] Starting PostgreSQL backup at ${TIMESTAMP}..."

# 执行备份并压缩
pg_dump "${DB_URL}" --clean --if-exists --no-owner --no-privileges | gzip > "${LOCAL_PATH}"

FILE_SIZE=$(du -h "${LOCAL_PATH}" | cut -f1)
echo "[backup] Local backup created: ${LOCAL_PATH} (${FILE_SIZE})"

# 上传到 S3（若配置了 bucket）
if [ -n "${S3_BUCKET}" ]; then
  if command -v aws &> /dev/null; then
    S3_KEY="backups/postgres/${FILENAME}"
    aws s3 cp "${LOCAL_PATH}" "s3://${S3_BUCKET}/${S3_KEY}" --region "${AWS_REGION}"
    echo "[backup] Uploaded to s3://${S3_BUCKET}/${S3_KEY}"
  else
    echo "[backup] WARNING: aws CLI not found, skipping S3 upload" >&2
  fi
fi

# 清理过期备份
find "${BACKUP_DIR}" -name "crypto_quant_*.sql.gz" -type f -mtime +${RETENTION_DAYS} -delete
echo "[backup] Cleaned up backups older than ${RETENTION_DAYS} days"

echo "[backup] Done"
