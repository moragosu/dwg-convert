"""
DWG/DXF 파일 읽기 모듈.
DWG: ODA File Converter → dwg2dxf 순으로 DXF 변환 시도.
DXF: ezdxf로 직접 읽기.
"""
import os
import re
import subprocess
import tempfile
from pathlib import Path

import ezdxf
from ezdxf.document import Drawing

# LibreDWG 빌드 경로 (소스 빌드 시)
_LIBREDWG_DWG2DXF = "/tmp/libredwg-0.13.4/programs/dwg2dxf"
_LIBREDWG_LIBS    = "/tmp/libredwg-0.13.4/src/.libs"


def read_dwg_or_dxf(file_path: str) -> Drawing:
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext == ".dxf":
        return _read_dxf(file_path)
    elif ext == ".dwg":
        return _read_dwg(file_path)
    else:
        raise ValueError(f"지원하지 않는 파일 형식: {ext}\n.dwg 또는 .dxf 파일을 선택하세요.")


def _preprocess_dxf(dxf_path: str) -> str:
    """
    LibreDWG가 생성한 DXF의 SORTENTSTABLE 엔티티 제거.
    그룹코드 331이 잘못 쓰여 ezdxf가 DXFStructureError를 냄.
    전처리된 내용을 새 임시 파일에 저장하고 경로 반환.
    """
    with open(dxf_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    fixed = re.sub(
        r"  0\r?\nSORTENTSTABLE\r?\n.*?(?=  0\r?\n(?!SORTENTSTABLE))",
        "",
        content,
        flags=re.DOTALL,
    )

    if fixed == content:
        return dxf_path  # 변경 없으면 원본 그대로

    tmp = Path(dxf_path).with_name(Path(dxf_path).stem + "_fixed.dxf")
    with open(str(tmp), "w", encoding="utf-8") as f:
        f.write(fixed)
    return str(tmp)


def _read_dxf(file_path: str, preprocess: bool = False) -> Drawing:
    try:
        path = _preprocess_dxf(file_path) if preprocess else file_path
        doc = ezdxf.readfile(path)
        return doc
    except ezdxf.DXFStructureError:
        # 전처리 없이 실패하면 전처리 후 재시도
        if not preprocess:
            return _read_dxf(file_path, preprocess=True)
        raise
    except Exception as e:
        raise RuntimeError(f"DXF 읽기 실패: {e}")


def _read_dwg(file_path: str) -> Drawing:
    with tempfile.TemporaryDirectory() as tmpdir:
        dxf_path = _try_oda_convert(file_path, tmpdir)
        if dxf_path:
            return _read_dxf(dxf_path)

        dxf_path = _try_libdwg_convert(file_path, tmpdir)
        if dxf_path:
            return _read_dxf(dxf_path)

    raise RuntimeError(
        "DWG 파일을 직접 변환할 수 없습니다.\n\n"
        "해결 방법:\n"
        "1. CAD 프로그램(AutoCAD, LibreCAD 등)에서 DXF로 내보내기 후 선택\n"
        "2. ODA File Converter 설치:\n"
        "   https://www.opendesign.com/guestfiles/oda_file_converter\n"
        "3. sudo apt-get install libredwg-utils"
    )


def _try_oda_convert(dwg_path: str, output_dir: str) -> str | None:
    oda_candidates = [
        "ODAFileConverter",
        "/usr/bin/ODAFileConverter",
        os.path.expanduser("~/ODAFileConverter/ODAFileConverter"),
        "/opt/ODAFileConverter/ODAFileConverter",
    ]
    for oda in oda_candidates:
        if not _command_exists(oda):
            continue
        input_dir = str(Path(dwg_path).parent)
        stem = Path(dwg_path).stem
        result_path = Path(output_dir) / f"{stem}.dxf"
        try:
            subprocess.run(
                [oda, input_dir, output_dir, "ACAD2018", "DXF", "0", "1"],
                capture_output=True, timeout=180, check=True
            )
            if result_path.exists():
                return str(result_path)
            # 대소문자 변형 탐색
            for candidate in Path(output_dir).glob("*.dxf"):
                return str(candidate)
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass
    return None


def _try_libdwg_convert(dwg_path: str, output_dir: str) -> str | None:
    # 소스 빌드 경로 우선, 없으면 PATH에서 검색
    candidates = [_LIBREDWG_DWG2DXF] if Path(_LIBREDWG_DWG2DXF).exists() else []
    if _command_exists("dwg2dxf"):
        candidates.append("dwg2dxf")
    if not candidates:
        return None

    env = os.environ.copy()
    if Path(_LIBREDWG_LIBS).exists():
        existing = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = f"{_LIBREDWG_LIBS}:{existing}" if existing else _LIBREDWG_LIBS

    out_path = Path(output_dir) / "converted.dxf"
    for cmd in candidates:
        try:
            subprocess.run(
                [cmd, "-o", str(out_path), dwg_path],
                capture_output=True, timeout=300, check=True, env=env,
            )
            if out_path.exists():
                return str(out_path)
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass
    return None


def _command_exists(cmd: str) -> bool:
    return subprocess.run(["which", cmd], capture_output=True).returncode == 0


def get_all_layers(doc: Drawing) -> list[str]:
    # 레이어 테이블 + 엔티티에서 직접 사용된 레이어 통합
    layer_set: set[str] = {layer.dxf.name for layer in doc.layers}
    msp = doc.modelspace()
    for entity in msp:
        try:
            layer_set.add(entity.dxf.layer)
        except Exception:
            pass
    return sorted(layer_set)
