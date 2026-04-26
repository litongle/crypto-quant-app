"""
RSI分层极值追踪自动量化交易系统 - 配置管理模块

使用Pydantic的BaseSettings进行配置管理，支持从环境变量和.env文件读取配置
"""

import os
from typing import List, Dict, Any, Optional, Union, Tuple
from pydantic import BaseSettings, Field, validator, PostgresDsn, RedisDsn, HttpUrl, SecretStr
from pathlib import Path
from functools import lru_cache


class Settings(BaseSettings):
    """系统配置类，从环境变量和.env文件读取配置"""
    
    # 基础配置
    APP_NAME: str = "RSI分层极值追踪量化交易系统"
    APP_VERSION: str = "0.1.0"
    DEBUG_MODE: bool = Field(False, description="调试模式开关")
    
    # 路径配置
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    LOG_DIR: Path = Field(Path("logs"), description="日志目录")
    DATA_DIR: Path = Field(Path("data"), description="数据目录")
    BACKUP_DIR: Path = Field(Path("backups"), description="备份目录")
    
    # ====================== 1. 数据库配置 ======================
    POSTGRES_USER: str = Field("postgres", description="PostgreSQL用户名")
    POSTGRES_PASSWORD: str = Field("postgres", description="PostgreSQL密码")
    POSTGRES_DB: str = Field("rsi_tracker", description="PostgreSQL数据库名")
    POSTGRES_HOST: str = Field("timescaledb", description="PostgreSQL主机名")
    POSTGRES_PORT: int = Field(5432, description="PostgreSQL端口")
    
    # 构建数据库URL
    DATABASE_URL: Optional[PostgresDsn] = None
    
    @validator("DATABASE_URL", pre=True)
    def assemble_db_connection(cls, v: Optional[str], values: Dict[str, Any]) -> Any:
        if isinstance(v, str):
            return v
        return PostgresDsn.build(
            scheme="postgresql",
            user=values.get("POSTGRES_USER"),
            password=values.get("POSTGRES_PASSWORD"),
            host=values.get("POSTGRES_HOST"),
            port=str(values.get("POSTGRES_PORT")),
            path=f"/{values.get('POSTGRES_DB') or ''}",
        )
    
    # 数据保留策略
    DATA_RETENTION_DAYS: int = Field(7, description="K线数据保留天数")
    TRADE_LOG_RETENTION_DAYS: int = Field(30, description="交易日志保留天数")
    
    # ====================== 2. Redis配置 ======================
    REDIS_HOST: str = Field("redis", description="Redis主机名")
    REDIS_PORT: int = Field(6379, description="Redis端口")
    REDIS_DB: int = Field(0, description="Redis数据库索引")
    REDIS_PASSWORD: Optional[str] = Field(None, description="Redis密码")
    
    # 构建Redis URL
    REDIS_URL: Optional[RedisDsn] = None
    
    @validator("REDIS_URL", pre=True)
    def assemble_redis_connection(cls, v: Optional[str], values: Dict[str, Any]) -> Any:
        if isinstance(v, str):
            return v
        
        # 构建Redis URL，根据是否有密码使用不同格式
        password = values.get("REDIS_PASSWORD")
        if password:
            return f"redis://:{password}@{values.get('REDIS_HOST')}:{values.get('REDIS_PORT')}/{values.get('REDIS_DB')}"
        return f"redis://{values.get('REDIS_HOST')}:{values.get('REDIS_PORT')}/{values.get('REDIS_DB')}"
    
    # ====================== 3. 交易所API配置 ======================
    # OKX API配置
    OKX_API_KEY: SecretStr = Field("", description="OKX API密钥")
    OKX_API_SECRET: SecretStr = Field("", description="OKX API密钥")
    OKX_API_PASSPHRASE: SecretStr = Field("", description="OKX API密码短语")
    OKX_API_URL: HttpUrl = Field("https://www.okx.com", description="OKX API地址")
    OKX_WS_PUBLIC_URL: str = Field("wss://ws.okx.com:8443/ws/v5/public", description="OKX公共WebSocket地址")
    OKX_WS_PRIVATE_URL: str = Field("wss://ws.okx.com:8443/ws/v5/private", description="OKX私有WebSocket地址")
    
    # 预留其他交易所API配置
    BINANCE_API_KEY: SecretStr = Field("", description="Binance API密钥")
    BINANCE_API_SECRET: SecretStr = Field("", description="Binance API密钥")
    
    HTX_API_KEY: SecretStr = Field("", description="HTX API密钥")
    HTX_API_SECRET: SecretStr = Field("", description="HTX API密钥")
    
    # ====================== 4. 交易策略参数 ======================
    # RSI参数
    RSI_PERIOD: int = Field(14, description="RSI计算周期")
    
    # 多头阈值
    RSI_LONG_LEVEL1: int = Field(35, description="多头第一层阈值")
    RSI_LONG_LEVEL2: int = Field(30, description="多头第二层阈值")
    RSI_LONG_LEVEL3: int = Field(20, description="多头第三层阈值")
    
    # 空头阈值
    RSI_SHORT_LEVEL1: int = Field(65, description="空头第一层阈值")
    RSI_SHORT_LEVEL2: int = Field(70, description="空头第二层阈值")
    RSI_SHORT_LEVEL3: int = Field(80, description="空头第三层阈值")
    
    # 极值回撤参数
    RSI_RETRACEMENT_POINTS: int = Field(2, description="极值回撤触发点数")
    
    # 加仓参数
    MAX_ADDITIONAL_POSITIONS: int = Field(4, description="最大加仓次数")
    
    # 止损参数
    FIXED_STOP_LOSS_POINTS: int = Field(6, description="固定止损点数")
    
    # 止盈参数（分层）
    PROFIT_TAKING_WINDOWS: str = Field("5,10,15,30,40", description="持仓K线数分层窗口")
    PROFIT_RETRACEMENT_POINTS: str = Field("2,3,5,8,13", description="对应窗口最大浮盈回撤阈值")
    MIN_PROFIT_POINTS: str = Field("3,4,7,11,18", description="达到回撤止盈时的最小盈利")
    
    @property
    def profit_taking_config(self) -> List[Tuple[int, int, int]]:
        """解析止盈配置为元组列表[(窗口,回撤点数,最小盈利),...]"""
        windows = [int(x) for x in self.PROFIT_TAKING_WINDOWS.split(",")]
        retracements = [int(x) for x in self.PROFIT_RETRACEMENT_POINTS.split(",")]
        min_profits = [int(x) for x in self.MIN_PROFIT_POINTS.split(",")]
        
        # 确保三个列表长度一致
        min_len = min(len(windows), len(retracements), len(min_profits))
        return [(windows[i], retracements[i], min_profits[i]) for i in range(min_len)]
    
    # 持仓管理
    MAX_HOLDING_CANDLES: int = Field(60, description="最大持仓K线数")
    COOLING_CANDLES: int = Field(3, description="平仓后冷却期K线数")
    
    # 杠杆和资金管理
    DEFAULT_LEVERAGE: int = Field(20, description="默认杠杆倍数")
    MAX_LEVERAGE: int = Field(125, description="最大杠杆倍数")
    ORDER_FUND_RATIO: float = Field(0.25, description="单次开仓占用账户USDT比例")
    MAX_POSITION_VALUE: float = Field(0.8, description="最大持仓价值占账户比例")
    
    # ====================== 5. 云备份配置 ======================
    # 备份目标
    BACKUP_PROVIDER: str = Field("oss", description="备份提供商：oss(阿里云)、cos(腾讯云)、s3(亚马逊)")
    BACKUP_BUCKET: str = Field("", description="存储桶名称")
    BACKUP_PREFIX: str = Field("rsi-tracker/", description="存储路径前缀")
    
    # 阿里云OSS配置
    OSS_ACCESS_KEY: SecretStr = Field("", description="阿里云OSS访问密钥")
    OSS_SECRET_KEY: SecretStr = Field("", description="阿里云OSS访问密钥")
    OSS_ENDPOINT: str = Field("oss-cn-hangzhou.aliyuncs.com", description="阿里云OSS终端节点")
    
    # 备份计划
    BACKUP_CRON: str = Field("0 3 * * *", description="备份计划(cron格式)")
    BACKUP_RETENTION: int = Field(30, description="云端备份保留天数")
    
    # ====================== 6. 系统运行参数 ======================
    # Web服务配置
    WEB_HOST: str = Field("0.0.0.0", description="Web服务监听地址")
    WEB_PORT: int = Field(8080, description="Web服务监听端口")
    API_PREFIX: str = Field("/api/v1", description="API路径前缀")
    
    # Celery任务队列配置
    CELERY_BROKER_URL: str = Field("", description="Celery消息代理URL")
    CELERY_RESULT_BACKEND: str = Field("", description="Celery结果后端URL")
    CELERY_TASK_ALWAYS_EAGER: bool = Field(False, description="是否立即执行任务(调试用)")
    
    @validator("CELERY_BROKER_URL", "CELERY_RESULT_BACKEND", pre=True)
    def set_celery_urls(cls, v: str, values: Dict[str, Any]) -> str:
        if v:
            return v
        return values.get("REDIS_URL", "")
    
    # 日志配置
    LOG_LEVEL: str = Field("INFO", description="日志级别(DEBUG, INFO, WARNING, ERROR)")
    LOG_FORMAT: str = Field("json", description="日志格式(json, text)")
    LOG_FILE: str = Field("/app/logs/app.log", description="日志文件路径")
    
    # 行情数据配置
    KLINE_INTERVAL: str = Field("1m", description="K线时间间隔(1m = 1分钟)")
    SYMBOL: str = Field("ETH-USDT-SWAP", description="交易对")
    
    # ====================== 7. 安全相关配置 ======================
    # JWT认证配置
    JWT_SECRET: str = Field("your_very_long_random_secret_key", description="JWT密钥")
    JWT_ALGORITHM: str = Field("HS256", description="JWT算法")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(1440, description="JWT访问令牌过期时间(分钟)")
    
    # Web安全配置
    CORS_ORIGINS: str = Field("http://localhost:3000,http://localhost:8080", description="CORS允许的源")
    ALLOWED_HOSTS: str = Field("localhost,127.0.0.1", description="允许的主机名")
    RATE_LIMIT: int = Field(100, description="API速率限制(每分钟请求数)")
    
    # 解析CORS源为列表
    @property
    def cors_origins_list(self) -> List[str]:
        return self.CORS_ORIGINS.split(",")
    
    # 解析允许的主机为列表
    @property
    def allowed_hosts_list(self) -> List[str]:
        return self.ALLOWED_HOSTS.split(",")
    
    # 加密配置
    ENCRYPTION_KEY: str = Field("your_32byte_encryption_key", description="用于加密敏感数据的密钥")
    
    # IP白名单
    IP_WHITELIST: str = Field("", description="允许访问的IP白名单(逗号分隔)")
    
    @property
    def ip_whitelist_list(self) -> List[str]:
        if not self.IP_WHITELIST:
            return []
        return self.IP_WHITELIST.split(",")
    
    # 告警通知
    ENABLE_NOTIFICATIONS: bool = Field(True, description="是否启用通知")
    NOTIFICATION_WEBHOOK: str = Field("", description="通知Webhook URL")
    NOTIFICATION_EMAIL: str = Field("", description="告警邮箱地址")
    
    class Config:
        """Pydantic配置类"""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """
    获取应用配置单例
    使用lru_cache装饰器确保只创建一个Settings实例
    """
    return Settings()


# 导出配置实例，方便其他模块导入
settings = get_settings()
