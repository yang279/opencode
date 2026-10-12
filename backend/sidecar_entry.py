"""PyInstaller 打包入口：调用 myopencode 后端 main。"""
import sys

from myopencode.__main__ import main

if __name__ == "__main__":
    sys.exit(main())