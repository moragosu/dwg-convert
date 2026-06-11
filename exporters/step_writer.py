"""
순수 Python STEP AP214 작성기.
shapely Polygon을 압출한 솔리드를 STEP 파일로 내보냅니다.

엔티티 번호: 2-pass 방식
  Pass 1: 심볼 이름 → 번호 매핑 생성
  Pass 2: @@sym@@ 플레이스홀더를 #번호로 치환 후 파일 작성
"""
import datetime
import re
from pathlib import Path

from shapely.geometry import Polygon


def export_step(
    polygon: Polygon,
    height_mm: float,
    output_path: str,
    name: str = "BUILDING",
) -> None:
    coords = _clean_coords(polygon)
    if len(coords) < 3:
        raise ValueError("폴리곤 좌표가 너무 적습니다 (최소 3개 필요).")
    if height_mm <= 0:
        raise ValueError("높이는 0보다 커야 합니다.")

    records = _build_records(coords, height_mm, name)
    _write_file(records, output_path, name)


def export_step_multi(
    zones: list[tuple[str, Polygon]],
    height_mm: float,
    output_path: str,
) -> None:
    """여러 존을 각각 EXTRUDED_AREA_SOLID로 하나의 STEP 파일에 내보냄."""
    if not zones:
        raise ValueError("내보낼 존이 없습니다.")
    if height_mm <= 0:
        raise ValueError("높이는 0보다 커야 합니다.")

    all_records: list[tuple[str, str]] = []
    for zone_name, polygon in zones:
        coords = _clean_coords(polygon)
        if len(coords) < 3:
            continue
        # 존마다 심볼 prefix를 붙여 이름 충돌 방지
        prefix = re.sub(r"[^A-Za-z0-9]", "_", zone_name).lower()
        all_records.extend(_build_records(coords, height_mm, zone_name, prefix=prefix))

    if not all_records:
        raise ValueError("유효한 폴리곤이 없습니다.")

    title = f"{len(zones)}개 존"
    _write_file(all_records, output_path, title)


def _clean_coords(polygon: Polygon) -> list[tuple[float, float]]:
    coords = list(polygon.exterior.coords)
    if len(coords) > 1 and coords[0] == coords[-1]:
        coords = coords[:-1]
    return coords


def _ref(sym: str) -> str:
    """심볼 참조 플레이스홀더."""
    return f"@@{sym}@@"


def _build_records(
    coords: list[tuple[float, float]],
    height_mm: float,
    name: str,
    prefix: str = "",
) -> list[tuple[str, str]]:
    """
    (심볼, STEP_엔티티_문자열) 목록 반환.
    엔티티 문자열 내 @@sym@@ 참조는 Pass 2에서 #번호로 치환.
    prefix: 다중 존 시 심볼 충돌 방지용 접두사.
    """
    p = f"{prefix}_" if prefix else ""
    R: list[tuple[str, str]] = []

    def add(sym: str, body: str) -> None:
        R.append((p + sym, body))

    def r(sym: str) -> str:
        return _ref(p + sym)

    # --- 단위 및 글로벌 컨텍스트 ---
    add("mm_unit",    "(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.))")
    add("angle_unit", "(NAMED_UNIT(*) PLANE_ANGLE_UNIT() SI_UNIT($,.RADIAN.))")
    add("solid_unit", "(NAMED_UNIT(*) SI_UNIT($,.STERADIAN.) SOLID_ANGLE_UNIT())")
    add("uncert",
        f"UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-007),"
        f"{r('mm_unit')},"
        f"'distance_accuracy_value','confusion accuracy')")
    add("geom_ctx",
        f"( GEOMETRIC_REPRESENTATION_CONTEXT(3)"
        f" GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT(({r('uncert')}))"
        f" GLOBAL_UNIT_ASSIGNED_CONTEXT(({r('mm_unit')},{r('angle_unit')},{r('solid_unit')}))"
        f" REPRESENTATION_CONTEXT('Context #1','3D Context with UNIT and UNCERTAINTY') )")

    # --- 애플리케이션 컨텍스트 ---
    add("app_ctx",
        "APPLICATION_CONTEXT('core data for automotive mechanical design processes')")

    # --- 좌표계 ---
    add("origin",    "CARTESIAN_POINT('',(0.0,0.0,0.0))")
    add("x_dir",     "DIRECTION('',(1.0,0.0,0.0))")
    add("z_dir",     "DIRECTION('',(0.0,0.0,1.0))")
    add("placement",
        f"AXIS2_PLACEMENT_3D('',{r('origin')},{r('z_dir')},{r('x_dir')})")

    # --- 2D 폴리라인 ---
    for i, (x, y) in enumerate(coords):
        add(f"pt_{i}", f"CARTESIAN_POINT('',({x:.6f},{y:.6f}))")

    pt_refs = ",".join(r(f"pt_{i}") for i in range(len(coords)))
    add("polyline", f"POLYLINE('',({pt_refs}))")

    # --- 프로파일 및 솔리드 ---
    add("profile",
        f"ARBITRARY_CLOSED_PROFILE_DEF(.AREA.,'{name}_PROFILE',{r('polyline')})")
    add("solid",
        f"EXTRUDED_AREA_SOLID('{name}',{r('placement')},{r('profile')},{height_mm:.6f})")

    # --- SHAPE_REPRESENTATION ---
    add("shape_rep",
        f"SHAPE_REPRESENTATION('{name}',({r('solid')}),{r('geom_ctx')})")

    # --- PRODUCT 계층 ---
    add("prod_ctx",
        f"PRODUCT_CONTEXT('',{r('app_ctx')},'mechanical')")
    add("prod",
        f"PRODUCT('{name}','{name}','',('{name}'))")
    add("prod_def_form",
        f"PRODUCT_DEFINITION_FORMATION('','',{r('prod')})")
    add("prod_def_ctx",
        f"PRODUCT_DEFINITION_CONTEXT('part definition',{r('app_ctx')},'design')")
    add("prod_def",
        f"PRODUCT_DEFINITION('{name}','',{r('prod_def_form')},{r('prod_def_ctx')})")
    add("shape_def_rep",
        f"SHAPE_DEFINITION_REPRESENTATION({r('prod_def')},{r('shape_rep')})")

    return R


def _write_file(
    records: list[tuple[str, str]],
    output_path: str,
    name: str,
) -> None:
    # Pass 1: 심볼 → 번호 (1부터)
    sym_to_num: dict[str, int] = {}
    for i, (sym, _) in enumerate(records, start=1):
        sym_to_num[sym] = i

    # Pass 2: @@sym@@ → #번호 치환
    def replace_refs(body: str) -> str:
        def sub(m: re.Match) -> str:
            sym = m.group(1)
            num = sym_to_num.get(sym)
            return f"#{num}" if num is not None else m.group(0)
        return re.sub(r"@@(\w+)@@", sub, body)

    now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    out_name = Path(output_path).name

    lines: list[str] = [
        "ISO-10303-21;",
        "HEADER;",
        f"FILE_DESCRIPTION(('DWG to STEP - {name}'),'2;1');",
        f"FILE_NAME('{out_name}','{now}',(''),(''),'dwg-convert','','');",
        "FILE_SCHEMA(('AUTOMOTIVE_DESIGN'));",
        "ENDSEC;",
        "DATA;",
    ]

    for sym, body in records:
        num = sym_to_num[sym]
        lines.append(f"#{num}={replace_refs(body)};")

    lines += ["ENDSEC;", "END-ISO-10303-21;"]

    with open(output_path, "w", encoding="ascii", errors="replace") as f:
        f.write("\n".join(lines) + "\n")
