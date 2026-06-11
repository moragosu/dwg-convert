#!/usr/bin/env python3
"""
DWG → 3D STEP 변환기 진입점.
사용법: python3 main.py
"""
import os
import sys

# WSL2: X 서버가 없으면 DISPLAY 자동 설정
if sys.platform.startswith("linux") and "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":0"


def _check_deps() -> None:
    missing = []
    try:
        import ezdxf  # noqa: F401
    except ImportError:
        missing.append("ezdxf       →  uv sync")
    try:
        import shapely  # noqa: F401
    except ImportError:
        missing.append("shapely     →  uv sync")
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        missing.append("matplotlib  →  uv sync")
    try:
        import tkinter  # noqa: F401
    except ImportError:
        missing.append("tkinter     →  sudo apt-get install python3-tk")

    if missing:
        print("누락된 패키지:")
        for m in missing:
            print(f"  {m}")
        sys.exit(1)


def main() -> None:
    """uv run dwg-convert 또는 python main.py 진입점."""
    _check_deps()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from gui.app import MainApp
    app = MainApp()
    app.mainloop()


if __name__ == "__main__":
    main()
