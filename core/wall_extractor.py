"""
외벽 폴리라인 추출 모듈.
4단계 폭포수: 레이어 패턴 → 최대 닫힌 LWPOLYLINE → LINE 병합 → 실패
"""
import re
from typing import Optional

from ezdxf.document import Drawing
from shapely.geometry import Polygon, MultiLineString
from shapely.ops import unary_union, polygonize

WALL_LAYER_PATTERNS = [
    r"^A[-_]?WALL$",
    r"^A[-_]?G[-_]?WALL",
    r"WALL[-_]?EXT",
    r"OUTER[-_]?WALL",
    r"BLDG[-_]?WALL",
    r"EXTERIOR",
    r"외벽",
    r"외부",
    r"건물외곽",
    r"^WALL$",
]


def extract_outer_wall(
    doc: Drawing,
    preferred_layers: list[str] | None = None,
) -> tuple[Polygon, list[str]]:
    """
    외벽 폴리곤 추출.
    반환: (shapely Polygon, 사용된 레이어 목록)
    """
    msp = doc.modelspace()
    # 레이어 테이블 + 엔티티에서 사용된 레이어 모두 포함
    layer_set: set[str] = {layer.dxf.name for layer in doc.layers}
    for entity in msp:
        try:
            layer_set.add(entity.dxf.layer)
        except Exception:
            pass
    all_layer_names = sorted(layer_set)

    # 1단계: 지정 레이어 또는 패턴 매칭
    wall_layers = preferred_layers or _detect_wall_layers(all_layer_names)
    if wall_layers:
        polygon = _extract_from_layers(msp, wall_layers)
        if _is_valid_polygon(polygon):
            return polygon, wall_layers

    # 2단계: 모든 레이어에서 최대 닫힌 LWPOLYLINE
    polygon = _largest_closed_polyline(msp)
    if _is_valid_polygon(polygon):
        return polygon, []

    # 3단계: LINE 세그먼트 병합
    polygon = _outline_from_lines(msp)
    if _is_valid_polygon(polygon):
        return polygon, []

    raise RuntimeError(
        "외벽을 자동으로 찾을 수 없습니다.\n"
        "레이어 목록에서 외벽 레이어를 직접 선택하세요."
    )


def _detect_wall_layers(all_layers: list[str]) -> list[str]:
    matched = []
    for layer in all_layers:
        for pattern in WALL_LAYER_PATTERNS:
            if re.search(pattern, layer, re.IGNORECASE):
                matched.append(layer)
                break
    return matched


def _extract_from_layers(msp, layer_names: list[str]) -> Optional[Polygon]:
    layer_set = set(layer_names)
    candidates: list[Polygon] = []

    for entity in msp:
        if entity.dxf.layer not in layer_set:
            continue
        poly = _entity_to_polygon(entity)
        if poly and poly.is_valid and poly.area > 1.0:
            candidates.append(poly)

    if not candidates:
        return None
    return max(candidates, key=lambda p: p.area)


def _largest_closed_polyline(msp) -> Optional[Polygon]:
    candidates: list[Polygon] = []
    for entity in msp:
        if entity.dxftype() not in ("LWPOLYLINE", "POLYLINE"):
            continue
        if entity.dxftype() == "LWPOLYLINE" and not entity.closed:
            continue
        poly = _entity_to_polygon(entity)
        if poly and poly.is_valid and poly.area > 1.0:
            candidates.append(poly)

    if not candidates:
        return None
    return max(candidates, key=lambda p: p.area)


def _outline_from_lines(msp) -> Optional[Polygon]:
    segments = []
    for entity in msp:
        if entity.dxftype() == "LINE":
            try:
                start = (entity.dxf.start.x, entity.dxf.start.y)
                end = (entity.dxf.end.x, entity.dxf.end.y)
                if start != end:
                    segments.append((start, end))
            except Exception:
                pass

    if not segments:
        return None

    try:
        multi_line = MultiLineString(segments)
        merged = unary_union(multi_line)
        polygons = list(polygonize(merged))
        if not polygons:
            return None
        return max(polygons, key=lambda p: p.area)
    except Exception:
        return None


def _entity_to_polygon(entity) -> Optional[Polygon]:
    try:
        if entity.dxftype() == "LWPOLYLINE":
            points = [(p[0], p[1]) for p in entity.get_points()]
            if len(points) >= 3:
                return Polygon(points)
        elif entity.dxftype() == "POLYLINE":
            points = [(v.dxf.location.x, v.dxf.location.y)
                      for v in entity.vertices]
            if len(points) >= 3:
                return Polygon(points)
    except Exception:
        pass
    return None


def _is_valid_polygon(poly: Optional[Polygon]) -> bool:
    return poly is not None and poly.is_valid and poly.area > 1.0
