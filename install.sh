#!/bin/bash
# DWG → 3D STEP 변환기 설치 스크립트
set -e

# ── 1. uv 설치 확인 ────────────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
    echo "uv 설치 중..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# ── 2. Python 패키지 설치 (pyproject.toml 기반) ───────────────────────────
echo "=== Python 패키지 설치 (uv sync) ==="
uv sync

# ── 3. 시스템 패키지 (tkinter) ────────────────────────────────────────────
echo ""
echo "=== 시스템 패키지 확인 ==="
if python3 -c "import tkinter" 2>/dev/null; then
    echo "  tkinter: OK"
else
    echo "  tkinter 미설치 → 설치 중..."
    sudo apt-get install -y python3-tk
fi

# ── 4. DWG 변환 도구 (선택) ───────────────────────────────────────────────
echo ""
echo "=== DWG 직접 변환 도구 (선택사항) ==="
if command -v dwg2dxf &>/dev/null || [ -f /tmp/libredwg-0.13.4/programs/dwg2dxf ]; then
    echo "  dwg2dxf: OK"
else
    echo "  dwg2dxf 미설치 — DWG 파일 사용 시 아래 중 하나 설치:"
    echo "    sudo apt-get install libredwg-utils"
    echo "    또는 ODA File Converter: https://www.opendesign.com/guestfiles/oda_file_converter"
fi

echo ""
echo "=== 설치 완료 ==="
echo "실행 방법:"
echo "  uv run python main.py"
echo "  또는: uv run dwg-convert"
