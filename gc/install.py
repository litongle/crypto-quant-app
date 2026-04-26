#!/usr/bin/env python3
"""
RSI分层极值追踪自动量化交易系统 - 一键安装脚本

该脚本提供一键安装功能，包括：
1. 系统环境检查
2. 依赖安装
3. 项目文件创建
4. 环境变量配置
5. 数据库初始化
6. Docker环境配置
7. 启动服务

使用方法:
    python install.py [选项]

选项:
    --no-docker       不使用Docker安装
    --no-deps         不安装依赖
    --config-only     仅配置环境变量
    --help            显示帮助信息
"""

import os
import sys
import re
import json
import time
import shutil
import platform
import subprocess
import argparse
import getpass
import urllib.request
import zipfile
import tarfile
import tempfile
import logging
import socket
import secrets
import webbrowser
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Union, Callable

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('install.log', encoding='utf-8')
    ]
)
logger = logging.getLogger("installer")

# 全局变量
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR))
DEFAULT_DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DEFAULT_CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")
DEFAULT_LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
DEFAULT_BACKUP_DIR = os.path.join(PROJECT_ROOT, "backup")
TEMP_DIR = tempfile.mkdtemp(prefix="rsi_installer_")

# 颜色代码
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


# 命令行参数解析
def parse_args():
    parser = argparse.ArgumentParser(description="RSI分层极值追踪自动量化交易系统安装脚本")
    parser.add_argument("--no-docker", action="store_true", help="不使用Docker安装")
    parser.add_argument("--no-deps", action="store_true", help="不安装依赖")
    parser.add_argument("--config-only", action="store_true", help="仅配置环境变量")
    parser.add_argument("--debug", action="store_true", help="启用调试模式")
    return parser.parse_args()


# 打印带颜色的消息
def print_color(message, color=Colors.BLUE, bold=False):
    if bold:
        print(f"{color}{Colors.BOLD}{message}{Colors.ENDC}")
    else:
        print(f"{color}{message}{Colors.ENDC}")


# 打印标题
def print_title(title):
    print("\n" + "=" * 80)
    print_color(f" {title} ", Colors.HEADER, bold=True)
    print("=" * 80)


# 打印步骤
def print_step(step):
    print_color(f"\n>> {step}", Colors.CYAN)


# 打印成功消息
def print_success(message):
    print_color(f"✓ {message}", Colors.GREEN)


# 打印警告消息
def print_warning(message):
    print_color(f"! {message}", Colors.YELLOW)


# 打印错误消息
def print_error(message):
    print_color(f"✗ {message}", Colors.RED)


# 打印信息消息
def print_info(message):
    print_color(f"ℹ {message}", Colors.BLUE)


# 执行命令
def run_command(command, shell=False, cwd=None, env=None, capture_output=False):
    try:
        if isinstance(command, str) and not shell:
            command = command.split()
        
        logger.debug(f"执行命令: {command}")
        
        if capture_output:
            result = subprocess.run(
                command,
                shell=shell,
                cwd=cwd,
                env=env,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            return result.stdout.strip()
        else:
            subprocess.run(
                command,
                shell=shell,
                cwd=cwd,
                env=env,
                check=True
            )
            return True
    except subprocess.CalledProcessError as e:
        logger.error(f"命令执行失败: {e}")
        if capture_output:
            logger.error(f"错误输出: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"命令执行异常: {e}")
        return False


# 检查命令是否存在
def command_exists(command):
    try:
        subprocess.run(
            ["which" if platform.system() != "Windows" else "where", command],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        return True
    except:
        return False


# 检查端口是否被占用
def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


# 检查Python版本
def check_python_version():
    print_step("检查Python版本")
    
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print_error(f"Python版本过低: {version.major}.{version.minor}.{version.micro}")
        print_info("需要Python 3.8或更高版本")
        return False
    
    print_success(f"Python版本: {version.major}.{version.minor}.{version.micro}")
    return True


# 检查操作系统
def check_os():
    print_step("检查操作系统")
    
    system = platform.system()
    release = platform.release()
    
    if system == "Linux":
        print_success(f"操作系统: Linux {release}")
        return True
    elif system == "Darwin":
        print_success(f"操作系统: macOS {release}")
        return True
    elif system == "Windows":
        print_success(f"操作系统: Windows {release}")
        return True
    else:
        print_warning(f"未知操作系统: {system} {release}")
        return True


# 检查Docker
def check_docker():
    print_step("检查Docker")
    
    if not command_exists("docker"):
        print_error("Docker未安装")
        print_info("请先安装Docker: https://docs.docker.com/get-docker/")
        return False
    
    # 检查Docker版本
    docker_version = run_command("docker --version", capture_output=True)
    if not docker_version:
        print_error("无法获取Docker版本")
        return False
    
    print_success(f"Docker版本: {docker_version}")
    
    # 检查Docker Compose
    if command_exists("docker-compose"):
        compose_version = run_command("docker-compose --version", capture_output=True)
        print_success(f"Docker Compose版本: {compose_version}")
    elif command_exists("docker") and "compose" in run_command("docker help", capture_output=True):
        compose_version = run_command("docker compose version", capture_output=True)
        print_success(f"Docker Compose插件版本: {compose_version}")
    else:
        print_error("Docker Compose未安装")
        print_info("请安装Docker Compose: https://docs.docker.com/compose/install/")
        return False
    
    # 检查Docker服务是否运行
    if platform.system() == "Linux":
        docker_running = run_command("systemctl is-active docker", capture_output=True)
        if docker_running != "active":
            print_error("Docker服务未运行")
            print_info("请启动Docker服务: sudo systemctl start docker")
            return False
    
    print_success("Docker服务正在运行")
    return True


# 检查依赖
def check_dependencies(args):
    print_step("检查依赖")
    
    # 基本依赖
    required_modules = [
        "fastapi", "uvicorn", "sqlalchemy", "pydantic", "python-dotenv",
        "psycopg2-binary", "redis", "celery", "httpx", "pandas", "numpy"
    ]
    
    missing_modules = []
    for module in required_modules:
        try:
            __import__(module)
        except ImportError:
            missing_modules.append(module)
    
    if missing_modules:
        print_warning(f"缺少以下Python模块: {', '.join(missing_modules)}")
        
        if not args.no_deps:
            print_info("正在安装缺少的依赖...")
            
            # 创建requirements.txt
            with open("requirements.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(missing_modules))
            
            # 安装依赖
            if run_command(f"{sys.executable} -m pip install -r requirements.txt"):
                print_success("依赖安装成功")
            else:
                print_error("依赖安装失败")
                return False
        else:
            print_info("已跳过依赖安装，请手动安装缺少的模块")
    else:
        print_success("所有依赖已安装")
    
    return True


# 创建目录结构
def create_directory_structure():
    print_step("创建目录结构")
    
    directories = [
        "app",
        "app/api",
        "app/api/api_v1",
        "app/api/api_v1/endpoints",
        "app/core",
        "app/database",
        "app/exchange",
        "app/strategy",
        "app/tasks",
        "app/utils",
        "app/static",
        "docker",
        "docker/api",
        "docker/celery",
        "docker/nginx",
        "docker/timescaledb",
        "frontend",
        "scripts",
        "logs",
        "backup",
        "data"
    ]
    
    for directory in directories:
        os.makedirs(os.path.join(PROJECT_ROOT, directory), exist_ok=True)
        print_info(f"创建目录: {directory}")
    
    print_success("目录结构创建完成")
    return True


# 生成随机密钥
def generate_secret_key(length=32):
    return secrets.token_urlsafe(length)


# 创建环境变量文件
def create_env_file():
    print_step("创建环境变量文件")
    
    env_file = os.path.join(PROJECT_ROOT, ".env")
    env_example_file = os.path.join(PROJECT_ROOT, ".env.example")
    
    # 如果.env文件已存在，询问是否覆盖
    if os.path.exists(env_file):
        print_warning(".env文件已存在")
        overwrite = input("是否覆盖? (y/N): ").lower() == "y"
        if not overwrite:
            print_info("保留现有.env文件")
            return True
    
    # 生成API密钥
    api_key = generate_secret_key()
    
    # 创建默认环境变量
    env_content = f"""# 环境变量配置文件
# 由安装脚本自动生成于 {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

# 基本设置
APP_NAME=RSI分层极值追踪量化系统
DEBUG_MODE=true
LOG_LEVEL=INFO
API_SECRET_KEY={api_key}
ALLOW_REGISTRATION=false

# 数据库设置
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=rsi_tracker
POSTGRES_USER=postgres
POSTGRES_PASSWORD=changeme
DATA_RETENTION_DAYS=7

# Redis设置
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0
REDIS_URL=redis://redis:6379/0

# 交易所API设置
OKX_API_KEY=
OKX_API_SECRET=
OKX_PASSPHRASE=
OKX_MAX_LEVERAGE=50

# 策略设置
RSI_PERIOD=14
LONG_LEVELS=30,25,20
SHORT_LEVELS=70,75,80
RETRACEMENT_POINTS=10
MAX_ADDITIONAL_POSITIONS=3
FIXED_STOP_LOSS_POINTS=50
PROFIT_TAKING_CONFIG=[{"profit_rate": 0.03, "position_rate": 0.5}, {"profit_rate": 0.05, "position_rate": 1.0}]
MAX_HOLDING_CANDLES=1440
COOLING_CANDLES=10

# 备份设置
ENABLE_AUTO_BACKUP=true
BACKUP_INTERVAL_HOURS=24
BACKUP_KEEP_COUNT=7
BACKUP_DIR=/app/backup
"""
    
    # 写入.env文件
    with open(env_file, "w", encoding="utf-8") as f:
        f.write(env_content)
    
    # 创建.env.example文件
    with open(env_example_file, "w", encoding="utf-8") as f:
        f.write(env_content)
    
    print_success(".env文件创建成功")
    return True


# 创建简易配置Web服务器
def create_config_server():
    print_step("创建配置Web服务器")
    
    server_file = os.path.join(PROJECT_ROOT, "config_server.py")
    
    server_content = """#!/usr/bin/env python3
import os
import json
import secrets
import logging
import uvicorn
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Depends, status, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("config-server")

# 创建FastAPI应用
app = FastAPI(title="RSI量化系统配置服务器", description="用于配置RSI分层极值追踪自动量化交易系统")

# 安全认证
security = HTTPBasic()

# 模板目录
templates = Jinja2Templates(directory="templates")

# 生成管理员密码
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = secrets.token_urlsafe(8)

# 打印管理员凭据
print("=" * 50)
print(f"配置服务器已启动")
print(f"访问地址: http://localhost:8000")
print(f"用户名: {ADMIN_USERNAME}")
print(f"密码: {ADMIN_PASSWORD}")
print("=" * 50)


# 认证依赖
def get_current_user(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username != ADMIN_USERNAME or credentials.password != ADMIN_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证失败",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# 环境变量模型
class EnvConfig(BaseModel):
    key: str
    value: str
    description: Optional[str] = None


# 读取环境变量
def read_env_file(file_path: str = ".env") -> Dict[str, str]:
    env_data = {}
    
    if not os.path.exists(file_path):
        return env_data
    
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
    
    return env_data


# 更新环境变量
def update_env_file(file_path: str, updates: Dict[str, str]) -> bool:
    # 备份原文件
    if os.path.exists(file_path):
        backup_path = f"{file_path}.bak"
        try:
            with open(file_path, "r", encoding="utf-8") as src, \
                 open(backup_path, "w", encoding="utf-8") as dst:
                dst.write(src.read())
        except Exception as e:
            logger.error(f"备份环境变量文件失败: {e}")
            return False
    
    try:
        # 读取原文件内容
        lines = []
        if os.path.exists(file_path):
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
                    if any(c in value for c in " \t\"'"):
                        value = f'"{value}"'
                    updated_lines.append(f"{key}={value}\\n")
                    updated_keys.add(key)
                else:
                    updated_lines.append(original_line)
            else:
                updated_lines.append(original_line)
        
        # 添加未更新的键
        for key, value in updates.items():
            if key not in updated_keys:
                # 如果值包含空格或特殊字符，添加引号
                if any(c in value for c in " \t\"'"):
                    value = f'"{value}"'
                updated_lines.append(f"{key}={value}\\n")
        
        # 写入更新后的内容
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(updated_lines)
        
        return True
    except Exception as e:
        logger.error(f"更新环境变量文件失败: {e}")
        
        # 恢复备份
        backup_path = f"{file_path}.bak"
        if os.path.exists(backup_path):
            try:
                os.replace(backup_path, file_path)
            except Exception as restore_error:
                logger.error(f"恢复环境变量文件备份失败: {restore_error}")
        
        return False


# 创建模板目录
os.makedirs("templates", exist_ok=True)

# 创建HTML模板
with open("templates/config.html", "w", encoding="utf-8") as f:
    f.write('''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RSI量化系统配置</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f7fa;
        }
        h1 {
            color: #2c3e50;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
        }
        .card {
            background-color: white;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
            padding: 20px;
            margin-bottom: 20px;
        }
        .form-group {
            margin-bottom: 15px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
        }
        input[type="text"], input[type="password"], textarea {
            width: 100%;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 4px;
            box-sizing: border-box;
            font-family: inherit;
            font-size: 14px;
        }
        textarea {
            height: 100px;
            resize: vertical;
        }
        .btn {
            background-color: #3498db;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
            transition: background-color 0.3s;
        }
        .btn:hover {
            background-color: #2980b9;
        }
        .btn-warning {
            background-color: #e67e22;
        }
        .btn-warning:hover {
            background-color: #d35400;
        }
        .btn-success {
            background-color: #2ecc71;
        }
        .btn-success:hover {
            background-color: #27ae60;
        }
        .btn-danger {
            background-color: #e74c3c;
        }
        .btn-danger:hover {
            background-color: #c0392b;
        }
        .section-title {
            margin-top: 30px;
            margin-bottom: 15px;
            color: #2c3e50;
            font-size: 18px;
            font-weight: bold;
        }
        .alert {
            padding: 15px;
            border-radius: 4px;
            margin-bottom: 20px;
        }
        .alert-success {
            background-color: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        .alert-danger {
            background-color: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        .footer {
            margin-top: 50px;
            text-align: center;
            color: #7f8c8d;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <h1>RSI分层极值追踪自动量化交易系统配置</h1>
    
    {% if message %}
    <div class="alert {% if success %}alert-success{% else %}alert-danger{% endif %}">
        {{ message }}
    </div>
    {% endif %}
    
    <form method="post" action="/save">
        <div class="card">
            <h2 class="section-title">交易所API配置</h2>
            
            <div class="form-group">
                <label for="OKX_API_KEY">OKX API Key:</label>
                <input type="text" id="OKX_API_KEY" name="OKX_API_KEY" value="{{ env.get('OKX_API_KEY', '') }}">
            </div>
            
            <div class="form-group">
                <label for="OKX_API_SECRET">OKX API Secret:</label>
                <input type="password" id="OKX_API_SECRET" name="OKX_API_SECRET" value="{{ env.get('OKX_API_SECRET', '') }}">
            </div>
            
            <div class="form-group">
                <label for="OKX_PASSPHRASE">OKX API Passphrase:</label>
                <input type="password" id="OKX_PASSPHRASE" name="OKX_PASSPHRASE" value="{{ env.get('OKX_PASSPHRASE', '') }}">
            </div>
            
            <div class="form-group">
                <label for="OKX_MAX_LEVERAGE">最大杠杆倍数:</label>
                <input type="text" id="OKX_MAX_LEVERAGE" name="OKX_MAX_LEVERAGE" value="{{ env.get('OKX_MAX_LEVERAGE', '50') }}">
            </div>
            
            <div class="form-group">
                <label for="DEBUG_MODE">沙箱模式:</label>
                <select id="DEBUG_MODE" name="DEBUG_MODE">
                    <option value="true" {% if env.get('DEBUG_MODE') == 'true' %}selected{% endif %}>开启</option>
                    <option value="false" {% if env.get('DEBUG_MODE') == 'false' %}selected{% endif %}>关闭</option>
                </select>
            </div>
        </div>
        
        <div class="card">
            <h2 class="section-title">数据库配置</h2>
            
            <div class="form-group">
                <label for="POSTGRES_HOST">数据库主机:</label>
                <input type="text" id="POSTGRES_HOST" name="POSTGRES_HOST" value="{{ env.get('POSTGRES_HOST', 'postgres') }}">
            </div>
            
            <div class="form-group">
                <label for="POSTGRES_PORT">数据库端口:</label>
                <input type="text" id="POSTGRES_PORT" name="POSTGRES_PORT" value="{{ env.get('POSTGRES_PORT', '5432') }}">
            </div>
            
            <div class="form-group">
                <label for="POSTGRES_DB">数据库名称:</label>
                <input type="text" id="POSTGRES_DB" name="POSTGRES_DB" value="{{ env.get('POSTGRES_DB', 'rsi_tracker') }}">
            </div>
            
            <div class="form-group">
                <label for="POSTGRES_USER">数据库用户:</label>
                <input type="text" id="POSTGRES_USER" name="POSTGRES_USER" value="{{ env.get('POSTGRES_USER', 'postgres') }}">
            </div>
            
            <div class="form-group">
                <label for="POSTGRES_PASSWORD">数据库密码:</label>
                <input type="password" id="POSTGRES_PASSWORD" name="POSTGRES_PASSWORD" value="{{ env.get('POSTGRES_PASSWORD', '') }}">
            </div>
        </div>
        
        <div class="card">
            <h2 class="section-title">策略参数配置</h2>
            
            <div class="form-group">
                <label for="RSI_PERIOD">RSI周期:</label>
                <input type="text" id="RSI_PERIOD" name="RSI_PERIOD" value="{{ env.get('RSI_PERIOD', '14') }}">
            </div>
            
            <div class="form-group">
                <label for="LONG_LEVELS">多头RSI级别 (逗号分隔):</label>
                <input type="text" id="LONG_LEVELS" name="LONG_LEVELS" value="{{ env.get('LONG_LEVELS', '30,25,20') }}">
            </div>
            
            <div class="form-group">
                <label for="SHORT_LEVELS">空头RSI级别 (逗号分隔):</label>
                <input type="text" id="SHORT_LEVELS" name="SHORT_LEVELS" value="{{ env.get('SHORT_LEVELS', '70,75,80') }}">
            </div>
            
            <div class="form-group">
                <label for="RETRACEMENT_POINTS">回撤点数:</label>
                <input type="text" id="RETRACEMENT_POINTS" name="RETRACEMENT_POINTS" value="{{ env.get('RETRACEMENT_POINTS', '10') }}">
            </div>
            
            <div class="form-group">
                <label for="MAX_ADDITIONAL_POSITIONS">最大加仓次数:</label>
                <input type="text" id="MAX_ADDITIONAL_POSITIONS" name="MAX_ADDITIONAL_POSITIONS" value="{{ env.get('MAX_ADDITIONAL_POSITIONS', '3') }}">
            </div>
        </div>
        
        <div class="card">
            <h2 class="section-title">系统配置</h2>
            
            <div class="form-group">
                <label for="APP_NAME">系统名称:</label>
                <input type="text" id="APP_NAME" name="APP_NAME" value="{{ env.get('APP_NAME', 'RSI分层极值追踪量化系统') }}">
            </div>
            
            <div class="form-group">
                <label for="LOG_LEVEL">日志级别:</label>
                <select id="LOG_LEVEL" name="LOG_LEVEL">
                    <option value="DEBUG" {% if env.get('LOG_LEVEL') == 'DEBUG' %}selected{% endif %}>DEBUG</option>
                    <option value="INFO" {% if env.get('LOG_LEVEL') == 'INFO' %}selected{% endif %}>INFO</option>
                    <option value="WARNING" {% if env.get('LOG_LEVEL') == 'WARNING' %}selected{% endif %}>WARNING</option>
                    <option value="ERROR" {% if env.get('LOG_LEVEL') == 'ERROR' %}selected{% endif %}>ERROR</option>
                </select>
            </div>
            
            <div class="form-group">
                <label for="DATA_RETENTION_DAYS">数据保留天数:</label>
                <input type="text" id="DATA_RETENTION_DAYS" name="DATA_RETENTION_DAYS" value="{{ env.get('DATA_RETENTION_DAYS', '7') }}">
            </div>
        </div>
        
        <div style="text-align: center; margin-top: 20px;">
            <button type="submit" class="btn btn-success">保存配置</button>
            <a href="/start" class="btn btn-primary" style="margin-left: 10px;">启动系统</a>
        </div>
    </form>
    
    <div class="footer">
        <p>RSI分层极值追踪自动量化交易系统 &copy; 2025</p>
    </div>
</body>
</html>''')


# 路由
@app.get("/", response_class=HTMLResponse)
async def read_config(request: Request, username: str = Depends(get_current_user)):
    env_data = read_env_file()
    return templates.TemplateResponse(
        "config.html", 
        {"request": request, "env": env_data, "message": None, "success": True}
    )


@app.post("/save", response_class=HTMLResponse)
async def save_config(
    request: Request,
    username: str = Depends(get_current_user),
    OKX_API_KEY: str = Form(""),
    OKX_API_SECRET: str = Form(""),
    OKX_PASSPHRASE: str = Form(""),
    OKX_MAX_LEVERAGE: str = Form("50"),
    DEBUG_MODE: str = Form("true"),
    POSTGRES_HOST: str = Form("postgres"),
    POSTGRES_PORT: str = Form("5432"),
    POSTGRES_DB: str = Form("rsi_tracker"),
    POSTGRES_USER: str = Form("postgres"),
    POSTGRES_PASSWORD: str = Form(""),
    RSI_PERIOD: str = Form("14"),
    LONG_LEVELS: str = Form("30,25,20"),
    SHORT_LEVELS: str = Form("70,75,80"),
    RETRACEMENT_POINTS: str = Form("10"),
    MAX_ADDITIONAL_POSITIONS: str = Form("3"),
    APP_NAME: str = Form("RSI分层极值追踪量化系统"),
    LOG_LEVEL: str = Form("INFO"),
    DATA_RETENTION_DAYS: str = Form("7")
):
    # 准备更新数据
    updates = {
        "OKX_API_KEY": OKX_API_KEY,
        "OKX_API_SECRET": OKX_API_SECRET,
        "OKX_PASSPHRASE": OKX_PASSPHRASE,
        "OKX_MAX_LEVERAGE": OKX_MAX_LEVERAGE,
        "DEBUG_MODE": DEBUG_MODE,
        "POSTGRES_HOST": POSTGRES_HOST,
        "POSTGRES_PORT": POSTGRES_PORT,
        "POSTGRES_DB": POSTGRES_DB,
        "POSTGRES_USER": POSTGRES_USER,
        "POSTGRES_PASSWORD": POSTGRES_PASSWORD,
        "RSI_PERIOD": RSI_PERIOD,
        "LONG_LEVELS": LONG_LEVELS,
        "SHORT_LEVELS": SHORT_LEVELS,
        "RETRACEMENT_POINTS": RETRACEMENT_POINTS,
        "MAX_ADDITIONAL_POSITIONS": MAX_ADDITIONAL_POSITIONS,
        "APP_NAME": APP_NAME,
        "LOG_LEVEL": LOG_LEVEL,
        "DATA_RETENTION_DAYS": DATA_RETENTION_DAYS
    }
    
    # 更新环境变量文件
    success = update_env_file(".env", updates)
    
    # 重新读取环境变量
    env_data = read_env_file()
    
    # 返回结果
    message = "配置保存成功！" if success else "配置保存失败，请检查日志。"
    return templates.TemplateResponse(
        "config.html", 
        {"request": request, "env": env_data, "message": message, "success": success}
    )


@app.get("/start")
async def start_system(username: str = Depends(get_current_user)):
    # 这里可以添加启动系统的逻辑
    return RedirectResponse(url="/", status_code=303)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
''')
    
    print_success("配置Web服务器创建成功")
    return True


# 创建Docker配置
def create_docker_files():
    print_step("创建Docker配置文件")
    
    # 创建docker-compose.yml
    docker_compose_file = os.path.join(PROJECT_ROOT, "docker-compose.yml")
    with open(docker_compose_file, "w", encoding="utf-8") as f:
        f.write("""version: '3.8'

services:
  # API服务
  api:
    build:
      context: .
      dockerfile: docker/api/Dockerfile
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - ./app:/app
      - ./logs:/app/logs
      - ./data:/app/data
      - ./backup:/app/backup
    env_file:
      - .env
    depends_on:
      - postgres
      - redis
    networks:
      - rsi_network

  # Celery Worker
  worker:
    build:
      context: .
      dockerfile: docker/celery/Dockerfile
    restart: unless-stopped
    command: celery -A app.tasks.worker_simple worker --loglevel=info
    volumes:
      - ./app:/app
      - ./logs:/app/logs
      - ./data:/app/data
    env_file:
      - .env
    depends_on:
      - redis
      - postgres
    networks:
      - rsi_network

  # Celery Beat
  beat:
    build:
      context: .
      dockerfile: docker/celery/Dockerfile
    restart: unless-stopped
    command: celery -A app.tasks.worker_simple beat --loglevel=info
    volumes:
      - ./app:/app
      - ./logs:/app/logs
    env_file:
      - .env
    depends_on:
      - redis
      - worker
    networks:
      - rsi_network

  # TimescaleDB
  postgres:
    image: timescale/timescaledb:latest-pg15
    restart: unless-stopped
    ports:
      - "5432:5432"
    environment:
      - POSTGRES_USER=${POSTGRES_USER:-postgres}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-changeme}
      - POSTGRES_DB=${POSTGRES_DB:-rsi_tracker}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - rsi_network

  # Redis
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    ports:
      - "6379:6379"
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    networks:
      - rsi_network

  # Nginx (Web服务)
  nginx:
    image: nginx:alpine
    restart: unless-stopped
    ports:
      - "80:80"
    volumes:
      - ./docker/nginx/nginx.conf:/etc/nginx/conf.d/default.conf
      - ./app/static:/usr/share/nginx/html
    depends_on:
      - api
    networks:
      - rsi_network

networks:
  rsi_network:
    driver: bridge

volumes:
  postgres_data:
  redis_data:
""")
    
    # 创建API Dockerfile
    os.makedirs(os.path.join(PROJECT_ROOT, "docker/api"), exist_ok=True)
    with open(os.path.join(PROJECT_ROOT, "docker/api/Dockerfile"), "w", encoding="utf-8") as f:
        f.write("""FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 创建必要的目录
RUN mkdir -p /app/logs /app/data /app/backup

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
""")
    
    # 创建Celery Dockerfile
    os.makedirs(os.path.join(PROJECT_ROOT, "docker/celery"), exist_ok=True)
    with open(os.path.join(PROJECT_ROOT, "docker/celery/Dockerfile"), "w", encoding="utf-8") as f:
        f.write("""FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 创建必要的目录
RUN mkdir -p /app/logs /app/data
""")
    
    # 创建Nginx配置
    os.makedirs(os.path.join(PROJECT_ROOT, "docker/nginx"), exist_ok=True)
    with open(os.path.join(PROJECT_ROOT, "docker/nginx/nginx.conf"), "w", encoding="utf-8") as f:
        f.write("""server {
    listen 80;
    server_name localhost;

    location / {
        root /usr/share/nginx/html;
        index index.html;
        try_files $uri $uri/ /index.html;
    }

    location /api {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /docs {
        proxy_pass http://api:8000/docs;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /openapi.json {
        proxy_pass http://api:8000/openapi.json;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /ws {
        proxy_pass http://api:8000/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
""")
    
    print_success("Docker配置文件创建成功")
    return True


# 启动配置服务器
def start_config_server():
    print_step("启动配置服务器")
    
    # 检查是否已安装uvicorn和fastapi
    try:
        import uvicorn
        import fastapi
    except ImportError:
        print_warning("缺少uvicorn或fastapi模块，正在安装...")
        if not run_command(f"{sys.executable} -m pip install fastapi uvicorn jinja2"):
            print_error("安装uvicorn和fastapi失败")
            return False
    
    # 检查端口是否被占用
    if is_port_in_use(8000):
        print_error("端口8000已被占用，请关闭占用该端口的程序后重试")
        return False
    
    # 启动配置服务器
    config_server_path = os.path.join(PROJECT_ROOT, "config_server.py")
    
    print_info("正在启动配置服务器...")
    print_info("请在浏览器中访问: http://localhost:8000")
    
    # 设置可执行权限
    if platform.system() != "Windows":
        os.chmod(config_server_path, 0o755)
    
    # 在新进程中启动服务器
    if platform.system() == "Windows":
        subprocess.Popen([sys.executable, config_server_path], creationflags=subprocess.CREATE_NEW_CONSOLE)
    else:
        subprocess.Popen([sys.executable, config_server_path], start_new_session=True)
    
    # 等待服务器启动
    time.sleep(2)
    
    # 尝试打开浏览器
    try:
        webbrowser.open("http://localhost:8000")
    except:
        print_info("无法自动打开浏览器，请手动访问: http://localhost:8000")
    
    print_success("配置服务器已启动")
    return True


# 主函数
def main():
    print_title("RSI分层极值追踪自动量化交易系统安装程序")
    
    # 解析命令行参数
    args = parse_args()
    
    # 设置日志级别
    if args.debug:
        logger.setLevel(logging.DEBUG)
    
    # 检查环境
    if not check_python_version():
        return 1
    
    check_os()
    
    if not args.no_docker and not check_docker():
        print_warning("Docker检查失败，将使用非Docker模式安装")
        args.no_docker = True
    
    if not check_dependencies(args):
        print_warning("依赖检查失败，可能会影响系统运行")
    
    # 创建目录结构
    if not args.config_only and not create_directory_structure():
        print_error("创建目录结构失败")
        return 1
    
    # 创建环境变量文件
    if not create_env_file():
        print_error("创建环境变量文件失败")
        return 1
    
    # 创建Docker配置
    if not args.no_docker and not args.config_only and not create_docker_files():
        print_error("创建Docker配置文件失败")
        return 1
    
    # 创建配置服务器
    if not create_config_server():
        print_error("创建配置服务器失败")
        return 1
    
    # 启动配置服务器
    if not start_config_server():
        print_error("启动配置服务器失败")
        return 1
    
    print_title("安装完成")
    print_info("请在浏览器中完成系统配置")
    print_info("配置完成后，可以使用以下命令启动系统:")
    
    if not args.no_docker:
        print_color("docker-compose up -d", Colors.GREEN)
    else:
        print_color(f"{sys.executable} -m app.main", Colors.GREEN)
    
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print_warning("\n安装已取消")
        sys.exit(1)
    except Exception as e:
        print_error(f"安装过程中发生错误: {e}")
        logger.exception("安装失败")
        sys.exit(1)
