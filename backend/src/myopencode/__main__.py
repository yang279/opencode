"""myopencode 后端入口。

启动 FastAPI 服务，并向 stdout 打印握手行供 Rust 壳层读取：
    {"port": 8787, "token": "..."}

开发模式：python -m myopencode --port 0
发布模式：PyInstaller 打成的 sidecar 二进制。
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys

from .config.loader import load_config
from .core.observability import setup_logging
from .server.app import create_app


def _free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def _is_root_path(path: str) -> bool:
    """判断路径是否为文件系统根（防止工作目录漂移到 / 或盘符根）。"""
    real = os.path.realpath(os.path.abspath(path))
    if real in ("/", os.sep):
        return True
    if os.name == "nt":
        stripped = real.rstrip("\\/")
        return len(stripped) <= 2 and stripped.endswith(":")
    return False


def _default_workspace() -> str:
    home = os.path.expanduser("~")
    workspace = os.path.join(home, "myopencode")
    os.makedirs(workspace, exist_ok=True)
    return workspace


def _normalize_working_dir(wd: str | None) -> str:
    """规范化工作目录：空/相对 "." 取 cwd；若落在根目录则回退到 ~/myopencode。

    返回前确保目录存在（首次运行自动创建），再 realpath 归一。
    """
    if not wd or wd == ".":
        wd = os.getcwd()
    if _is_root_path(wd):
        wd = _default_workspace()
    wd = os.path.realpath(os.path.abspath(wd))
    os.makedirs(wd, exist_ok=True)
    return wd


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="myopencode backend")
    parser.add_argument("--host", default=os.environ.get("MYOPENCODE_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MYOPENCODE_PORT", "0") or 0),
        help="0 = 自动分配",
    )
    parser.add_argument("--config", default=None, help="配置文件路径")
    parser.add_argument("--working-dir", default=None, help="覆盖工作目录")
    parser.add_argument("--token", default=os.environ.get("MYOPENCODE_TOKEN"), help="固定 token（开发用）")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    # 优先级：config.json 显式配置的 working_dir（非空且非 "."）优先，
    # 否则用 --working-dir（Rust 壳层传入的默认值）兜底。
    configured = (config.working_dir or "").strip()
    if configured and configured != ".":
        config.working_dir = _normalize_working_dir(configured)
    else:
        config.working_dir = _normalize_working_dir(args.working_dir or config.working_dir)

    setup_logging(config.observability)

    port = args.port if args.port else _free_port(args.host)

    # 握手行：服务真正就绪（lifespan startup）后再打印，Rust 据此拿到 port + token
    def _announce(_app) -> None:
        handshake = json.dumps({"port": port, "token": _app.state.token})
        print(handshake, flush=True)

    app = create_app(config, token=args.token, on_startup=_announce)

    import uvicorn

    uvicorn.run(app, host=args.host, port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())