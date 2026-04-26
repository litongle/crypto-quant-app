"""
用户 API — 已合并到 auth.py，此文件保留为空以防路由冲突

原 /me 端点已移至 auth/me，统一使用 APIResponse 格式。
"""
from fastapi import APIRouter

router = APIRouter()

# 用户相关端点已全部迁移至 auth.py:
# - GET /me → GET /auth/me（统一返回 APIResponse）
