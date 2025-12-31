#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Echoman 后端服务启动脚本

此脚本可以启动所有后端服务：
- FastAPI (API 服务器)
- Celery Worker (异步任务执行器)
- Celery Beat (定时任务调度器)

使用方法:
    python backend.py              # 交互式选择要启动的服务
    python backend.py --all        # 启动所有服务
    python backend.py --api        # 仅启动 API 服务器
    python backend.py --worker     # 仅启动 Celery Worker
    python backend.py --beat       # 仅启动 Celery Beat
    python backend.py --api --worker --beat  # 启动指定的多个服务
    python backend.py --all --db --restart-celery  # 启动全部服务并自动拉起数据库、重启已有的 celery
"""

import os
import sys
import subprocess
import time
import signal
import argparse
from pathlib import Path
from typing import List

def activate_conda_and_run_command(command, shell=False, check=True):
    """
    在 conda echoman 环境中运行命令
    
    Args:
        command: 要运行的命令（列表或字符串）
        shell: 是否使用 shell 模式
        check: 是否检查返回码
    
    Returns:
        subprocess.CompletedProcess 对象
    """
    conda_sh = "/root/anaconda3/etc/profile.d/conda.sh"
    
    if isinstance(command, list):
        command_str = " ".join(command)
    else:
        command_str = command
    
    # 组合激活 conda 环境和运行命令
    full_command = f"source {conda_sh} && conda activate echoman && {command_str}"
    
    return subprocess.run(full_command, shell=True, check=check, executable="/bin/bash")

def check_port(port):
    """检查端口是否被占用"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def check_postgres():
    """检查 PostgreSQL 是否运行"""
    print("🔍 检查 PostgreSQL 连接...")
    try:
        result = activate_conda_and_run_command(
            "python -c \"import psycopg2; conn = psycopg2.connect('dbname=echoman user=echoman password=echoman_password host=localhost'); conn.close(); print('OK')\"",
            check=False
        )
        return result.returncode == 0
    except:
        return False

def check_redis():
    """检查 Redis 是否运行"""
    print("🔍 检查 Redis 连接...")
    try:
        result = activate_conda_and_run_command(
            "python -c \"import redis; r = redis.Redis(host='localhost', port=6379); r.ping(); print('OK')\"",
            check=False
        )
        return result.returncode == 0
    except:
        return False

def start_database_services():
    """启动数据库服务（使用 Docker）"""
    print("\n📦 启动数据库服务...")
    print("提示: 使用 Docker 启动 PostgreSQL 和 Redis")
    
    backend_dir = Path(__file__).parent / "backend"
    os.chdir(backend_dir)
    
    try:
        # 只启动数据库服务
        subprocess.run(
            ["docker-compose", "up", "-d", "postgres", "redis"],
            check=True
        )
        print("✅ 数据库服务启动成功")
        
        # 等待数据库就绪
        print("⏳ 等待数据库就绪...")
        time.sleep(5)
        
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 数据库服务启动失败: {e}")
        return False
    except FileNotFoundError:
        print("❌ 未找到 docker-compose 命令")
        print("💡 请手动启动 PostgreSQL 和 Redis，或安装 Docker")
        return False

def install_dependencies(backend_dir):
    """安装 Python 依赖"""
    print("\n📦 检查 Python 依赖...")
    
    requirements_file = backend_dir / "requirements.txt"
    if not requirements_file.exists():
        print(f"❌ 错误: requirements.txt 不存在: {requirements_file}")
        return False
    
    # 检查是否需要安装依赖
    try:
        result = activate_conda_and_run_command(
            "python -c \"import fastapi; import sqlalchemy; import celery\"",
            check=False
        )
        
        if result.returncode == 0:
            print("✅ 依赖已安装")
            return True
        else:
            print("📦 检测到依赖未完整安装，正在安装...")
    except:
        print("📦 正在安装依赖...")
    
    try:
        activate_conda_and_run_command(f"pip install -r {requirements_file}")
        print("✅ 依赖安装完成")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 依赖安装失败: {e}")
        return False

def init_database(backend_dir):
    """初始化数据库"""
    print("\n🗄️  初始化数据库...")
    
    os.chdir(backend_dir)
    
    # 创建数据库初始化脚本
    init_script = """
import asyncio
from app.core.database import engine
from app.models import Base

async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ 数据库表创建完成")

if __name__ == "__main__":
    asyncio.run(create_tables())
"""
    
    try:
        # 创建临时初始化脚本
        script_path = backend_dir / "init_db_temp.py"
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(init_script)
        
        # 创建所有表
        print("📝 创建数据库表...")
        result = activate_conda_and_run_command(
            f"python {script_path}",
            check=False
        )
        
        # 删除临时脚本
        script_path.unlink(missing_ok=True)
        
        print("✅ 数据库初始化完成")
        return True
    except Exception as e:
        print(f"⚠️  数据库初始化警告: {e}")
        print("💡 如果数据库表已存在，可以忽略此警告")
        return True

# 全局变量用于跟踪子进程
processes = []

def signal_handler(sig, frame):
    """处理 Ctrl+C 信号，优雅关闭所有服务"""
    print("\n\n🛑 正在停止所有服务...")
    for proc in processes:
        if proc.poll() is None:  # 进程仍在运行
            proc.terminate()
    
    # 等待所有进程结束
    time.sleep(2)
    for proc in processes:
        if proc.poll() is None:
            proc.kill()
    
    print("👋 所有服务已停止")
    sys.exit(0)


def start_api_server(backend_dir: Path):
    """
    启动 FastAPI 服务器
    
    Args:
        backend_dir: 后端目录路径
        
    Returns:
        subprocess.Popen 对象
    """
    print("\n🚀 启动 FastAPI 服务器...")
    conda_sh = "/root/anaconda3/etc/profile.d/conda.sh"
    command = f"source {conda_sh} && conda activate echoman && cd {backend_dir} && uvicorn app.main:app --reload --host 0.0.0.0 --port 8778"
    
    proc = subprocess.Popen(
        command,
        shell=True,
        executable="/bin/bash",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    print("✅ FastAPI 服务器已启动 (端口 8778)")
    print("   📄 API 文档: http://localhost:8778/docs")
    print("   🩺 健康检查: http://localhost:8778/health")
    
    return proc


def start_celery_worker(backend_dir: Path):
    """
    启动 Celery Worker
    
    Args:
        backend_dir: 后端目录路径
        
    Returns:
        subprocess.Popen 对象
    """
    print("\n⚙️  启动 Celery Worker...")
    conda_sh = "/root/anaconda3/etc/profile.d/conda.sh"
    command = f"source {conda_sh} && conda activate echoman && cd {backend_dir} && celery -A app.tasks.celery_app worker --loglevel=info"
    
    proc = subprocess.Popen(
        command,
        shell=True,
        executable="/bin/bash",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    print("✅ Celery Worker 已启动")
    print("   ⚡ 可执行异步任务")
    
    return proc


def start_celery_beat(backend_dir: Path):
    """
    启动 Celery Beat
    
    Args:
        backend_dir: 后端目录路径
        
    Returns:
        subprocess.Popen 对象
    """
    print("\n⏰ 启动 Celery Beat...")
    conda_sh = "/root/anaconda3/etc/profile.d/conda.sh"
    command = f"source {conda_sh} && conda activate echoman && cd {backend_dir} && celery -A app.tasks.celery_app beat --loglevel=info"
    
    proc = subprocess.Popen(
        command,
        shell=True,
        executable="/bin/bash",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    print("✅ Celery Beat 已启动")
    print("   📅 定时任务调度器运行中")
    print("   🕐 采集时间: 8:00, 10:00, 12:00, 14:00, 16:00, 18:00, 20:00, 22:00")
    
    return proc


def stop_running_celery():
    """尝试停止已存在的 celery worker/beat（粗粒度 pkill）"""
    print("🛑 停止已运行的 Celery worker/beat（如有）...")
    subprocess.run("pkill -f \"celery -A app.tasks.celery_app [w]orker\"", shell=True)
    subprocess.run("pkill -f \"celery -A app.tasks.celery_app [b]eat\"", shell=True)
    time.sleep(1)


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="Echoman 后端服务启动脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python backend.py              # 交互式选择服务
  python backend.py --all        # 启动所有服务
  python backend.py --api        # 仅启动 API 服务器
  python backend.py --worker     # 仅启动 Celery Worker
  python backend.py --beat       # 仅启动 Celery Beat
  python backend.py --api --worker --beat  # 启动指定的多个服务
        """
    )
    
    parser.add_argument("--all", action="store_true", help="启动所有服务（API + Worker + Beat）")
    parser.add_argument("--api", action="store_true", help="启动 FastAPI 服务器")
    parser.add_argument("--worker", action="store_true", help="启动 Celery Worker")
    parser.add_argument("--beat", action="store_true", help="启动 Celery Beat")
    parser.add_argument("--db", action="store_true", help="启动数据库服务（PostgreSQL + Redis，需 docker-compose）")
    parser.add_argument("--no-check", action="store_true", help="跳过数据库和依赖检查（不推荐）")
    parser.add_argument("--restart-celery", action="store_true", help="启动前尝试停止已存在的 Celery worker/beat 进程（pkill）")
    
    return parser.parse_args()


def interactive_service_selection():
    """交互式选择要启动的服务"""
    print("\n" + "=" * 70)
    print("🎯 请选择要启动的服务")
    print("=" * 70)
    print()
    print("1. 启动所有服务 (API + Worker + Beat) - 推荐用于完整功能")
    print("2. 仅启动 API 服务器 - 用于快速开发/测试 API")
    print("3. 仅启动 Celery Worker - 用于执行异步任务")
    print("4. 仅启动 Celery Beat - 用于定时任务调度")
    print("5. 自定义组合")
    print("0. 退出")
    print()
    
    while True:
        choice = input("请选择 (0-5) [1]: ").strip()
        
        if choice == "" or choice == "1":
            return {"api": True, "worker": True, "beat": True}
        elif choice == "2":
            return {"api": True, "worker": False, "beat": False}
        elif choice == "3":
            return {"api": False, "worker": True, "beat": False}
        elif choice == "4":
            return {"api": False, "worker": False, "beat": True}
        elif choice == "5":
            services = {"api": False, "worker": False, "beat": False}
            
            api = input("启动 FastAPI 服务器? (y/n) [y]: ").strip().lower()
            services["api"] = api in ['', 'y', 'yes']
            
            worker = input("启动 Celery Worker? (y/n) [y]: ").strip().lower()
            services["worker"] = worker in ['', 'y', 'yes']
            
            beat = input("启动 Celery Beat? (y/n) [y]: ").strip().lower()
            services["beat"] = beat in ['', 'y', 'yes']
            
            if not any(services.values()):
                print("⚠️  至少需要选择一个服务！")
                continue
            
            return services
        elif choice == "0":
            print("👋 已取消")
            sys.exit(0)
        else:
            print("❌ 无效选择，请重新输入")


def main():
    """
    启动后端服务
    """
    # 解析命令行参数
    args = parse_arguments()
    
    # 获取脚本所在目录（项目根目录）
    root_dir = Path(__file__).parent.absolute()
    backend_dir = root_dir / "backend"
    
    # 检查后端目录是否存在
    if not backend_dir.exists():
        print(f"❌ 错误: 后端目录不存在: {backend_dir}")
        sys.exit(1)
    
    print("=" * 70)
    print("🚀 Echoman 后端服务管理器")
    print("=" * 70)
    print(f"📂 后端目录: {backend_dir}")
    print(f"🐍 使用 conda echoman 环境")
    print()
    
    # 确定要启动的服务
    if args.all:
        services = {"api": True, "worker": True, "beat": True}
    elif args.api or args.worker or args.beat:
        services = {
            "api": args.api,
            "worker": args.worker,
            "beat": args.beat
        }
    else:
        # 交互式选择
        services = interactive_service_selection()
    
    # 显示将要启动的服务
    print("\n📋 将启动以下服务:")
    if services["api"]:
        print("  ✅ FastAPI 服务器 (端口 8778)")
    if services["worker"]:
        print("  ✅ Celery Worker (异步任务)")
    if services["beat"]:
        print("  ✅ Celery Beat (定时调度)")
    if args.db:
        print("  ✅ 自动启动数据库服务 (PostgreSQL + Redis, docker-compose)")
    print()
    
    # 步骤 1: 检查数据库服务（除非指定跳过）
    if not args.no_check:
        # 如指定 --db，优先尝试启动数据库服务
        if args.db:
            if not start_database_services():
                sys.exit(1)
        
        postgres_ok = check_postgres()
        redis_ok = check_redis()
        
        if not postgres_ok or not redis_ok:
            print("\n⚠️  数据库服务未运行")
            
            if args.db:
                print("❌ 已尝试自动启动数据库，但仍无法连接，请检查 docker-compose 及网络配置")
                sys.exit(1)
            
            print()
            print("您可以选择以下任一方式启动数据库:")
            print("  1. 使用 Docker (快速方便)")
            print("  2. 使用本地安装 (完全控制)")
            print()
            
            # 询问是否自动启动
            response = input("是否使用 Docker 自动启动数据库服务? (y/n) [y]: ").strip().lower()
            if response in ['', 'y', 'yes']:
                if not start_database_services():
                    print("\n❌ 无法启动数据库服务")
                    print()
                    print("💡 请选择以下方式之一启动数据库:")
                    print()
                    print("方式一：使用 Docker（推荐用于快速开始）")
                    print("  cd backend && docker-compose up -d postgres redis")
                    print()
                    print("方式二：本地安装（推荐用于生产环境）")
                    print("  查看详细教程: backend/INSTALL_LOCAL_DATABASE.md")
                    print()
                    sys.exit(1)
                
                # 重新检查
                postgres_ok = check_postgres()
                redis_ok = check_redis()
                
                if not postgres_ok or not redis_ok:
                    print("❌ 数据库服务启动后仍无法连接，请检查配置")
                    sys.exit(1)
            else:
                print("\n💡 请手动启动数据库服务:")
                print()
                print("方式一：使用 Docker")
                print("  cd backend && docker-compose up -d postgres redis")
                print()
                print("方式二：本地安装")
                print("  查看详细教程: backend/INSTALL_LOCAL_DATABASE.md")
                print()
                print("数据库连接配置:")
                print("  - PostgreSQL: localhost:5432 (用户: echoman, 密码: echoman_password)")
                print("  - Redis: localhost:6379")
                print()
                sys.exit(1)
        else:
            print("✅ PostgreSQL 已运行")
            print("✅ Redis 已运行")
        
        # 步骤 2: 安装依赖
        if not install_dependencies(backend_dir):
            sys.exit(1)
        
        # 步骤 3: 初始化数据库
        init_database(backend_dir)
        
        # 步骤 4: 检查端口
        if services["api"] and check_port(8778):
            print("\n⚠️  警告: 端口 8778 已被占用")
            # 在后台模式下自动跳过，前台模式下询问
            if sys.stdin.isatty():
                response = input("是否继续? (y/n) [n]: ").strip().lower()
                if response not in ['y', 'yes']:
                    sys.exit(1)
            else:
                print("   后台模式：自动跳过端口检查")
    
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 如需要，先停止已有的 celery 进程，避免重复启动
    if args.restart_celery and (services["worker"] or services["beat"]):
        stop_running_celery()
    
    # 启动选定的服务
    print("\n" + "=" * 70)
    print("🎬 正在启动服务...")
    print("=" * 70)
    
    try:
        if services["api"]:
            proc = start_api_server(backend_dir)
            processes.append(proc)
            time.sleep(2)  # 等待 API 服务器启动
        
        if services["worker"]:
            proc = start_celery_worker(backend_dir)
            processes.append(proc)
            time.sleep(2)  # 等待 Worker 启动
        
        if services["beat"]:
            proc = start_celery_beat(backend_dir)
            processes.append(proc)
            time.sleep(2)  # 等待 Beat 启动
        
        print("\n" + "=" * 70)
        print("✅ 所有服务已启动")
        print("=" * 70)
        print()
        print("📝 提示:")
        print("  - 按 Ctrl+C 停止所有服务")
        if services["api"]:
            print("  - API 文档: http://localhost:8778/docs")
            print("  - 健康检查: http://localhost:8778/health")
        if services["beat"]:
            print("  - 下次自动采集时间: 见上方输出")
        print()
        print("💡 服务日志实时输出中...")
        print("=" * 70)
        print()
        
        # 监控所有进程，显示日志
        while True:
            for proc in processes[:]:  # 使用副本遍历
                if proc.poll() is not None:
                    # 进程已结束
                    print(f"\n❌ 服务意外停止 (退出码: {proc.returncode})")
                    # 停止所有服务
                    signal_handler(None, None)
                
                # 读取并显示输出
                if proc.stdout:
                    line = proc.stdout.readline()
                    if line:
                        print(line.rstrip())
            
            time.sleep(0.1)
            
    except Exception as e:
        print(f"\n❌ 启动服务时出错: {e}")
        signal_handler(None, None)


if __name__ == "__main__":
    main()
