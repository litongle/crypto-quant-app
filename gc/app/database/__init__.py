"""
RSI分层极值追踪自动量化交易系统 - 数据库模块

提供数据库连接、会话管理和ORM基类
使用SQLAlchemy作为ORM框架，TimescaleDB(PostgreSQL)作为后端数据库
"""

from typing import Generator, Any, Dict
import logging
from sqlalchemy import create_engine, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

from app.core.config import settings

# 配置日志
logger = logging.getLogger(__name__)

# 创建SQLAlchemy引擎
# 使用连接池配置，适合高频交易场景
engine = create_engine(
    str(settings.DATABASE_URL),
    pool_size=10,  # 连接池大小
    max_overflow=20,  # 最大溢出连接数
    pool_timeout=30,  # 连接超时时间(秒)
    pool_recycle=1800,  # 连接回收时间(秒)
    pool_pre_ping=True,  # 使用前ping一下确保连接有效
    poolclass=QueuePool,  # 使用队列连接池
    echo=settings.DEBUG_MODE,  # 调试模式下打印SQL语句
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建Base类，所有ORM模型都将继承此类
Base = declarative_base()

# 定义命名约定的元数据
metadata = MetaData(naming_convention={
    "ix": "ix_%(column_0_label)s",  # 索引命名约定
    "uq": "uq_%(table_name)s_%(column_0_name)s",  # 唯一约束命名约定
    "ck": "ck_%(table_name)s_%(constraint_name)s",  # 检查约束命名约定
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",  # 外键命名约定
    "pk": "pk_%(table_name)s"  # 主键命名约定
})


def get_db() -> Generator[Session, None, None]:
    """
    获取数据库会话的依赖函数
    用于FastAPI的Depends注入
    
    Yields:
        Session: 数据库会话对象
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """
    初始化数据库
    创建所有表并执行必要的初始化操作
    """
    try:
        # 创建TimescaleDB扩展(如果不存在)
        with engine.connect() as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")
            logger.info("TimescaleDB extension created or already exists")
        
        # 创建所有表
        Base.metadata.create_all(bind=engine)
        logger.info("All database tables created successfully")
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise


def setup_timescale_hypertables() -> None:
    """
    设置TimescaleDB超表
    将时间序列表转换为TimescaleDB超表，提高查询性能
    在所有表创建完成后调用
    """
    # 这个函数将在models导入后由应用程序启动脚本调用
    # 具体的超表创建代码将在各个模型文件中实现
    pass


# 导出所有需要的组件
__all__ = ["Base", "engine", "get_db", "init_db", "setup_timescale_hypertables"]
