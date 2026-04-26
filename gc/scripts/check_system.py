#!/usr/bin/env python
"""
RSI分层极值追踪自动量化交易系统 - 系统状态检测脚本

该脚本用于检测系统各组件的运行状态，包括：
1. 数据库连接测试
2. Redis连接测试
3. OKX API连接测试
4. Celery任务队列状态检查
5. 系统健康度评估
6. 详细的输出报告

使用方法:
    python -m scripts.check_system [--verbose] [--output-file FILENAME]

选项:
    --verbose: 显示详细输出
    --output-file: 将报告保存到指定文件

示例:
    python -m scripts.check_system --verbose --output-file system_status.txt
"""

import os
import sys
import time
import json
import asyncio
import argparse
import datetime
import platform
import socket
from typing import Dict, List, Any, Optional, Tuple
import traceback
from pathlib import Path

# 添加项目根目录到系统路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 导入项目模块
try:
    from app.core.config import settings
    from app.database import engine, get_db
    from app.database.models import Kline, TradingAccount, Position, Trade, StrategyState
    from app.exchange import ApiCredential, create_exchange, ExchangeType
    from sqlalchemy import text, select, func
    from celery.app.control import Control
    from celery import Celery
    import redis
    import psutil
    import pandas as pd
    import matplotlib.pyplot as plt
except ImportError as e:
    print(f"错误: 导入项目模块失败 - {e}")
    print("请确保在项目根目录下运行此脚本，并已安装所有依赖")
    sys.exit(1)

# ANSI颜色代码
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class SystemChecker:
    """系统状态检测类"""
    
    def __init__(self, verbose: bool = False):
        """
        初始化系统检测器
        
        Args:
            verbose: 是否显示详细输出
        """
        self.verbose = verbose
        self.results = {
            "timestamp": datetime.datetime.now().isoformat(),
            "system_info": self._get_system_info(),
            "tests": {},
            "health_score": 0,
            "overall_status": "未知"
        }
        self.celery_app = None
        self.redis_client = None
    
    def _get_system_info(self) -> Dict[str, str]:
        """获取系统信息"""
        try:
            return {
                "hostname": socket.gethostname(),
                "platform": platform.platform(),
                "python_version": platform.python_version(),
                "cpu_count": psutil.cpu_count(logical=True),
                "memory_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
                "disk_free_gb": round(psutil.disk_usage('/').free / (1024**3), 2),
                "project_path": str(Path(__file__).resolve().parent.parent)
            }
        except Exception as e:
            return {
                "error": f"获取系统信息失败: {str(e)}"
            }
    
    def _log(self, message: str, level: str = "info"):
        """记录日志"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if level == "info":
            prefix = f"{Colors.BLUE}[INFO]{Colors.ENDC}"
        elif level == "success":
            prefix = f"{Colors.GREEN}[成功]{Colors.ENDC}"
        elif level == "warning":
            prefix = f"{Colors.YELLOW}[警告]{Colors.ENDC}"
        elif level == "error":
            prefix = f"{Colors.RED}[错误]{Colors.ENDC}"
        else:
            prefix = f"[{level.upper()}]"
        
        if self.verbose or level in ["error", "warning"]:
            print(f"{prefix} {timestamp} - {message}")
    
    async def test_database_connection(self) -> Dict[str, Any]:
        """测试数据库连接"""
        self._log("测试数据库连接...")
        start_time = time.time()
        result = {
            "name": "数据库连接测试",
            "status": "失败",
            "details": {},
            "error": None
        }
        
        try:
            # 测试数据库连接
            with engine.connect() as connection:
                # 检查数据库版本
                version_query = text("SELECT version();")
                version_result = connection.execute(version_query).scalar()
                
                # 检查TimescaleDB是否安装
                timescale_query = text("""
                    SELECT default_version, installed_version 
                    FROM pg_available_extensions 
                    WHERE name = 'timescaledb';
                """)
                timescale_result = connection.execute(timescale_query).fetchone()
                
                # 检查表是否存在
                tables_query = text("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public';
                """)
                tables_result = connection.execute(tables_query).fetchall()
                tables = [row[0] for row in tables_result]
                
                # 检查超表是否正确设置
                hypertables_query = text("""
                    SELECT table_name, created_on
                    FROM timescaledb_information.hypertables;
                """)
                try:
                    hypertables_result = connection.execute(hypertables_query).fetchall()
                    hypertables = [row[0] for row in hypertables_result]
                except:
                    hypertables = []
                
                # 获取数据库大小
                size_query = text("""
                    SELECT pg_size_pretty(pg_database_size(current_database()));
                """)
                size_result = connection.execute(size_query).scalar()
                
                # 检查K线数据
                kline_count = 0
                try:
                    db = next(get_db())
                    kline_count = db.query(func.count(Kline.id)).scalar()
                    db.close()
                except Exception as e:
                    self._log(f"获取K线数据失败: {e}", "warning")
                
                result["status"] = "成功"
                result["details"] = {
                    "version": version_result,
                    "timescale_installed": timescale_result is not None,
                    "timescale_version": timescale_result[0] if timescale_result else None,
                    "tables": tables,
                    "hypertables": hypertables,
                    "database_size": size_result,
                    "kline_count": kline_count,
                    "connection_string": str(engine.url).replace(
                        settings.POSTGRES_PASSWORD, "****" if settings.POSTGRES_PASSWORD else ""
                    )
                }
                self._log("数据库连接测试成功", "success")
                
        except Exception as e:
            error_msg = f"数据库连接测试失败: {str(e)}"
            result["error"] = error_msg
            self._log(error_msg, "error")
            if self.verbose:
                traceback.print_exc()
        
        result["duration"] = round(time.time() - start_time, 3)
        return result
    
    async def test_redis_connection(self) -> Dict[str, Any]:
        """测试Redis连接"""
        self._log("测试Redis连接...")
        start_time = time.time()
        result = {
            "name": "Redis连接测试",
            "status": "失败",
            "details": {},
            "error": None
        }
        
        try:
            # 从REDIS_URL解析连接参数
            redis_url = settings.REDIS_URL
            
            # 创建Redis客户端
            self.redis_client = redis.from_url(redis_url)
            
            # 测试连接
            ping_result = self.redis_client.ping()
            
            # 获取Redis信息
            info = self.redis_client.info()
            
            # 获取内存使用情况
            memory_info = self.redis_client.info("memory")
            
            # 获取客户端列表
            clients = self.redis_client.info("clients")
            
            # 测试写入和读取
            test_key = "system_check_test_key"
            test_value = f"test_value_{datetime.datetime.now().timestamp()}"
            self.redis_client.set(test_key, test_value, ex=60)  # 60秒过期
            read_value = self.redis_client.get(test_key)
            read_value = read_value.decode() if read_value else None
            
            # 获取Celery相关键
            celery_keys = []
            for key in self.redis_client.scan_iter("celery*"):
                celery_keys.append(key.decode())
            
            result["status"] = "成功"
            result["details"] = {
                "ping": ping_result,
                "version": info.get("redis_version"),
                "uptime_days": round(info.get("uptime_in_seconds", 0) / 86400, 2),
                "memory_used": memory_info.get("used_memory_human"),
                "memory_peak": memory_info.get("used_memory_peak_human"),
                "connected_clients": clients.get("connected_clients"),
                "test_write_read": read_value == test_value,
                "celery_keys_count": len(celery_keys),
                "celery_keys": celery_keys[:5] + ["..."] if len(celery_keys) > 5 else celery_keys,
                "connection_string": redis_url.replace(
                    redis_url.split("@")[0].split(":")[-1], "****" if "@" in redis_url else redis_url
                ) if ":" in redis_url else redis_url
            }
            self._log("Redis连接测试成功", "success")
            
        except Exception as e:
            error_msg = f"Redis连接测试失败: {str(e)}"
            result["error"] = error_msg
            self._log(error_msg, "error")
            if self.verbose:
                traceback.print_exc()
        
        result["duration"] = round(time.time() - start_time, 3)
        return result
    
    async def test_okx_api(self) -> Dict[str, Any]:
        """测试OKX API连接"""
        self._log("测试OKX API连接...")
        start_time = time.time()
        result = {
            "name": "OKX API连接测试",
            "status": "失败",
            "details": {},
            "error": None
        }
        
        try:
            # 创建API凭证
            credentials = ApiCredential(
                api_key=settings.OKX_API_KEY,
                api_secret=settings.OKX_API_SECRET,
                passphrase=settings.OKX_PASSPHRASE
            )
            
            # 检查凭证是否完整
            if not all([credentials.api_key, credentials.api_secret, credentials.passphrase]):
                result["error"] = "API凭证不完整，请检查环境变量配置"
                self._log(result["error"], "error")
                result["duration"] = round(time.time() - start_time, 3)
                return result
            
            # 创建交易所客户端
            exchange_client = create_exchange(
                exchange_type=ExchangeType.OKX,
                credentials=credentials,
                test_mode=settings.DEBUG_MODE
            )
            
            # 测试API连接
            server_time = await exchange_client.get_server_time()
            
            # 获取账户信息
            account_info = await exchange_client.get_account_balance()
            
            # 获取ETH-USDT-SWAP的K线数据
            klines = await exchange_client.get_klines(
                symbol="ETH-USDT-SWAP",
                interval="1m",
                limit=5
            )
            
            # 关闭客户端
            await exchange_client.close()
            
            result["status"] = "成功"
            result["details"] = {
                "server_time": server_time,
                "server_time_diff_seconds": abs(int(time.time() * 1000) - server_time) / 1000,
                "account_info": {
                    "total_equity": account_info.total_equity,
                    "available_balance": account_info.available_balance,
                    "margin_balance": account_info.margin_balance,
                    "unrealized_pnl": account_info.unrealized_pnl
                },
                "klines_count": len(klines),
                "latest_kline": {
                    "symbol": klines[-1].symbol,
                    "interval": klines[-1].interval,
                    "open_time": klines[-1].open_time.isoformat(),
                    "close": float(klines[-1].close),
                    "volume": float(klines[-1].volume)
                } if klines else None,
                "test_mode": settings.DEBUG_MODE
            }
            self._log("OKX API连接测试成功", "success")
            
        except Exception as e:
            error_msg = f"OKX API连接测试失败: {str(e)}"
            result["error"] = error_msg
            self._log(error_msg, "error")
            if self.verbose:
                traceback.print_exc()
        
        result["duration"] = round(time.time() - start_time, 3)
        return result
    
    async def test_celery_status(self) -> Dict[str, Any]:
        """测试Celery任务队列状态"""
        self._log("测试Celery任务队列状态...")
        start_time = time.time()
        result = {
            "name": "Celery任务队列状态检查",
            "status": "失败",
            "details": {},
            "error": None
        }
        
        try:
            # 创建Celery应用
            self.celery_app = Celery("rsi_tracker")
            self.celery_app.conf.broker_url = settings.REDIS_URL
            self.celery_app.conf.result_backend = settings.REDIS_URL
            
            # 获取控制接口
            control = Control(self.celery_app)
            
            # 检查活跃的worker
            active_workers = control.inspect().active()
            
            # 检查已注册的任务
            registered_tasks = control.inspect().registered()
            
            # 检查计划任务
            scheduled_tasks = control.inspect().scheduled()
            
            # 检查保留任务
            reserved_tasks = control.inspect().reserved()
            
            # 检查活跃任务
            active_tasks = control.inspect().active()
            
            # 检查队列状态
            stats = control.inspect().stats()
            
            # 从Redis获取Celery任务状态
            task_states = {}
            if self.redis_client:
                for key in self.redis_client.scan_iter("celery-task-meta-*"):
                    try:
                        value = self.redis_client.get(key)
                        if value:
                            state = json.loads(value)
                            task_id = key.decode().replace("celery-task-meta-", "")
                            task_states[task_id] = {
                                "status": state.get("status"),
                                "result": state.get("result"),
                                "traceback": state.get("traceback")
                            }
                    except:
                        pass
            
            result["status"] = "成功" if active_workers else "警告"
            result["details"] = {
                "active_workers": active_workers,
                "workers_count": len(active_workers) if active_workers else 0,
                "registered_tasks": registered_tasks,
                "registered_tasks_count": sum(len(tasks) for worker, tasks in registered_tasks.items()) if registered_tasks else 0,
                "scheduled_tasks": scheduled_tasks,
                "scheduled_tasks_count": sum(len(tasks) for worker, tasks in scheduled_tasks.items()) if scheduled_tasks else 0,
                "reserved_tasks": reserved_tasks,
                "active_tasks": active_tasks,
                "stats": stats,
                "recent_task_states": {k: task_states[k] for k in list(task_states.keys())[:5]} if task_states else {}
            }
            
            if not active_workers:
                result["error"] = "没有活跃的Celery Worker"
                self._log(result["error"], "warning")
            else:
                self._log("Celery任务队列状态检查成功", "success")
            
        except Exception as e:
            error_msg = f"Celery任务队列状态检查失败: {str(e)}"
            result["error"] = error_msg
            self._log(error_msg, "error")
            if self.verbose:
                traceback.print_exc()
        
        result["duration"] = round(time.time() - start_time, 3)
        return result
    
    async def check_system_health(self) -> Dict[str, Any]:
        """检查系统健康状态"""
        self._log("评估系统健康状态...")
        start_time = time.time()
        result = {
            "name": "系统健康度评估",
            "status": "未知",
            "details": {},
            "error": None
        }
        
        try:
            # 获取系统资源使用情况
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # 获取数据库统计信息
            db_stats = {}
            try:
                db = next(get_db())
                
                # 获取K线数据统计
                kline_count = db.query(func.count(Kline.id)).scalar()
                latest_kline = db.query(Kline).order_by(Kline.timestamp.desc()).first()
                
                # 获取账户统计
                account_count = db.query(func.count(TradingAccount.id)).scalar()
                active_account_count = db.query(func.count(TradingAccount.id)).filter(
                    TradingAccount.is_active == True
                ).scalar()
                
                # 获取策略统计
                strategy_count = db.query(func.count(StrategyState.id)).scalar()
                active_strategy_count = db.query(func.count(StrategyState.id)).filter(
                    StrategyState.is_active == True
                ).scalar()
                
                # 获取持仓统计
                position_count = db.query(func.count(Position.id)).scalar()
                
                # 获取交易统计
                trade_count = db.query(func.count(Trade.id)).scalar()
                
                db_stats = {
                    "kline_count": kline_count,
                    "latest_kline_time": latest_kline.timestamp.isoformat() if latest_kline else None,
                    "kline_freshness_seconds": (datetime.datetime.utcnow() - latest_kline.timestamp).total_seconds() if latest_kline else None,
                    "account_count": account_count,
                    "active_account_count": active_account_count,
                    "strategy_count": strategy_count,
                    "active_strategy_count": active_strategy_count,
                    "position_count": position_count,
                    "trade_count": trade_count
                }
                
                db.close()
            except Exception as e:
                self._log(f"获取数据库统计信息失败: {e}", "warning")
            
            # 计算健康分数 (0-100)
            health_score = 100
            health_factors = []
            
            # 系统资源因素 (最多扣30分)
            if cpu_percent > 90:
                health_score -= 15
                health_factors.append(f"CPU使用率过高: {cpu_percent}%")
            elif cpu_percent > 75:
                health_score -= 5
                health_factors.append(f"CPU使用率较高: {cpu_percent}%")
                
            if memory.percent > 90:
                health_score -= 15
                health_factors.append(f"内存使用率过高: {memory.percent}%")
            elif memory.percent > 75:
                health_score -= 5
                health_factors.append(f"内存使用率较高: {memory.percent}%")
                
            if disk.percent > 90:
                health_score -= 15
                health_factors.append(f"磁盘使用率过高: {disk.percent}%")
            elif disk.percent > 75:
                health_score -= 5
                health_factors.append(f"磁盘使用率较高: {disk.percent}%")
            
            # 数据库因素 (最多扣20分)
            if "kline_freshness_seconds" in db_stats and db_stats["kline_freshness_seconds"] is not None:
                if db_stats["kline_freshness_seconds"] > 3600:  # 1小时
                    health_score -= 20
                    health_factors.append(f"K线数据过期: {db_stats['kline_freshness_seconds'] // 60} 分钟")
                elif db_stats["kline_freshness_seconds"] > 300:  # 5分钟
                    health_score -= 10
                    health_factors.append(f"K线数据较旧: {db_stats['kline_freshness_seconds'] // 60} 分钟")
            
            # 服务连接因素 (最多扣50分)
            for test_name, test_result in self.results["tests"].items():
                if test_result["status"] == "失败":
                    if "数据库" in test_name:
                        health_score -= 30
                        health_factors.append(f"{test_name}失败")
                    elif "Redis" in test_name:
                        health_score -= 20
                        health_factors.append(f"{test_name}失败")
                    elif "OKX API" in test_name:
                        health_score -= 30
                        health_factors.append(f"{test_name}失败")
                    elif "Celery" in test_name:
                        health_score -= 20
                        health_factors.append(f"{test_name}失败")
                elif test_result["status"] == "警告":
                    health_score -= 10
                    health_factors.append(f"{test_name}警告")
            
            # 确保分数在0-100之间
            health_score = max(0, min(100, health_score))
            
            # 确定整体状态
            if health_score >= 90:
                overall_status = "优良"
            elif health_score >= 70:
                overall_status = "良好"
            elif health_score >= 50:
                overall_status = "一般"
            elif health_score >= 30:
                overall_status = "较差"
            else:
                overall_status = "危险"
            
            result["status"] = "成功"
            result["details"] = {
                "cpu_usage_percent": cpu_percent,
                "memory_usage_percent": memory.percent,
                "memory_used_gb": round(memory.used / (1024**3), 2),
                "memory_total_gb": round(memory.total / (1024**3), 2),
                "disk_usage_percent": disk.percent,
                "disk_used_gb": round(disk.used / (1024**3), 2),
                "disk_total_gb": round(disk.total / (1024**3), 2),
                "db_stats": db_stats,
                "health_score": health_score,
                "health_factors": health_factors,
                "overall_status": overall_status
            }
            
            # 更新全局结果
            self.results["health_score"] = health_score
            self.results["overall_status"] = overall_status
            
            self._log(f"系统健康度评估完成: {health_score}/100 ({overall_status})", 
                     "success" if health_score >= 70 else "warning" if health_score >= 50 else "error")
            
        except Exception as e:
            error_msg = f"系统健康度评估失败: {str(e)}"
            result["error"] = error_msg
            self._log(error_msg, "error")
            if self.verbose:
                traceback.print_exc()
        
        result["duration"] = round(time.time() - start_time, 3)
        return result
    
    async def run_all_tests(self):
        """运行所有测试"""
        self._log(f"{Colors.HEADER}{Colors.BOLD}开始系统状态检测...{Colors.ENDC}")
        
        # 运行数据库连接测试
        self.results["tests"]["database"] = await self.test_database_connection()
        
        # 运行Redis连接测试
        self.results["tests"]["redis"] = await self.test_redis_connection()
        
        # 运行OKX API连接测试
        self.results["tests"]["okx_api"] = await self.test_okx_api()
        
        # 运行Celery任务队列状态检查
        self.results["tests"]["celery"] = await self.test_celery_status()
        
        # 评估系统健康状态
        self.results["tests"]["health"] = await self.check_system_health()
        
        # 计算总耗时
        total_duration = sum(test["duration"] for test in self.results["tests"].values())
        self.results["total_duration"] = round(total_duration, 3)
        
        self._log(f"{Colors.HEADER}{Colors.BOLD}系统状态检测完成 ({self.results['total_duration']}秒){Colors.ENDC}")
        
        return self.results
    
    def generate_report(self, output_file: Optional[str] = None) -> str:
        """生成详细报告"""
        report = []
        
        # 添加标题
        report.append("=" * 80)
        report.append(f"RSI分层极值追踪自动量化交易系统 - 系统状态报告")
        report.append(f"生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("=" * 80)
        
        # 添加系统信息
        report.append("\n系统信息:")
        report.append("-" * 40)
        for key, value in self.results["system_info"].items():
            report.append(f"{key}: {value}")
        
        # 添加健康状态摘要
        report.append("\n健康状态摘要:")
        report.append("-" * 40)
        report.append(f"健康得分: {self.results['health_score']}/100")
        report.append(f"整体状态: {self.results['overall_status']}")
        
        if "health" in self.results["tests"] and "details" in self.results["tests"]["health"]:
            health_details = self.results["tests"]["health"]["details"]
            if "health_factors" in health_details and health_details["health_factors"]:
                report.append("\n影响因素:")
                for factor in health_details["health_factors"]:
                    report.append(f"- {factor}")
        
        # 添加测试结果摘要
        report.append("\n测试结果摘要:")
        report.append("-" * 40)
        for test_name, test_result in self.results["tests"].items():
            if test_name != "health":  # 健康状态已经单独显示
                status_str = test_result["status"]
                duration_str = f"{test_result['duration']}秒"
                report.append(f"{test_result['name']}: {status_str} ({duration_str})")
                if test_result["error"]:
                    report.append(f"  错误: {test_result['error']}")
        
        # 添加详细测试结果
        report.append("\n详细测试结果:")
        report.append("=" * 80)
        
        # 数据库连接测试详情
        if "database" in self.results["tests"]:
            db_test = self.results["tests"]["database"]
            report.append("\n数据库连接测试:")
            report.append("-" * 40)
            report.append(f"状态: {db_test['status']}")
            report.append(f"耗时: {db_test['duration']}秒")
            
            if db_test["error"]:
                report.append(f"错误: {db_test['error']}")
            
            if "details" in db_test and db_test["details"]:
                details = db_test["details"]
                report.append(f"数据库版本: {details.get('version', '未知')}")
                report.append(f"TimescaleDB安装: {'是' if details.get('timescale_installed') else '否'}")
                report.append(f"TimescaleDB版本: {details.get('timescale_version', '未知')}")
                report.append(f"数据库大小: {details.get('database_size', '未知')}")
                report.append(f"K线数据量: {details.get('kline_count', 0)}")
                
                report.append("\n表列表:")
                for table in details.get("tables", []):
                    report.append(f"- {table}")
                
                report.append("\n超表列表:")
                for hypertable in details.get("hypertables", []):
                    report.append(f"- {hypertable}")
        
        # Redis连接测试详情
        if "redis" in self.results["tests"]:
            redis_test = self.results["tests"]["redis"]
            report.append("\nRedis连接测试:")
            report.append("-" * 40)
            report.append(f"状态: {redis_test['status']}")
            report.append(f"耗时: {redis_test['duration']}秒")
            
            if redis_test["error"]:
                report.append(f"错误: {redis_test['error']}")
            
            if "details" in redis_test and redis_test["details"]:
                details = redis_test["details"]
                report.append(f"Redis版本: {details.get('version', '未知')}")
                report.append(f"运行时间: {details.get('uptime_days', '未知')} 天")
                report.append(f"内存使用: {details.get('memory_used', '未知')}")
                report.append(f"内存峰值: {details.get('memory_peak', '未知')}")
                report.append(f"连接客户端数: {details.get('connected_clients', '未知')}")
                report.append(f"读写测试: {'成功' if details.get('test_write_read') else '失败'}")
                report.append(f"Celery键数量: {details.get('celery_keys_count', 0)}")
        
        # OKX API连接测试详情
        if "okx_api" in self.results["tests"]:
            api_test = self.results["tests"]["okx_api"]
            report.append("\nOKX API连接测试:")
            report.append("-" * 40)
            report.append(f"状态: {api_test['status']}")
            report.append(f"耗时: {api_test['duration']}秒")
            
            if api_test["error"]:
                report.append(f"错误: {api_test['error']}")
            
            if "details" in api_test and api_test["details"]:
                details = api_test["details"]
                report.append(f"服务器时间: {details.get('server_time', '未知')}")
                report.append(f"时间差异: {details.get('server_time_diff_seconds', '未知')} 秒")
                report.append(f"测试模式: {'是' if details.get('test_mode') else '否'}")
                
                if "account_info" in details:
                    account = details["account_info"]
                    report.append("\n账户信息:")
                    report.append(f"- 总权益: {account.get('total_equity', '未知')} USDT")
                    report.append(f"- 可用余额: {account.get('available_balance', '未知')} USDT")
                    report.append(f"- 保证金余额: {account.get('margin_balance', '未知')} USDT")
                    report.append(f"- 未实现盈亏: {account.get('unrealized_pnl', '未知')} USDT")
                
                if "latest_kline" in details and details["latest_kline"]:
                    kline = details["latest_kline"]
                    report.append("\n最新K线数据:")
                    report.append(f"- 交易对: {kline.get('symbol', '未知')}")
                    report.append(f"- 时间间隔: {kline.get('interval', '未知')}")
                    report.append(f"- 开盘时间: {kline.get('open_time', '未知')}")
                    report.append(f"- 收盘价: {kline.get('close', '未知')}")
                    report.append(f"- 成交量: {kline.get('volume', '未知')}")
        
        # Celery任务队列状态检查详情
        if "celery" in self.results["tests"]:
            celery_test = self.results["tests"]["celery"]
            report.append("\nCelery任务队列状态检查:")
            report.append("-" * 40)
            report.append(f"状态: {celery_test['status']}")
            report.append(f"耗时: {celery_test['duration']}秒")
            
            if celery_test["error"]:
                report.append(f"错误: {celery_test['error']}")
            
            if "details" in celery_test and celery_test["details"]:
                details = celery_test["details"]
                report.append(f"活跃Worker数: {details.get('workers_count', 0)}")
                report.append(f"注册任务数: {details.get('registered_tasks_count', 0)}")
                report.append(f"计划任务数: {details.get('scheduled_tasks_count', 0)}")
                
                if details.get("active_workers"):
                    report.append("\n活跃Worker:")
                    for worker, tasks in details["active_workers"].items():
                        report.append(f"- {worker}: {len(tasks)} 个活跃任务")
        
        # 系统健康度评估详情
        if "health" in self.results["tests"]:
            health_test = self.results["tests"]["health"]
            report.append("\n系统健康度评估:")
            report.append("-" * 40)
            report.append(f"状态: {health_test['status']}")
            report.append(f"耗时: {health_test['duration']}秒")
            
            if health_test["error"]:
                report.append(f"错误: {health_test['error']}")
            
            if "details" in health_test and health_test["details"]:
                details = health_test["details"]
                report.append(f"CPU使用率: {details.get('cpu_usage_percent', '未知')}%")
                report.append(f"内存使用率: {details.get('memory_usage_percent', '未知')}% ({details.get('memory_used_gb', '未知')}/{details.get('memory_total_gb', '未知')} GB)")
                report.append(f"磁盘使用率: {details.get('disk_usage_percent', '未知')}% ({details.get('disk_used_gb', '未知')}/{details.get('disk_total_gb', '未知')} GB)")
                
                if "db_stats" in details and details["db_stats"]:
                    db_stats = details["db_stats"]
                    report.append("\n数据库统计:")
                    report.append(f"- K线数据量: {db_stats.get('kline_count', 0)}")
                    report.append(f"- 最新K线时间: {db_stats.get('latest_kline_time', '未知')}")
                    report.append(f"- K线数据新鲜度: {db_stats.get('kline_freshness_seconds', '未知')} 秒")
                    report.append(f"- 账户总数: {db_stats.get('account_count', 0)}")
                    report.append(f"- 活跃账户数: {db_stats.get('active_account_count', 0)}")
                    report.append(f"- 策略总数: {db_stats.get('strategy_count', 0)}")
                    report.append(f"- 活跃策略数: {db_stats.get('active_strategy_count', 0)}")
                    report.append(f"- 持仓数量: {db_stats.get('position_count', 0)}")
                    report.append(f"- 交易记录数: {db_stats.get('trade_count', 0)}")
        
        # 添加结尾
        report.append("\n" + "=" * 80)
        report.append("报告生成完成")
        report.append(f"总耗时: {self.results['total_duration']}秒")
        report.append("=" * 80)
        
        # 合并报告
        report_text = "\n".join(report)
        
        # 保存到文件
        if output_file:
            try:
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(report_text)
                print(f"\n报告已保存至: {output_file}")
            except Exception as e:
                print(f"\n保存报告失败: {e}")
        
        return report_text
    
    def generate_charts(self, output_dir: str = "reports"):
        """生成图表"""
        try:
            # 创建输出目录
            os.makedirs(output_dir, exist_ok=True)
            
            # 生成健康度饼图
            plt.figure(figsize=(10, 6))
            plt.pie(
                [self.results["health_score"], 100 - self.results["health_score"]],
                labels=["健康", "问题"],
                colors=["#4CAF50", "#F44336"],
                autopct='%1.1f%%',
                startangle=90
            )
            plt.title(f"系统健康度: {self.results['health_score']}/100 ({self.results['overall_status']})")
            plt.axis('equal')
            plt.tight_layout()
            health_chart_path = os.path.join(output_dir, "health_score.png")
            plt.savefig(health_chart_path)
            plt.close()
            
            # 生成测试结果柱状图
            test_names = []
            durations = []
            colors = []
            
            for test_name, test_result in self.results["tests"].items():
                if test_name != "health":  # 健康状态已经单独显示
                    test_names.append(test_result["name"])
                    durations.append(test_result["duration"])
                    if test_result["status"] == "成功":
                        colors.append("#4CAF50")  # 绿色
                    elif test_result["status"] == "警告":
                        colors.append("#FFC107")  # 黄色
                    else:
                        colors.append("#F44336")  # 红色
            
            plt.figure(figsize=(10, 6))
            bars = plt.bar(test_names, durations, color=colors)
            plt.title("测试执行时间")
            plt.ylabel("耗时 (秒)")
            plt.xticks(rotation=45, ha="right")
            
            # 添加数值标签
            for bar in bars:
                height = bar.get_height()
                plt.text(
                    bar.get_x() + bar.get_width() / 2.,
                    height + 0.02,
                    f"{height:.2f}s",
                    ha="center", va="bottom"
                )
            
            plt.tight_layout()
            duration_chart_path = os.path.join(output_dir, "test_durations.png")
            plt.savefig(duration_chart_path)
            plt.close()
            
            print(f"\n图表已保存至: {output_dir}/")
            return [health_chart_path, duration_chart_path]
            
        except Exception as e:
            print(f"\n生成图表失败: {e}")
            if self.verbose:
                traceback.print_exc()
            return []


async def main():
    """主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="RSI分层极值追踪自动量化交易系统 - 系统状态检测脚本")
    parser.add_argument("--verbose", action="store_true", help="显示详细输出")
    parser.add_argument("--output-file", type=str, help="将报告保存到指定文件")
    parser.add_argument("--generate-charts", action="store_true", help="生成图表")
    parser.add_argument("--output-dir", type=str, default="reports", help="图表输出目录")
    args = parser.parse_args()
    
    # 创建系统检测器
    checker = SystemChecker(verbose=args.verbose)
    
    # 运行所有测试
    results = await checker.run_all_tests()
    
    # 生成报告
    report = checker.generate_report(args.output_file)
    
    # 打印报告
    print("\n" + report)
    
    # 生成图表
    if args.generate_charts:
        checker.generate_charts(args.output_dir)


if __name__ == "__main__":
    # 运行主函数
    asyncio.run(main())
