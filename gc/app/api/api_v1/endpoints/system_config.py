"""
系统配置管理API端点

该模块提供以下功能：
- 获取环境变量配置
- 更新环境变量配置
- 测试数据库、Redis和交易所API连接
- 重启服务
- 系统状态检查
- 配置验证
"""

import os
import re
import json
import subprocess
import asyncio
import logging
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator, root_validator

from sqlalchemy.orm import Session
from redis import Redis
import psutil

from app.core.config import settings
from app.core.security import get_current_active_superuser
from app.database import get_db, engine
from app.api import deps
from app.exchange import ApiCredential, create_exchange, ExchangeType
from app.utils.env_manager import load_env_file, update_env_file, encrypt_value, decrypt_value

# 设置日志
logger = logging.getLogger(__name__)

# 创建路由
router = APIRouter()

# 定义模型
class ExchangeConfig(BaseModel):
    """交易所配置模型"""
    okx_api_key: str = Field(..., description="OKX API Key")
    okx_api_secret: str = Field(..., description="OKX API Secret")
    okx_passphrase: str = Field(..., description="OKX API Passphrase")
    okx_max_leverage: int = Field(50, description="最大杠杆倍数", ge=1, le=125)
    debug_mode: bool = Field(True, description="是否启用沙箱模式")


class DatabaseConfig(BaseModel):
    """数据库配置模型"""
    postgres_host: str = Field(..., description="数据库主机")
    postgres_port: int = Field(5432, description="数据库端口", ge=1, le=65535)
    postgres_db: str = Field(..., description="数据库名称")
    postgres_user: str = Field(..., description="数据库用户名")
    postgres_password: str = Field(..., description="数据库密码")
    data_retention_days: int = Field(7, description="数据保留天数", ge=1, le=365)


class RedisConfig(BaseModel):
    """Redis配置模型"""
    redis_host: str = Field(..., description="Redis主机")
    redis_port: int = Field(6379, description="Redis端口", ge=1, le=65535)
    redis_password: str = Field("", description="Redis密码")
    redis_db: int = Field(0, description="Redis数据库", ge=0, le=15)


class StrategyConfig(BaseModel):
    """策略配置模型"""
    rsi_period: int = Field(14, description="RSI周期", ge=5, le=30)
    long_levels: str = Field("30,25,20", description="多头RSI级别，逗号分隔")
    short_levels: str = Field("70,75,80", description="空头RSI级别，逗号分隔")
    retracement_points: int = Field(10, description="回撤点数", ge=1, le=100)
    max_additional_positions: int = Field(3, description="最大加仓次数", ge=0, le=10)
    fixed_stop_loss_points: int = Field(50, description="固定止损点数", ge=0, le=1000)
    profit_taking_config: str = Field(
        '[{"profit_rate": 0.03, "position_rate": 0.5}, {"profit_rate": 0.05, "position_rate": 1.0}]',
        description="分批止盈配置，JSON格式"
    )
    max_holding_candles: int = Field(1440, description="最大持仓K线数", ge=0, le=10000)
    cooling_candles: int = Field(10, description="冷却K线数", ge=0, le=100)
    
    @validator('profit_taking_config')
    def validate_profit_taking_config(cls, v):
        try:
            config = json.loads(v)
            if not isinstance(config, list):
                raise ValueError("分批止盈配置必须是数组格式")
            
            for item in config:
                if not isinstance(item, dict) or 'profit_rate' not in item or 'position_rate' not in item:
                    raise ValueError("每个配置项必须包含profit_rate和position_rate字段")
            
            return v
        except json.JSONDecodeError:
            raise ValueError("JSON格式错误")
    
    @validator('long_levels', 'short_levels')
    def validate_levels(cls, v):
        pattern = re.compile(r'^\d+(,\d+)*$')
        if not pattern.match(v):
            raise ValueError("格式错误，应为逗号分隔的数字，如：30,25,20")
        return v


class SystemConfig(BaseModel):
    """系统配置模型"""
    app_name: str = Field("RSI分层极值追踪量化系统", description="系统名称")
    api_secret_key: str = Field(..., description="API密钥")
    log_level: str = Field("INFO", description="日志级别")
    allow_registration: bool = Field(False, description="是否允许注册")
    enable_auto_backup: bool = Field(True, description="是否启用自动备份")
    backup_interval_hours: int = Field(24, description="备份频率(小时)", ge=1, le=168)
    backup_keep_count: int = Field(7, description="备份保留数量", ge=1, le=100)
    backup_dir: str = Field("/app/backup", description="备份目录")


class EnvConfig(BaseModel):
    """环境变量配置模型"""
    exchange: ExchangeConfig
    database: DatabaseConfig
    redis: RedisConfig
    strategy: StrategyConfig
    system: SystemConfig


class ConnectionTestRequest(BaseModel):
    """连接测试请求模型"""
    type: str = Field(..., description="连接类型：exchange, database, redis")
    config: Dict[str, Any] = Field(..., description="连接配置")


class ConnectionTestResponse(BaseModel):
    """连接测试响应模型"""
    success: bool = Field(..., description="测试是否成功")
    message: str = Field(..., description="测试结果消息")
    details: Optional[Dict[str, Any]] = Field(None, description="详细信息")


class SystemStatusResponse(BaseModel):
    """系统状态响应模型"""
    status: str = Field(..., description="系统状态")
    uptime: int = Field(..., description="系统运行时间(秒)")
    cpu_usage: float = Field(..., description="CPU使用率(%)")
    memory_usage: Dict[str, Any] = Field(..., description="内存使用情况")
    disk_usage: Dict[str, Any] = Field(..., description="磁盘使用情况")
    services: Dict[str, Any] = Field(..., description="服务状态")
    database: Dict[str, Any] = Field(..., description="数据库状态")
    redis: Dict[str, Any] = Field(..., description="Redis状态")
    last_backup: Optional[Dict[str, Any]] = Field(None, description="最后备份信息")


class RestartRequest(BaseModel):
    """重启服务请求模型"""
    services: List[str] = Field(["api", "worker", "beat"], description="要重启的服务列表")
    force: bool = Field(False, description="是否强制重启")


class RestartResponse(BaseModel):
    """重启服务响应模型"""
    success: bool = Field(..., description="重启是否成功")
    message: str = Field(..., description="重启结果消息")
    details: Optional[Dict[str, Any]] = Field(None, description="详细信息")


# 辅助函数
def get_env_config() -> Dict[str, Any]:
    """
    获取环境变量配置
    
    Returns:
        Dict[str, Any]: 环境变量配置
    """
    # 获取.env文件路径
    env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), ".env")
    
    # 读取.env文件
    env_data = load_env_file(env_file)
    
    # 解析配置
    config = {
        "exchange": {
            "okx_api_key": env_data.get("OKX_API_KEY", ""),
            "okx_api_secret": env_data.get("OKX_API_SECRET", ""),
            "okx_passphrase": env_data.get("OKX_PASSPHRASE", ""),
            "okx_max_leverage": int(env_data.get("OKX_MAX_LEVERAGE", "50")),
            "debug_mode": env_data.get("DEBUG_MODE", "true").lower() in ("true", "1", "yes")
        },
        "database": {
            "postgres_host": env_data.get("POSTGRES_HOST", "postgres"),
            "postgres_port": int(env_data.get("POSTGRES_PORT", "5432")),
            "postgres_db": env_data.get("POSTGRES_DB", "rsi_tracker"),
            "postgres_user": env_data.get("POSTGRES_USER", "postgres"),
            "postgres_password": env_data.get("POSTGRES_PASSWORD", ""),
            "data_retention_days": int(env_data.get("DATA_RETENTION_DAYS", "7"))
        },
        "redis": {
            "redis_host": env_data.get("REDIS_HOST", "redis"),
            "redis_port": int(env_data.get("REDIS_PORT", "6379")),
            "redis_password": env_data.get("REDIS_PASSWORD", ""),
            "redis_db": int(env_data.get("REDIS_DB", "0"))
        },
        "strategy": {
            "rsi_period": int(env_data.get("RSI_PERIOD", "14")),
            "long_levels": env_data.get("LONG_LEVELS", "30,25,20"),
            "short_levels": env_data.get("SHORT_LEVELS", "70,75,80"),
            "retracement_points": int(env_data.get("RETRACEMENT_POINTS", "10")),
            "max_additional_positions": int(env_data.get("MAX_ADDITIONAL_POSITIONS", "3")),
            "fixed_stop_loss_points": int(env_data.get("FIXED_STOP_LOSS_POINTS", "50")),
            "profit_taking_config": env_data.get("PROFIT_TAKING_CONFIG", '[{"profit_rate": 0.03, "position_rate": 0.5}, {"profit_rate": 0.05, "position_rate": 1.0}]'),
            "max_holding_candles": int(env_data.get("MAX_HOLDING_CANDLES", "1440")),
            "cooling_candles": int(env_data.get("COOLING_CANDLES", "10"))
        },
        "system": {
            "app_name": env_data.get("APP_NAME", "RSI分层极值追踪量化系统"),
            "api_secret_key": env_data.get("API_SECRET_KEY", ""),
            "log_level": env_data.get("LOG_LEVEL", "INFO"),
            "allow_registration": env_data.get("ALLOW_REGISTRATION", "false").lower() in ("true", "1", "yes"),
            "enable_auto_backup": env_data.get("ENABLE_AUTO_BACKUP", "true").lower() in ("true", "1", "yes"),
            "backup_interval_hours": int(env_data.get("BACKUP_INTERVAL_HOURS", "24")),
            "backup_keep_count": int(env_data.get("BACKUP_KEEP_COUNT", "7")),
            "backup_dir": env_data.get("BACKUP_DIR", "/app/backup")
        }
    }
    
    # 解密敏感信息
    if config["exchange"]["okx_api_key"].startswith("enc:"):
        config["exchange"]["okx_api_key"] = decrypt_value(config["exchange"]["okx_api_key"][4:])
    
    if config["exchange"]["okx_api_secret"].startswith("enc:"):
        config["exchange"]["okx_api_secret"] = decrypt_value(config["exchange"]["okx_api_secret"][4:])
    
    if config["exchange"]["okx_passphrase"].startswith("enc:"):
        config["exchange"]["okx_passphrase"] = decrypt_value(config["exchange"]["okx_passphrase"][4:])
    
    if config["database"]["postgres_password"].startswith("enc:"):
        config["database"]["postgres_password"] = decrypt_value(config["database"]["postgres_password"][4:])
    
    if config["redis"]["redis_password"].startswith("enc:"):
        config["redis"]["redis_password"] = decrypt_value(config["redis"]["redis_password"][4:])
    
    if config["system"]["api_secret_key"].startswith("enc:"):
        config["system"]["api_secret_key"] = decrypt_value(config["system"]["api_secret_key"][4:])
    
    return config


def update_env_config_file(config: Dict[str, Any]) -> bool:
    """
    更新环境变量配置文件
    
    Args:
        config: 配置数据
        
    Returns:
        bool: 是否成功
    """
    # 获取.env文件路径
    env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), ".env")
    
    # 准备更新数据
    update_data = {}
    
    # 交易所配置
    if "exchange" in config:
        exchange = config["exchange"]
        # 加密敏感信息
        update_data["OKX_API_KEY"] = f"enc:{encrypt_value(exchange['okx_api_key'])}"
        update_data["OKX_API_SECRET"] = f"enc:{encrypt_value(exchange['okx_api_secret'])}"
        update_data["OKX_PASSPHRASE"] = f"enc:{encrypt_value(exchange['okx_passphrase'])}"
        update_data["OKX_MAX_LEVERAGE"] = str(exchange["okx_max_leverage"])
        update_data["DEBUG_MODE"] = "true" if exchange["debug_mode"] else "false"
    
    # 数据库配置
    if "database" in config:
        database = config["database"]
        update_data["POSTGRES_HOST"] = database["postgres_host"]
        update_data["POSTGRES_PORT"] = str(database["postgres_port"])
        update_data["POSTGRES_DB"] = database["postgres_db"]
        update_data["POSTGRES_USER"] = database["postgres_user"]
        update_data["POSTGRES_PASSWORD"] = f"enc:{encrypt_value(database['postgres_password'])}"
        update_data["DATA_RETENTION_DAYS"] = str(database["data_retention_days"])
    
    # Redis配置
    if "redis" in config:
        redis = config["redis"]
        update_data["REDIS_HOST"] = redis["redis_host"]
        update_data["REDIS_PORT"] = str(redis["redis_port"])
        update_data["REDIS_PASSWORD"] = f"enc:{encrypt_value(redis['redis_password'])}" if redis["redis_password"] else ""
        update_data["REDIS_DB"] = str(redis["redis_db"])
        
        # 更新REDIS_URL
        redis_url = f"redis://"
        if redis["redis_password"]:
            redis_url += f":{redis['redis_password']}@"
        redis_url += f"{redis['redis_host']}:{redis['redis_port']}/{redis['redis_db']}"
        update_data["REDIS_URL"] = redis_url
    
    # 策略配置
    if "strategy" in config:
        strategy = config["strategy"]
        update_data["RSI_PERIOD"] = str(strategy["rsi_period"])
        update_data["LONG_LEVELS"] = strategy["long_levels"]
        update_data["SHORT_LEVELS"] = strategy["short_levels"]
        update_data["RETRACEMENT_POINTS"] = str(strategy["retracement_points"])
        update_data["MAX_ADDITIONAL_POSITIONS"] = str(strategy["max_additional_positions"])
        update_data["FIXED_STOP_LOSS_POINTS"] = str(strategy["fixed_stop_loss_points"])
        update_data["PROFIT_TAKING_CONFIG"] = strategy["profit_taking_config"]
        update_data["MAX_HOLDING_CANDLES"] = str(strategy["max_holding_candles"])
        update_data["COOLING_CANDLES"] = str(strategy["cooling_candles"])
    
    # 系统配置
    if "system" in config:
        system = config["system"]
        update_data["APP_NAME"] = system["app_name"]
        update_data["API_SECRET_KEY"] = f"enc:{encrypt_value(system['api_secret_key'])}"
        update_data["LOG_LEVEL"] = system["log_level"]
        update_data["ALLOW_REGISTRATION"] = "true" if system["allow_registration"] else "false"
        update_data["ENABLE_AUTO_BACKUP"] = "true" if system["enable_auto_backup"] else "false"
        update_data["BACKUP_INTERVAL_HOURS"] = str(system["backup_interval_hours"])
        update_data["BACKUP_KEEP_COUNT"] = str(system["backup_keep_count"])
        update_data["BACKUP_DIR"] = system["backup_dir"]
    
    # 更新.env文件
    try:
        update_env_file(env_file, update_data)
        return True
    except Exception as e:
        logger.error(f"更新环境变量配置文件失败: {e}")
        return False


async def test_database_connection(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    测试数据库连接
    
    Args:
        config: 数据库配置
        
    Returns:
        Dict[str, Any]: 测试结果
    """
    import sqlalchemy
    from sqlalchemy import text
    
    try:
        # 构建连接URL
        url = f"postgresql://{config['postgres_user']}:{config['postgres_password']}@{config['postgres_host']}:{config['postgres_port']}/{config['postgres_db']}"
        
        # 创建引擎
        test_engine = sqlalchemy.create_engine(url)
        
        # 测试连接
        with test_engine.connect() as connection:
            # 检查数据库版本
            version = connection.execute(text("SELECT version();")).scalar()
            
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
            tables = [row[0] for row in connection.execute(tables_query).fetchall()]
            
            # 获取数据库大小
            size_query = text("""
                SELECT pg_size_pretty(pg_database_size(current_database()));
            """)
            size = connection.execute(size_query).scalar()
        
        return {
            "success": True,
            "message": "数据库连接成功",
            "details": {
                "version": version,
                "timescale_installed": timescale_result is not None,
                "timescale_version": timescale_result[0] if timescale_result else None,
                "tables_count": len(tables),
                "tables": tables[:10] + ["..."] if len(tables) > 10 else tables,
                "database_size": size
            }
        }
    except Exception as e:
        logger.error(f"测试数据库连接失败: {e}")
        return {
            "success": False,
            "message": f"数据库连接失败: {str(e)}",
            "details": None
        }


async def test_redis_connection(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    测试Redis连接
    
    Args:
        config: Redis配置
        
    Returns:
        Dict[str, Any]: 测试结果
    """
    try:
        # 创建Redis客户端
        redis_client = Redis(
            host=config["redis_host"],
            port=config["redis_port"],
            password=config["redis_password"] if config["redis_password"] else None,
            db=config["redis_db"],
            socket_timeout=5
        )
        
        # 测试连接
        ping_result = redis_client.ping()
        
        # 获取Redis信息
        info = redis_client.info()
        
        # 获取内存使用情况
        memory_info = redis_client.info("memory")
        
        # 获取客户端列表
        clients = redis_client.info("clients")
        
        # 测试写入和读取
        test_key = f"system_check_test_key_{datetime.now().timestamp()}"
        test_value = f"test_value_{datetime.now().timestamp()}"
        redis_client.set(test_key, test_value, ex=60)  # 60秒过期
        read_value = redis_client.get(test_key)
        read_value = read_value.decode() if read_value else None
        
        # 关闭连接
        redis_client.close()
        
        return {
            "success": True,
            "message": "Redis连接成功",
            "details": {
                "ping": ping_result,
                "version": info.get("redis_version"),
                "uptime_days": round(info.get("uptime_in_seconds", 0) / 86400, 2),
                "memory_used": memory_info.get("used_memory_human"),
                "memory_peak": memory_info.get("used_memory_peak_human"),
                "connected_clients": clients.get("connected_clients"),
                "test_write_read": read_value == test_value
            }
        }
    except Exception as e:
        logger.error(f"测试Redis连接失败: {e}")
        return {
            "success": False,
            "message": f"Redis连接失败: {str(e)}",
            "details": None
        }


async def test_exchange_connection(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    测试交易所API连接
    
    Args:
        config: 交易所配置
        
    Returns:
        Dict[str, Any]: 测试结果
    """
    try:
        # 创建API凭证
        credentials = ApiCredential(
            api_key=config["okx_api_key"],
            api_secret=config["okx_api_secret"],
            passphrase=config["okx_passphrase"]
        )
        
        # 创建交易所客户端
        exchange_client = create_exchange(
            exchange_type=ExchangeType.OKX,
            credentials=credentials,
            test_mode=config["debug_mode"]
        )
        
        # 测试API连接
        server_time = await exchange_client.get_server_time()
        
        # 获取账户信息
        account_info = await exchange_client.get_account_balance()
        
        # 获取ETH-USDT-SWAP的K线数据
        klines = await exchange_client.get_klines(
            symbol="ETH-USDT-SWAP",
            interval="1m",
            limit=1
        )
        
        # 关闭客户端
        await exchange_client.close()
        
        return {
            "success": True,
            "message": "交易所API连接成功",
            "details": {
                "server_time": server_time,
                "server_time_diff_seconds": abs(int(datetime.now().timestamp() * 1000) - server_time) / 1000,
                "account_info": {
                    "total_equity": float(account_info.total_equity),
                    "available_balance": float(account_info.available_balance),
                    "margin_balance": float(account_info.margin_balance),
                    "unrealized_pnl": float(account_info.unrealized_pnl)
                },
                "klines_count": len(klines),
                "test_mode": config["debug_mode"]
            }
        }
    except Exception as e:
        logger.error(f"测试交易所API连接失败: {e}")
        return {
            "success": False,
            "message": f"交易所API连接失败: {str(e)}",
            "details": None
        }


async def get_system_status(db: Session) -> Dict[str, Any]:
    """
    获取系统状态
    
    Args:
        db: 数据库会话
        
    Returns:
        Dict[str, Any]: 系统状态
    """
    try:
        # 系统运行时间
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = (datetime.now() - boot_time).total_seconds()
        
        # CPU使用率
        cpu_usage = psutil.cpu_percent(interval=1)
        
        # 内存使用情况
        memory = psutil.virtual_memory()
        memory_usage = {
            "total_gb": round(memory.total / (1024**3), 2),
            "used_gb": round(memory.used / (1024**3), 2),
            "free_gb": round(memory.available / (1024**3), 2),
            "percent": memory.percent
        }
        
        # 磁盘使用情况
        disk = psutil.disk_usage('/')
        disk_usage = {
            "total_gb": round(disk.total / (1024**3), 2),
            "used_gb": round(disk.used / (1024**3), 2),
            "free_gb": round(disk.free / (1024**3), 2),
            "percent": disk.percent
        }
        
        # 服务状态
        services = {}
        
        # 检查Docker容器状态
        try:
            docker_cmd = ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"]
            docker_output = subprocess.check_output(docker_cmd, universal_newlines=True)
            
            for line in docker_output.strip().split('\n'):
                if not line:
                    continue
                parts = line.split('\t')
                if len(parts) >= 2:
                    name = parts[0]
                    status = parts[1]
                    services[name] = {
                        "status": "running" if "Up" in status else "stopped",
                        "uptime": status
                    }
        except Exception as e:
            logger.error(f"获取Docker容器状态失败: {e}")
            services["error"] = str(e)
        
        # 数据库状态
        database_status = {}
        try:
            with engine.connect() as connection:
                # 数据库版本
                version_query = text("SELECT version();")
                version = connection.execute(version_query).scalar()
                
                # 数据库大小
                size_query = text("SELECT pg_size_pretty(pg_database_size(current_database()));")
                size = connection.execute(size_query).scalar()
                
                # 连接数
                conn_query = text("""
                    SELECT count(*) FROM pg_stat_activity 
                    WHERE datname = current_database();
                """)
                connections = connection.execute(conn_query).scalar()
                
                # 表数量
                tables_query = text("""
                    SELECT count(*) FROM information_schema.tables 
                    WHERE table_schema = 'public';
                """)
                tables_count = connection.execute(tables_query).scalar()
                
                # K线数据量
                klines_query = text("SELECT count(*) FROM kline;")
                try:
                    klines_count = connection.execute(klines_query).scalar()
                except:
                    klines_count = 0
                
                database_status = {
                    "version": version,
                    "size": size,
                    "connections": connections,
                    "tables_count": tables_count,
                    "klines_count": klines_count
                }
        except Exception as e:
            logger.error(f"获取数据库状态失败: {e}")
            database_status["error"] = str(e)
        
        # Redis状态
        redis_status = {}
        try:
            # 从REDIS_URL解析连接参数
            redis_url = settings.REDIS_URL
            
            # 创建Redis客户端
            redis_client = Redis.from_url(redis_url, socket_timeout=5)
            
            # 获取Redis信息
            info = redis_client.info()
            
            redis_status = {
                "version": info.get("redis_version"),
                "uptime_days": round(info.get("uptime_in_seconds", 0) / 86400, 2),
                "memory_used": info.get("used_memory_human"),
                "connected_clients": info.get("connected_clients"),
                "total_commands_processed": info.get("total_commands_processed")
            }
            
            # 关闭连接
            redis_client.close()
        except Exception as e:
            logger.error(f"获取Redis状态失败: {e}")
            redis_status["error"] = str(e)
        
        # 最后备份信息
        last_backup = None
        backup_dir = os.environ.get("BACKUP_DIR", "/app/backup")
        try:
            if os.path.exists(backup_dir):
                backup_files = [f for f in os.listdir(backup_dir) if f.endswith('.sql.gz') or f.endswith('.dump')]
                if backup_files:
                    backup_files.sort(key=lambda x: os.path.getmtime(os.path.join(backup_dir, x)), reverse=True)
                    latest_backup = backup_files[0]
                    backup_path = os.path.join(backup_dir, latest_backup)
                    backup_time = datetime.fromtimestamp(os.path.getmtime(backup_path))
                    backup_size = os.path.getsize(backup_path)
                    
                    last_backup = {
                        "filename": latest_backup,
                        "time": backup_time.isoformat(),
                        "size_mb": round(backup_size / (1024 * 1024), 2),
                        "age_hours": round((datetime.now() - backup_time).total_seconds() / 3600, 1)
                    }
        except Exception as e:
            logger.error(f"获取备份信息失败: {e}")
            last_backup = {"error": str(e)}
        
        # 确定系统状态
        status = "healthy"
        if cpu_usage > 90 or memory.percent > 90 or disk.percent > 90:
            status = "warning"
        
        if "error" in database_status or "error" in redis_status:
            status = "critical"
        
        return {
            "status": status,
            "uptime": int(uptime),
            "cpu_usage": cpu_usage,
            "memory_usage": memory_usage,
            "disk_usage": disk_usage,
            "services": services,
            "database": database_status,
            "redis": redis_status,
            "last_backup": last_backup
        }
    except Exception as e:
        logger.error(f"获取系统状态失败: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


def restart_service_task(services: List[str], force: bool = False):
    """
    重启服务任务（后台执行）
    
    Args:
        services: 要重启的服务列表
        force: 是否强制重启
    """
    try:
        logger.info(f"开始重启服务: {services}, force={force}")
        
        # 检查是否在Docker环境中
        in_docker = os.path.exists("/.dockerenv")
        
        if in_docker:
            # 在Docker环境中，使用docker-compose重启服务
            for service in services:
                cmd = ["docker-compose", "restart"]
                if force:
                    cmd.append("--force")
                cmd.append(service)
                
                logger.info(f"执行命令: {' '.join(cmd)}")
                subprocess.run(cmd, check=True)
                logger.info(f"服务 {service} 重启成功")
        else:
            # 在非Docker环境中，使用systemctl重启服务
            for service in services:
                service_name = f"rsi-tracker-{service}.service"
                cmd = ["systemctl", "restart", service_name]
                
                logger.info(f"执行命令: {' '.join(cmd)}")
                subprocess.run(cmd, check=True)
                logger.info(f"服务 {service} 重启成功")
        
        logger.info("所有服务重启完成")
    except Exception as e:
        logger.error(f"重启服务失败: {e}")


# 端点实现
@router.get("/env", response_model=EnvConfig)
async def get_env_config_endpoint(
    current_user = Depends(get_current_active_superuser)
):
    """
    获取环境变量配置
    """
    try:
        config = get_env_config()
        return config
    except Exception as e:
        logger.error(f"获取环境变量配置失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取环境变量配置失败: {str(e)}"
        )


@router.put("/env", response_model=dict)
async def update_env_config_endpoint(
    config: EnvConfig,
    current_user = Depends(get_current_active_superuser)
):
    """
    更新环境变量配置
    """
    try:
        # 更新配置文件
        success = update_env_config_file(config.dict())
        
        if success:
            return {"status": "success", "message": "环境变量配置已更新"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="更新环境变量配置失败"
            )
    except Exception as e:
        logger.error(f"更新环境变量配置失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新环境变量配置失败: {str(e)}"
        )


@router.post("/test-connection", response_model=ConnectionTestResponse)
async def test_connection_endpoint(
    request: ConnectionTestRequest,
    current_user = Depends(get_current_active_superuser)
):
    """
    测试连接
    """
    try:
        if request.type == "database":
            result = await test_database_connection(request.config)
        elif request.type == "redis":
            result = await test_redis_connection(request.config)
        elif request.type == "exchange":
            result = await test_exchange_connection(request.config)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的连接类型: {request.type}"
            )
        
        return result
    except Exception as e:
        logger.error(f"测试连接失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"测试连接失败: {str(e)}"
        )


@router.get("/status", response_model=SystemStatusResponse)
async def get_system_status_endpoint(
    db: Session = Depends(get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    获取系统状态
    """
    try:
        status = await get_system_status(db)
        return status
    except Exception as e:
        logger.error(f"获取系统状态失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取系统状态失败: {str(e)}"
        )


@router.post("/restart", response_model=RestartResponse)
async def restart_services_endpoint(
    request: RestartRequest,
    background_tasks: BackgroundTasks,
    current_user = Depends(get_current_active_superuser)
):
    """
    重启服务
    """
    try:
        # 验证服务列表
        valid_services = ["api", "worker", "beat", "postgres", "redis", "nginx"]
        invalid_services = [s for s in request.services if s not in valid_services]
        
        if invalid_services:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的服务: {', '.join(invalid_services)}"
            )
        
        # 添加后台任务
        background_tasks.add_task(restart_service_task, request.services, request.force)
        
        return {
            "success": True,
            "message": f"服务重启指令已发送: {', '.join(request.services)}",
            "details": {
                "services": request.services,
                "force": request.force,
                "time": datetime.now().isoformat()
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重启服务失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"重启服务失败: {str(e)}"
        )
