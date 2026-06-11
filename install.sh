#!/bin/bash
# DWG → 3D STEP 변환기 설치 스크립트
set -e

LIBREDWG_VERSION="0.13.3"
DWG2DXF_DEST="$HOME/.local/bin/dwg2dxf"

# ── 1. uv 설치 확인 ────────────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
    echo "=== uv 설치 중 ==="
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# ── 2. Python 패키지 설치 ──────────────────────────────────────────────────
echo "=== Python 패키지 설치 (uv sync) ==="
uv sync

# ── 3. tkinter (시스템 패키지) ─────────────────────────────────────────────
echo "=== 시스템 패키지 확인 ==="
if python3 -c "import tkinter" 2>/dev/null; then
    echo "  tkinter: OK"
else
    echo "  tkinter 설치 중..."
    sudo apt-get install -y python3-tk
fi

# ── 4. LibreDWG (dwg2dxf) ─────────────────────────────────────────────────
echo "=== DWG 변환 도구 확인 ==="
if command -v dwg2dxf &>/dev/null || [ -f "$DWG2DXF_DEST" ]; then
    echo "  dwg2dxf: OK"
else
    echo "  dwg2dxf 미설치 → 설치 시도 중..."

    # 방법 1: apt (가장 빠름, Ubuntu universe 저장소)
    if command -v apt-get &>/dev/null; then
        echo "  [방법 1] apt-get install libredwg-utils 시도..."
        if sudo apt-get install -y libredwg-utils 2>/dev/null && command -v dwg2dxf &>/dev/null; then
            echo "  dwg2dxf apt 설치 완료"
            exit 0  # 이후 빌드 불필요
        fi
    fi

    echo "  apt 설치 실패 → 소스 빌드로 전환..."

    # 빌드 의존성 확인
    for pkg in gcc make autoconf; do
        if ! command -v $pkg &>/dev/null; then
            echo "  빌드 도구 설치 중..."
            sudo apt-get install -y build-essential autoconf libtool
            break
        fi
    done

    # 다운로드 & 빌드
    TMP_SRC="/tmp/libredwg-${LIBREDWG_VERSION}"
    if [ ! -d "$TMP_SRC" ]; then
        TARBALL="/tmp/libredwg.tar.gz"
        URLS=(
            "https://github.com/LibreDWG/libredwg/releases/download/${LIBREDWG_VERSION}/libredwg-${LIBREDWG_VERSION}.tar.gz"
            "http://ftpmirror.gnu.org/libredwg/libredwg-${LIBREDWG_VERSION}.tar.gz"
            "https://mirror.fcix.net/gnu/libredwg/libredwg-${LIBREDWG_VERSION}.tar.gz"
            "http://ftp.gnu.org/gnu/libredwg/libredwg-${LIBREDWG_VERSION}.tar.gz"
        )
        DOWNLOADED=0
        for URL in "${URLS[@]}"; do
            echo "  다운로드 시도: $URL"
            if curl -fsSL --connect-timeout 15 "$URL" -o "$TARBALL" 2>/dev/null; then
                DOWNLOADED=1
                break
            fi
        done
        if [ "$DOWNLOADED" -eq 0 ]; then
            echo "  [오류] LibreDWG 다운로드 실패."
            echo "  수동 설치: https://github.com/LibreDWG/libredwg/releases"
            echo "  또는 DWG 대신 DXF 파일을 직접 사용하세요."
            exit 1
        fi
        tar xzf "$TARBALL" -C /tmp
    fi

    # fake pkg-config (의존성 없이 빌드)
    mkdir -p /tmp/fakepkg
    cat > /tmp/fakepkg/pkg-config << 'SH'
#!/bin/sh
exit 0
SH
    chmod +x /tmp/fakepkg/pkg-config

    mkdir -p "$HOME/.local/bin"
    cd "$TMP_SRC"
    PATH=/tmp/fakepkg:$PATH ./configure \
        --disable-bindings \
        --prefix="$HOME/.local" \
        --silent
    make -j"$(nproc)" CFLAGS="-O2 -Wno-error" --quiet
    make install --quiet
    cd -

    if [ -f "$DWG2DXF_DEST" ]; then
        echo "  dwg2dxf 설치 완료: $DWG2DXF_DEST"
    else
        echo "  [경고] dwg2dxf 빌드 실패 — DWG 대신 DXF 파일을 직접 사용하세요."
    fi
fi

echo ""
echo "=== 설치 완료 ==="
echo "실행 방법:"
echo "  uv run python main.py"
