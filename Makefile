# Crypto Quant App — 开发命令快捷方式
# 用法：直接 `make` 看所有命令；`make <target>` 执行
#
# 设计原则：
#   - 默认假设服务已起（用 exec，而不是 run --rm）
#   - 没起？先 `make up`
#   - 命令分组：服务 / 数据库 / 迁移 / 测试质量 / 日志排查

SHELL       := /bin/bash
COMPOSE     := docker compose
DB_USER     := postgres
DB_NAME     := crypto_quant
REDIS_PASS  := dev-redis-password

.DEFAULT_GOAL := help

# ═══════════════════════════════════════════════════
# 服务生命周期
# ═══════════════════════════════════════════════════

.PHONY: up
up: ## 启动所有服务（后台）
	$(COMPOSE) up -d

.PHONY: up-build
up-build: ## 重新构建镜像并启动
	$(COMPOSE) up -d --build

.PHONY: down
down: ## 停止服务（数据保留）
	$(COMPOSE) down

.PHONY: restart
restart: ## 重启 backend（改了代码且 reload 没生效时用）
	$(COMPOSE) restart backend

.PHONY: ps
ps: ## 看服务状态
	$(COMPOSE) ps

.PHONY: dev
dev: up migrate ## 一键开发：起服务 + 应用迁移

.PHONY: reset
reset: ## ⚠️  清空数据库重来（删所有数据，5 秒缓冲可 Ctrl+C）
	@echo "⚠️  即将删除所有数据库数据。5 秒内 Ctrl+C 取消..."
	@sleep 5
	$(COMPOSE) down -v
	$(COMPOSE) up -d
	$(MAKE) migrate
	@echo "✓ 重置完成"

# ═══════════════════════════════════════════════════
# 数据库交互
# ═══════════════════════════════════════════════════

.PHONY: shell
shell: ## 进 psql 交互
	$(COMPOSE) exec postgres psql -U $(DB_USER) -d $(DB_NAME)

.PHONY: redis-cli
redis-cli: ## 进 redis-cli 交互
	$(COMPOSE) exec redis redis-cli -a $(REDIS_PASS)

.PHONY: backend-shell
backend-shell: ## 进 backend 容器 bash
	$(COMPOSE) exec backend bash

# ═══════════════════════════════════════════════════
# Alembic 迁移
# ═══════════════════════════════════════════════════

.PHONY: migrate
migrate: ## 应用所有迁移到最新
	$(COMPOSE) exec backend alembic upgrade head

.PHONY: migrate-down
migrate-down: ## 回退一个版本
	$(COMPOSE) exec backend alembic downgrade -1

.PHONY: migrate-new
migrate-new: ## 生成新迁移；用法：make migrate-new m="add user table"
	@if [ -z "$(m)" ]; then \
		echo "❌ 请提供 message：make migrate-new m=\"描述\""; exit 1; \
	fi
	$(COMPOSE) exec backend alembic revision --autogenerate -m "$(m)"

.PHONY: migrate-history
migrate-history: ## 看迁移历史
	$(COMPOSE) exec backend alembic history

.PHONY: migrate-current
migrate-current: ## 看当前版本
	$(COMPOSE) exec backend alembic current

# ═══════════════════════════════════════════════════
# 测试与代码质量
# ═══════════════════════════════════════════════════

.PHONY: test
test: ## 跑全部测试
	$(COMPOSE) exec backend pytest

.PHONY: test-file
test-file: ## 跑指定文件；用法：make test-file f=tests/test_x.py
	@if [ -z "$(f)" ]; then \
		echo "❌ 请提供文件：make test-file f=tests/路径.py"; exit 1; \
	fi
	$(COMPOSE) exec backend pytest $(f)

.PHONY: test-k
test-k: ## 按名字过滤跑测试；用法：make test-k k=test_login
	@if [ -z "$(k)" ]; then \
		echo "❌ 请提供关键字：make test-k k=test_xxx"; exit 1; \
	fi
	$(COMPOSE) exec backend pytest -k "$(k)"

.PHONY: lint
lint: ## ruff + black 检查（不改代码）
	$(COMPOSE) exec backend ruff check .
	$(COMPOSE) exec backend python -m black --check .

.PHONY: lint-fix
lint-fix: ## ruff 自动修复 + black 格式化
	$(COMPOSE) exec backend ruff check --fix .
	$(COMPOSE) exec backend python -m black .

.PHONY: format
format: ## black 格式化（不跑 ruff）
	$(COMPOSE) exec backend python -m black .

.PHONY: typecheck
typecheck: ## mypy 严格类型检查
	$(COMPOSE) exec backend mypy .

.PHONY: check
check: lint typecheck test ## 一把梭：lint + 类型 + 测试

# ═══════════════════════════════════════════════════
# 日志与排查
# ═══════════════════════════════════════════════════

.PHONY: logs
logs: ## 跟 backend 日志（Ctrl+C 退出）
	$(COMPOSE) logs -f backend

.PHONY: logs-all
logs-all: ## 跟所有服务日志
	$(COMPOSE) logs -f

.PHONY: logs-tail
logs-tail: ## backend 最近 100 行日志（不跟随）
	$(COMPOSE) logs --tail=100 backend

# ═══════════════════════════════════════════════════
# 帮助
# ═══════════════════════════════════════════════════

.PHONY: help
help: ## 显示这份命令列表
	@echo ""
	@echo "  Crypto Quant App — 开发命令"
	@echo "  ────────────────────────────"
	@echo ""
	@grep -hE '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  常用组合："
	@echo "    make dev          # 起服务 + 迁移，开干"
	@echo "    make shell        # 进 psql 看数据"
	@echo "    make logs         # 跟 backend 日志"
	@echo "    make check        # 提交前一把过"
	@echo ""
