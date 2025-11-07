#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
前端启动脚本
运行此脚本以启动 Echoman 前端开发服务器
"""

import os
import sys
import subprocess
from pathlib import Path

def activate_conda_and_run_command(command, shell=False):
    """
    在 conda echoman 环境中运行命令
    
    Args:
        command: 要运行的命令（列表或字符串）
        shell: 是否使用 shell 模式
    
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
    
    return subprocess.run(full_command, shell=True, check=True, executable="/bin/bash")

def main():
    """
    启动前端开发服务器
    """
    # 获取脚本所在目录（项目根目录）
    root_dir = Path(__file__).parent.absolute()
    frontend_dir = root_dir / "frontend"
    
    # 检查前端目录是否存在
    if not frontend_dir.exists():
        print(f"❌ 错误: 前端目录不存在: {frontend_dir}")
        sys.exit(1)
    
    # 切换到前端目录
    os.chdir(frontend_dir)
    print(f"📂 切换到前端目录: {frontend_dir}")
    print(f"🐍 使用 conda echoman 环境")
    
    # 检查 node_modules 是否存在
    node_modules = frontend_dir / "node_modules"
    if not node_modules.exists():
        print("📦 检测到依赖未安装，正在安装依赖...")
        try:
            activate_conda_and_run_command("npm install")
            print("✅ 依赖安装完成")
        except subprocess.CalledProcessError as e:
            print(f"❌ 依赖安装失败: {e}")
            sys.exit(1)
        except FileNotFoundError:
            print("❌ 错误: 未找到 npm 命令，请先安装 Node.js")
            sys.exit(1)
    
    # 启动前端开发服务器
    print("\n🚀 正在启动前端开发服务器...")
    print("📝 提示: 按 Ctrl+C 停止服务器")
    print("🌐 服务器将监听所有网络接口，可远程访问")
    print("=" * 60)
    
    try:
        # 运行 npm run dev --host 以允许远程访问
        activate_conda_and_run_command("npm run dev -- --host")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ 前端服务器启动失败: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n👋 前端服务器已停止")
        sys.exit(0)
    except FileNotFoundError:
        print("❌ 错误: 未找到 npm 命令，请先安装 Node.js")
        sys.exit(1)

if __name__ == "__main__":
    main()

