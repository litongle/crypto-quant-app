"""
环境变量管理工具

该模块提供环境变量配置文件(.env)的读取、写入、加密、解密和验证功能。
主要功能包括：
1. 环境变量文件读取和写入
2. 敏感信息加密和解密
3. 配置验证
4. 备份功能

使用示例:
    # 读取环境变量文件
    env_data = load_env_file(".env")
    
    # 更新环境变量文件
    update_env_file(".env", {"API_KEY": "new_value"})
    
    # 加密敏感信息
    encrypted = encrypt_value("sensitive_data")
    
    # 解密敏感信息
    decrypted = decrypt_value(encrypted)
    
    # 创建环境变量文件备份
    backup_file = backup_env_file(".env")
    
    # 恢复环境变量文件
    restore_env_file(backup_file, ".env")
"""

import os
import re
import time
import json
import base64
import shutil
import logging
import secrets
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Union, Tuple

# 尝试导入加密库，如果不可用则使用简单的替代方案
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False

# 设置日志
logger = logging.getLogger(__name__)

# 默认加密盐值（仅在没有提供密钥的情况下使用）
DEFAULT_SALT = b"RSI_LAYERED_STRATEGY_SALT"

# 默认备份目录
DEFAULT_BACKUP_DIR = "backups/env"


def load_env_file(file_path: str) -> Dict[str, str]:
    """
    读取环境变量文件(.env)
    
    Args:
        file_path: 环境变量文件路径
        
    Returns:
        Dict[str, str]: 环境变量字典
    """
    env_data = {}
    
    # 检查文件是否存在
    if not os.path.exists(file_path):
        logger.warning(f"环境变量文件不存在: {file_path}")
        return env_data
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                
                # 跳过空行和注释
                if not line or line.startswith("#"):
                    continue
                
                # 解析键值对
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # 移除引号
                    if (value.startswith('"') and value.endswith('"')) or \
                       (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    
                    env_data[key] = value
        
        logger.debug(f"成功读取环境变量文件: {file_path}, 共{len(env_data)}项")
        return env_data
    except Exception as e:
        logger.error(f"读取环境变量文件失败: {file_path}, 错误: {e}")
        return env_data


def update_env_file(file_path: str, updates: Dict[str, str]) -> bool:
    """
    更新环境变量文件(.env)，保留注释和格式
    
    Args:
        file_path: 环境变量文件路径
        updates: 要更新的环境变量字典
        
    Returns:
        bool: 是否成功
    """
    # 检查文件是否存在
    if not os.path.exists(file_path):
        logger.warning(f"环境变量文件不存在: {file_path}，将创建新文件")
        try:
            # 创建目录
            os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
            
            # 创建新文件
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("# 环境变量配置文件\n")
                f.write("# 由系统自动生成于 " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n\n")
                
                # 写入更新的环境变量
                for key, value in updates.items():
                    # 如果值包含空格或特殊字符，添加引号
                    if re.search(r'[\s"\'\\]', value):
                        value = f'"{value}"'
                    f.write(f"{key}={value}\n")
            
            logger.info(f"成功创建环境变量文件: {file_path}")
            return True
        except Exception as e:
            logger.error(f"创建环境变量文件失败: {file_path}, 错误: {e}")
            return False
    
    try:
        # 备份原文件
        backup_file = backup_env_file(file_path)
        
        # 读取原文件内容
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        # 更新环境变量
        updated_lines = []
        updated_keys = set()
        
        for line in lines:
            original_line = line
            line = line.strip()
            
            # 保留空行和注释
            if not line or line.startswith("#"):
                updated_lines.append(original_line)
                continue
            
            # 更新键值对
            if "=" in line:
                key, _ = line.split("=", 1)
                key = key.strip()
                
                if key in updates:
                    value = updates[key]
                    # 如果值包含空格或特殊字符，添加引号
                    if re.search(r'[\s"\'\\]', value):
                        value = f'"{value}"'
                    updated_lines.append(f"{key}={value}\n")
                    updated_keys.add(key)
                else:
                    updated_lines.append(original_line)
            else:
                updated_lines.append(original_line)
        
        # 添加未更新的键
        if updated_lines and not updated_lines[-1].endswith("\n"):
            updated_lines.append("\n")
        
        for key, value in updates.items():
            if key not in updated_keys:
                # 如果值包含空格或特殊字符，添加引号
                if re.search(r'[\s"\'\\]', value):
                    value = f'"{value}"'
                updated_lines.append(f"{key}={value}\n")
        
        # 写入更新后的内容
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(updated_lines)
        
        logger.info(f"成功更新环境变量文件: {file_path}, 更新{len(updates)}项")
        return True
    except Exception as e:
        logger.error(f"更新环境变量文件失败: {file_path}, 错误: {e}")
        
        # 恢复备份
        if backup_file and os.path.exists(backup_file):
            try:
                shutil.copy2(backup_file, file_path)
                logger.info(f"已恢复环境变量文件备份: {backup_file} -> {file_path}")
            except Exception as restore_error:
                logger.error(f"恢复环境变量文件备份失败: {restore_error}")
        
        return False


def get_encryption_key(key: Optional[str] = None) -> bytes:
    """
    获取加密密钥
    
    Args:
        key: 可选的密钥字符串，如果未提供则尝试从环境变量获取
        
    Returns:
        bytes: 加密密钥
    """
    if not key:
        # 尝试从环境变量获取密钥
        key = os.environ.get("API_SECRET_KEY")
    
    if not key:
        # 使用默认密钥（警告：这不安全，仅用于开发）
        logger.warning("未提供加密密钥，使用默认密钥")
        key = "default_insecure_key_please_change_in_production"
    
    if CRYPTOGRAPHY_AVAILABLE:
        # 使用PBKDF2生成密钥
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=DEFAULT_SALT,
            iterations=100000,
        )
        return base64.urlsafe_b64encode(kdf.derive(key.encode()))
    else:
        # 简单的密钥生成（不安全，仅作为备用）
        import hashlib
        key_hash = hashlib.sha256(key.encode() + DEFAULT_SALT).digest()
        return base64.urlsafe_b64encode(key_hash)


def encrypt_value(value: str, key: Optional[str] = None) -> str:
    """
    加密字符串值
    
    Args:
        value: 要加密的字符串
        key: 可选的加密密钥
        
    Returns:
        str: 加密后的字符串
    """
    if not value:
        return value
    
    try:
        if CRYPTOGRAPHY_AVAILABLE:
            # 使用Fernet加密
            encryption_key = get_encryption_key(key)
            f = Fernet(encryption_key)
            encrypted = f.encrypt(value.encode())
            return base64.urlsafe_b64encode(encrypted).decode()
        else:
            # 简单的XOR加密（不安全，仅作为备用）
            encryption_key = get_encryption_key(key)
            key_bytes = base64.urlsafe_b64decode(encryption_key)
            value_bytes = value.encode()
            encrypted = bytearray()
            
            for i, b in enumerate(value_bytes):
                key_byte = key_bytes[i % len(key_bytes)]
                encrypted.append(b ^ key_byte)
            
            return base64.urlsafe_b64encode(encrypted).decode()
    except Exception as e:
        logger.error(f"加密失败: {e}")
        # 返回原始值，但添加标记表示加密失败
        return f"failed_to_encrypt:{value}"


def decrypt_value(encrypted_value: str, key: Optional[str] = None) -> str:
    """
    解密字符串值
    
    Args:
        encrypted_value: 加密的字符串
        key: 可选的加密密钥
        
    Returns:
        str: 解密后的字符串
    """
    if not encrypted_value:
        return encrypted_value
    
    # 检查是否是加密失败的值
    if encrypted_value.startswith("failed_to_encrypt:"):
        return encrypted_value[18:]
    
    try:
        if CRYPTOGRAPHY_AVAILABLE:
            # 使用Fernet解密
            encryption_key = get_encryption_key(key)
            f = Fernet(encryption_key)
            encrypted = base64.urlsafe_b64decode(encrypted_value.encode())
            decrypted = f.decrypt(encrypted)
            return decrypted.decode()
        else:
            # 简单的XOR解密
            encryption_key = get_encryption_key(key)
            key_bytes = base64.urlsafe_b64decode(encryption_key)
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_value.encode())
            decrypted = bytearray()
            
            for i, b in enumerate(encrypted_bytes):
                key_byte = key_bytes[i % len(key_bytes)]
                decrypted.append(b ^ key_byte)
            
            return decrypted.decode()
    except Exception as e:
        logger.error(f"解密失败: {e}")
        return f"failed_to_decrypt:{encrypted_value}"


def backup_env_file(file_path: str, backup_dir: Optional[str] = None) -> str:
    """
    创建环境变量文件备份
    
    Args:
        file_path: 环境变量文件路径
        backup_dir: 可选的备份目录
        
    Returns:
        str: 备份文件路径
    """
    if not os.path.exists(file_path):
        logger.warning(f"环境变量文件不存在，无法创建备份: {file_path}")
        return ""
    
    try:
        # 确定备份目录
        if not backup_dir:
            backup_dir = os.environ.get("BACKUP_DIR", DEFAULT_BACKUP_DIR)
        
        # 创建备份目录
        os.makedirs(backup_dir, exist_ok=True)
        
        # 生成备份文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = os.path.basename(file_path)
        backup_file = os.path.join(backup_dir, f"{file_name}.{timestamp}.bak")
        
        # 复制文件
        shutil.copy2(file_path, backup_file)
        
        logger.info(f"成功创建环境变量文件备份: {file_path} -> {backup_file}")
        return backup_file
    except Exception as e:
        logger.error(f"创建环境变量文件备份失败: {e}")
        return ""


def restore_env_file(backup_file: str, target_file: str) -> bool:
    """
    恢复环境变量文件备份
    
    Args:
        backup_file: 备份文件路径
        target_file: 目标文件路径
        
    Returns:
        bool: 是否成功
    """
    if not os.path.exists(backup_file):
        logger.error(f"备份文件不存在: {backup_file}")
        return False
    
    try:
        # 创建目标文件目录
        os.makedirs(os.path.dirname(os.path.abspath(target_file)), exist_ok=True)
        
        # 复制文件
        shutil.copy2(backup_file, target_file)
        
        logger.info(f"成功恢复环境变量文件: {backup_file} -> {target_file}")
        return True
    except Exception as e:
        logger.error(f"恢复环境变量文件失败: {e}")
        return False


def list_env_backups(backup_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    列出环境变量文件备份
    
    Args:
        backup_dir: 可选的备份目录
        
    Returns:
        List[Dict[str, Any]]: 备份文件列表
    """
    backups = []
    
    try:
        # 确定备份目录
        if not backup_dir:
            backup_dir = os.environ.get("BACKUP_DIR", DEFAULT_BACKUP_DIR)
        
        if not os.path.exists(backup_dir):
            logger.warning(f"备份目录不存在: {backup_dir}")
            return backups
        
        # 遍历备份文件
        for file in os.listdir(backup_dir):
            if file.endswith(".bak"):
                file_path = os.path.join(backup_dir, file)
                
                # 解析时间戳
                match = re.search(r"\.(\d{8}_\d{6})\.bak$", file)
                timestamp = None
                if match:
                    try:
                        timestamp = datetime.strptime(match.group(1), "%Y%m%d_%H%M%S")
                    except ValueError:
                        pass
                
                backups.append({
                    "file": file,
                    "path": file_path,
                    "size": os.path.getsize(file_path),
                    "timestamp": timestamp.isoformat() if timestamp else None,
                    "age_seconds": (datetime.now() - timestamp).total_seconds() if timestamp else None
                })
        
        # 按时间戳排序
        backups.sort(key=lambda x: x["timestamp"] if x["timestamp"] else "", reverse=True)
        
        return backups
    except Exception as e:
        logger.error(f"列出环境变量文件备份失败: {e}")
        return backups


def clean_old_backups(backup_dir: Optional[str] = None, keep_count: int = 10) -> int:
    """
    清理旧的环境变量文件备份
    
    Args:
        backup_dir: 可选的备份目录
        keep_count: 保留的备份数量
        
    Returns:
        int: 删除的备份数量
    """
    try:
        # 获取备份列表
        backups = list_env_backups(backup_dir)
        
        # 如果备份数量小于等于保留数量，不需要清理
        if len(backups) <= keep_count:
            return 0
        
        # 删除多余的备份
        deleted_count = 0
        for backup in backups[keep_count:]:
            try:
                os.remove(backup["path"])
                deleted_count += 1
                logger.debug(f"删除旧备份: {backup['path']}")
            except Exception as e:
                logger.error(f"删除旧备份失败: {backup['path']}, 错误: {e}")
        
        logger.info(f"清理旧备份完成，共删除{deleted_count}个备份")
        return deleted_count
    except Exception as e:
        logger.error(f"清理旧备份失败: {e}")
        return 0


def validate_config(config: Dict[str, Any], schema: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    验证配置是否符合模式定义
    
    Args:
        config: 配置字典
        schema: 模式定义字典
        
    Returns:
        Tuple[bool, List[str]]: (是否有效, 错误消息列表)
    """
    errors = []
    
    try:
        for key, schema_def in schema.items():
            # 检查必填项
            if schema_def.get("required", False) and (key not in config or not config[key]):
                errors.append(f"缺少必填项: {key}")
                continue
            
            # 如果配置中没有该项，跳过后续验证
            if key not in config:
                continue
            
            value = config[key]
            
            # 类型检查
            expected_type = schema_def.get("type")
            if expected_type:
                if expected_type == "string" and not isinstance(value, str):
                    errors.append(f"{key} 应为字符串类型")
                elif expected_type == "integer" and not isinstance(value, int):
                    try:
                        # 尝试转换为整数
                        config[key] = int(value)
                    except (ValueError, TypeError):
                        errors.append(f"{key} 应为整数类型")
                elif expected_type == "number" and not isinstance(value, (int, float)):
                    try:
                        # 尝试转换为浮点数
                        config[key] = float(value)
                    except (ValueError, TypeError):
                        errors.append(f"{key} 应为数字类型")
                elif expected_type == "boolean" and not isinstance(value, bool):
                    # 尝试转换为布尔值
                    if isinstance(value, str):
                        if value.lower() in ("true", "yes", "1"):
                            config[key] = True
                        elif value.lower() in ("false", "no", "0"):
                            config[key] = False
                        else:
                            errors.append(f"{key} 应为布尔类型")
                    else:
                        errors.append(f"{key} 应为布尔类型")
                elif expected_type == "array" and not isinstance(value, list):
                    try:
                        # 尝试解析JSON数组
                        if isinstance(value, str):
                            config[key] = json.loads(value)
                            if not isinstance(config[key], list):
                                errors.append(f"{key} 应为数组类型")
                        else:
                            errors.append(f"{key} 应为数组类型")
                    except json.JSONDecodeError:
                        errors.append(f"{key} 应为有效的JSON数组")
                elif expected_type == "object" and not isinstance(value, dict):
                    try:
                        # 尝试解析JSON对象
                        if isinstance(value, str):
                            config[key] = json.loads(value)
                            if not isinstance(config[key], dict):
                                errors.append(f"{key} 应为对象类型")
                        else:
                            errors.append(f"{key} 应为对象类型")
                    except json.JSONDecodeError:
                        errors.append(f"{key} 应为有效的JSON对象")
            
            # 范围检查
            if "minimum" in schema_def and value < schema_def["minimum"]:
                errors.append(f"{key} 应大于等于 {schema_def['minimum']}")
            
            if "maximum" in schema_def and value > schema_def["maximum"]:
                errors.append(f"{key} 应小于等于 {schema_def['maximum']}")
            
            # 枚举检查
            if "enum" in schema_def and value not in schema_def["enum"]:
                errors.append(f"{key} 应为以下值之一: {', '.join(map(str, schema_def['enum']))}")
            
            # 模式检查
            if "pattern" in schema_def and isinstance(value, str):
                pattern = re.compile(schema_def["pattern"])
                if not pattern.match(value):
                    errors.append(f"{key} 不符合指定的格式")
            
            # 自定义验证函数
            if "validator" in schema_def and callable(schema_def["validator"]):
                try:
                    result = schema_def["validator"](value)
                    if result is not True:
                        errors.append(f"{key}: {result}")
                except Exception as e:
                    errors.append(f"{key} 验证失败: {str(e)}")
        
        return len(errors) == 0, errors
    except Exception as e:
        logger.error(f"配置验证失败: {e}")
        errors.append(f"配置验证过程中发生错误: {str(e)}")
        return False, errors


def generate_api_key(length: int = 32) -> str:
    """
    生成安全的API密钥
    
    Args:
        length: 密钥长度
        
    Returns:
        str: 生成的API密钥
    """
    return secrets.token_urlsafe(length)


def get_env_var(key: str, default: Any = None, as_type: Optional[type] = None) -> Any:
    """
    获取环境变量，支持类型转换
    
    Args:
        key: 环境变量名
        default: 默认值
        as_type: 目标类型
        
    Returns:
        Any: 环境变量值
    """
    value = os.environ.get(key, default)
    
    if value is None:
        return default
    
    if as_type is not None:
        try:
            if as_type is bool:
                return value.lower() in ("true", "yes", "1", "y", "t")
            elif as_type is int:
                return int(value)
            elif as_type is float:
                return float(value)
            elif as_type is list:
                return value.split(",") if value else []
            else:
                return as_type(value)
        except (ValueError, TypeError):
            logger.warning(f"环境变量 {key} 转换为 {as_type.__name__} 类型失败，使用默认值")
            return default
    
    return value


def create_default_env_file(file_path: str) -> bool:
    """
    创建默认的环境变量文件
    
    Args:
        file_path: 环境变量文件路径
        
    Returns:
        bool: 是否成功
    """
    if os.path.exists(file_path):
        logger.warning(f"环境变量文件已存在: {file_path}")
        return False
    
    try:
        # 创建目录
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        
        # 生成API密钥
        api_key = generate_api_key()
        
        # 创建默认环境变量
        default_env = {
            "# 基本设置": "",
            "APP_NAME": "RSI分层极值追踪量化系统",
            "DEBUG_MODE": "true",
            "LOG_LEVEL": "INFO",
            "API_SECRET_KEY": api_key,
            "ALLOW_REGISTRATION": "false",
            
            "# 数据库设置": "",
            "POSTGRES_HOST": "postgres",
            "POSTGRES_PORT": "5432",
            "POSTGRES_DB": "rsi_tracker",
            "POSTGRES_USER": "postgres",
            "POSTGRES_PASSWORD": "changeme",
            "DATA_RETENTION_DAYS": "7",
            
            "# Redis设置": "",
            "REDIS_HOST": "redis",
            "REDIS_PORT": "6379",
            "REDIS_PASSWORD": "",
            "REDIS_DB": "0",
            "REDIS_URL": "redis://redis:6379/0",
            
            "# 交易所API设置": "",
            "OKX_API_KEY": "",
            "OKX_API_SECRET": "",
            "OKX_PASSPHRASE": "",
            "OKX_MAX_LEVERAGE": "50",
            
            "# 策略设置": "",
            "RSI_PERIOD": "14",
            "LONG_LEVELS": "30,25,20",
            "SHORT_LEVELS": "70,75,80",
            "RETRACEMENT_POINTS": "10",
            "MAX_ADDITIONAL_POSITIONS": "3",
            "FIXED_STOP_LOSS_POINTS": "50",
            "PROFIT_TAKING_CONFIG": '[{"profit_rate": 0.03, "position_rate": 0.5}, {"profit_rate": 0.05, "position_rate": 1.0}]',
            "MAX_HOLDING_CANDLES": "1440",
            "COOLING_CANDLES": "10",
            
            "# 备份设置": "",
            "ENABLE_AUTO_BACKUP": "true",
            "BACKUP_INTERVAL_HOURS": "24",
            "BACKUP_KEEP_COUNT": "7",
            "BACKUP_DIR": "/app/backup"
        }
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("# 环境变量配置文件\n")
            f.write("# 由系统自动生成于 " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n\n")
            
            for key, value in default_env.items():
                if key.startswith("#"):
                    f.write("\n" + key + "\n")
                else:
                    # 如果值包含空格或特殊字符，添加引号
                    if value and re.search(r'[\s"\'\\]', value):
                        value = f'"{value}"'
                    f.write(f"{key}={value}\n")
        
        logger.info(f"成功创建默认环境变量文件: {file_path}")
        return True
    except Exception as e:
        logger.error(f"创建默认环境变量文件失败: {file_path}, 错误: {e}")
        return False
