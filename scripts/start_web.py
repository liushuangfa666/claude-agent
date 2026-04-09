#!/usr/bin/env python3
"""
Claude Agent Web Dashboard 启动脚本

用法:
  python3 start_web.py           # 前台运行
  python3 start_web.py --port 18779  # 指定端口
  nohup python3 start_web.py &  # 后台运行
"""
import json
import os
import sys

# 把 scripts 目录加入路径（__file__ = scripts/start_web.py）
_scripts_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_scripts_dir)
sys.path.insert(0, _project_root)

# 切换到配置的 workspace（如果存在）
_config_paths = [
    os.path.join(_project_root, "claude.json"),
    os.path.expanduser("~/.config/crush/crush.json"),
]
for config_path in _config_paths:
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                config = json.load(f)
            workspace = config.get("workspace")
            if workspace and os.path.isdir(workspace):
                os.chdir(workspace)
                print(f"切换到 workspace: {workspace}")
        except Exception:
            pass
        break

import argparse  # noqa: E402, I001
from web_server import start_server  # noqa: E402, I001

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=18780)
    args = parser.parse_args()

    print("=" * 50)
    print("Claude Agent Web Dashboard")
    print("=" * 50)
    print(f"Dashboard: http://localhost:{args.port}")
    print(f"API:       http://localhost:{args.port}/api/status")
    print()
    print("Press Ctrl+C to stop")
    print("=" * 50)

    start_server(port=args.port)
