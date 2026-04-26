# RSI 分层极值追踪自动量化交易系统

> 一个面向个人的数字货币量化交易平台，专为 **ETH 合约** 设计，支持多账号、多交易所（当前集成 OKX，预留 Binance / HTX 接口）。策略基于 **RSI 分层极值追踪**，结合动态杠杆、加仓与浮动止盈/止损，提供 Web 可视化管理与实时监控。

---

## 1. 项目简介
- **定位**：分钟级自动量化交易机器人  
- **核心策略**：RSI 分层极值追踪 & 极值回撤加仓  
- **运行环境**：Debian / Docker  
- **目标人群**：单人自用，支持多账号 & 多平台扩展  

---

## 2. 技术架构说明

| 层级 | 组件 | 说明 |
|------|------|------|
| 前端 | Vue 3 + Vite + Element Plus | 参数配置、监控看板、日志查询 |
| API  | FastAPI | 提供 REST / WebSocket 服务 |
| 策略 | Python 模块 | RSI 计算、交易决策、风险控制 |
| 任务 | Celery + Redis | 1 min 级调度、异步下单、行情订阅 |
| 数据 | TimescaleDB (PostgreSQL) | 1 min K 线 & 交易日志，保留 7 天 |
| 缓存 | Redis | 实时行情 / 临时状态 |
| 备份 | rclone / OSS | 定时增量备份到云端 |
| 部署 | Docker Compose | 一键启动各组件 |

---

## 3. 功能特性
1. **多交易所、多账号** 管理，当前集成 OKX。
2. **RSI 分层极值追踪**  
   - 35/30/20 多头阈值，65/70/80 空头阈值  
   - 极值回撤 ≥2 点自动建仓 / 加仓  
3. **动态杠杆** 与 **弹性仓位控制**，资金比例可调。
4. **分层浮动止盈 & 固定止损**，支持反手循环。
5. **冷却期 / 最大持仓 K 线数** 风控。
6. **Web 实时监控**：账户、持仓、盈亏、日志。
7. **7 天历史数据** 时序存储，增量云备份。
8. **Docker 化部署**，2 核 4G 服务器可运行，可水平扩容。

---

## 4. 快速开始指南

```bash
# 克隆仓库
git clone https://github.com/yourname/rsi-tracker-bot.git
cd rsi-tracker-bot

# 复制环境变量模板
cp .env.example .env          # 填入 OKX API KEY/SECRET/PASSPHRASE 等

# 启动
docker compose up -d          # 首次启动会自动创建数据库并迁移表结构

# 访问前端
http://<服务器IP>:8080
```

---

## 5. 目录结构说明

```
├── api/                # FastAPI 路由
├── core/               # 公共工具 & 配置
├── strategy/           # RSI 分层极值追踪实现
├── exchange/           # 交易所适配器（okx, binance, htx…）
├── tasks/              # Celery 定时任务
├── database/           # ORM & 迁移脚本
├── frontend/           # Vue 3 前端工程
├── docker/             # Dockerfile & compose
└── docs/               # 设计文档
```

---

## 6. 配置说明

`.env` 关键字段：

| 变量 | 示例 | 说明 |
|------|------|------|
| `OKX_API_KEY` | `abc123` | 个人 API Key |
| `OKX_API_SECRET` | `xyz456` | API Secret |
| `OKX_API_PASSPHRASE` | `passphrase` | API Passphrase |
| `DEFAULT_LEVERAGE` | `20` | 默认杠杆倍数，启动后可 Web 调整 |
| `ORDER_FUND_RATIO` | `0.25` | 单次开仓占用账户 USDT 比例 |
| `DATABASE_URL` | `postgres://user:pwd@db:5432/rsi` | TimescaleDB 连接串 |
| `REDIS_URL` | `redis://redis:6379/0` | Redis 连接 |
| `BACKUP_CRON` | `0 3 * * *` | 每天 3:00 备份到云端 |

更多高级参数可在 Web 界面动态修改并热加载。

---

## 7. 部署指南

1. **生产域名与 HTTPS**  
   - 建议使用 `Caddy` / `Nginx` 反向代理，自动签发 TLS 证书。  
2. **系统资源**  
   - 2 核 4G 足以支撑 1-2 个交易账户；并发账户多时请升级至 4 核 8G。  
3. **日志与监控**  
   - Docker 内部日志使用 `json-file` 驱动，可配合 Loki / Grafana。  
4. **数据库维护**  
   - TimescaleDB 自动压缩旧分区；7 天以上数据可手动归档或删除。  
5. **云端备份**  
   - 通过 `rclone` 同步 `postgresql` dump、Redis RDB 到 OSS/COS。  

---

## 8. 安全提醒

- API 密钥**仅赋予交易权限**，禁止提现权限。  
- 建议在交易所启用 **IP 白名单**，仅允许服务器地址访问。  
- Docker 网络对外仅暴露 `80/443/8080` 端口，其余端口请限制内网访问。  
- 定期轮换密钥、升级依赖，防止安全漏洞。  
- 严控杠杆与资金比例，防止爆仓风险。  

---

祝您交易顺利，若有问题请在 Issues 提交反馈或邮件联系维护者。
