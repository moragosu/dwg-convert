"""
2D 미리보기 캔버스.
- 일반 모드: 휠 줌 / 드래그 패닝
- 영역 선택 모드: 드래그로 직사각형 영역 선택 → 콜백 호출
"""
import tkinter as tk
from typing import Callable, Optional

from shapely.geometry import Polygon

from core.layout_analyzer import ZONE_COLORS

MAX_BG_ENTITIES = 8000


class PreviewCanvas(tk.Canvas):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg="#F0F0F0", **kwargs)
        self._polygon: Optional[Polygon] = None
        self._zones: list[tuple[str, Polygon]] = []
        self._doc = None
        self._scale = 1.0
        self._offset_x = 0.0
        self._offset_y = 0.0

        # 선택 모드 상태
        self._selection_mode = False
        self._sel_callback: Optional[Callable] = None
        self._drag_start: Optional[tuple[int, int]] = None
        self._sel_rect_id: Optional[int] = None

        self.bind("<MouseWheel>",     self._on_zoom)
        self.bind("<Button-4>",       self._on_zoom)
        self.bind("<Button-5>",       self._on_zoom)
        self.bind("<ButtonPress-1>",  self._on_press)
        self.bind("<B1-Motion>",      self._on_drag)
        self.bind("<ButtonRelease-1>",self._on_release)
        self.bind("<Configure>",      self._on_resize)

    # ── 공개 API ────────────────────────────────────────────────────────

    def draw(
        self,
        polygon: Optional[Polygon] = None,
        zones: Optional[list[tuple[str, Polygon]]] = None,
        doc=None,
    ) -> None:
        self._polygon = polygon
        self._zones = zones or []
        self._doc = doc
        self._fit()
        self._redraw()

    def clear(self) -> None:
        self._polygon = None
        self._zones = []
        self._doc = None
        self.delete("all")
        cx = self.winfo_width() // 2 or 400
        cy = self.winfo_height() // 2 or 200
        self.create_text(cx, cy,
                         text="파일을 선택하면 미리보기가 표시됩니다.",
                         fill="#AAAAAA", font=("Arial", 11))

    def enable_selection_mode(self, callback: Callable[[float, float, float, float], None]) -> None:
        """영역 선택 모드 활성화. 드래그 완료 시 callback(x0,y0,x1,y1) 호출 (DXF 좌표)."""
        self._selection_mode = True
        self._sel_callback = callback
        self.configure(cursor="crosshair")

    def disable_selection_mode(self) -> None:
        self._selection_mode = False
        self._sel_callback = None
        self.configure(cursor="")
        if self._sel_rect_id:
            self.delete(self._sel_rect_id)
            self._sel_rect_id = None

    # ── 이벤트 ─────────────────────────────────────────────────────────

    def _on_press(self, event: tk.Event) -> None:
        self._drag_start = (event.x, event.y)

    def _on_drag(self, event: tk.Event) -> None:
        if self._drag_start is None:
            return
        if self._selection_mode:
            # 고무줄 직사각형
            if self._sel_rect_id:
                self.delete(self._sel_rect_id)
            x0, y0 = self._drag_start
            self._sel_rect_id = self.create_rectangle(
                x0, y0, event.x, event.y,
                outline="#FF4444", width=2, dash=(6, 3), tags="selrect")
        else:
            # 패닝
            dx = event.x - self._drag_start[0]
            dy = event.y - self._drag_start[1]
            self._offset_x += dx
            self._offset_y += dy
            self._drag_start = (event.x, event.y)
            self._redraw()

    def _on_release(self, event: tk.Event) -> None:
        if self._drag_start is None:
            return
        if self._selection_mode and self._sel_callback:
            cx0, cy0 = self._drag_start
            cx1, cy1 = event.x, event.y
            if abs(cx1 - cx0) > 5 and abs(cy1 - cy0) > 5:
                # 캔버스 픽셀 → DXF 좌표
                dx0, dy0 = self._c2d(cx0, cy0)
                dx1, dy1 = self._c2d(cx1, cy1)
                x0, x1 = min(dx0, dx1), max(dx0, dx1)
                y0, y1 = min(dy0, dy1), max(dy0, dy1)
                self._sel_callback(x0, y0, x1, y1)
        self._drag_start = None

    def _on_zoom(self, event: tk.Event) -> None:
        if self._selection_mode:
            return
        factor = 1.15 if (getattr(event, "num", 0) == 4 or getattr(event, "delta", 0) > 0) else (1 / 1.15)
        mx, my = event.x, event.y
        self._offset_x = mx + (self._offset_x - mx) * factor
        self._offset_y = my + (self._offset_y - my) * factor
        self._scale *= factor
        self._redraw()

    def _on_resize(self, event: tk.Event) -> None:
        if self._zones or self._polygon is not None:
            self._fit()
            self._redraw()
        else:
            self.clear()

    # ── 렌더링 ─────────────────────────────────────────────────────────

    def _fit(self) -> None:
        bounds = self._all_bounds()
        if bounds is None:
            return
        minx, miny, maxx, maxy = bounds
        w = self.winfo_width() or 800
        h = self.winfo_height() or 380
        margin = 40
        dw = max(maxx - minx, 1e-6)
        dh = max(maxy - miny, 1e-6)
        self._scale = min((w - margin * 2) / dw, (h - margin * 2) / dh)
        cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
        self._offset_x = w / 2 - cx * self._scale
        self._offset_y = h / 2 + cy * self._scale

    def _all_bounds(self) -> Optional[tuple[float, float, float, float]]:
        polys: list[Polygon] = []
        if self._polygon:
            polys.append(self._polygon)
        polys.extend(p for _, p in self._zones)
        if not polys and self._doc:
            return self._doc_bounds()
        if not polys:
            return None
        xs = [b for p in polys for b in (p.bounds[0], p.bounds[2])]
        ys = [b for p in polys for b in (p.bounds[1], p.bounds[3])]
        return min(xs), min(ys), max(xs), max(ys)

    def _doc_bounds(self):
        """폴리곤 없을 때 도큐먼트 엔티티에서 bounds 추정."""
        msp = self._doc.modelspace()
        xs, ys = [], []
        for e in msp:
            try:
                if e.dxftype() == "LINE":
                    xs += [e.dxf.start.x, e.dxf.end.x]
                    ys += [e.dxf.start.y, e.dxf.end.y]
                    if len(xs) > 2000:
                        break
            except Exception:
                pass
        if not xs:
            return None
        return min(xs), min(ys), max(xs), max(ys)

    def _redraw(self) -> None:
        self.delete("all")
        if self._doc is not None:
            self._draw_background()
        if self._zones:
            for i, (name, poly) in enumerate(self._zones):
                color = ZONE_COLORS[i % len(ZONE_COLORS)]
                self._draw_zone(poly, color, name)
        elif self._polygon is not None:
            self._draw_outline(self._polygon, "#0066FF")
        # 선택 사각형 복원
        if self._sel_rect_id:
            self.tag_raise("selrect")

    def _draw_background(self) -> None:
        msp = self._doc.modelspace()
        count = 0
        for entity in msp:
            if count >= MAX_BG_ENTITIES:
                break
            try:
                if entity.dxftype() == "LINE":
                    x1, y1 = self._d2c(entity.dxf.start.x, entity.dxf.start.y)
                    x2, y2 = self._d2c(entity.dxf.end.x, entity.dxf.end.y)
                    self.create_line(x1, y1, x2, y2, fill="#BBBBBB", width=1, tags="bg")
                    count += 1
                elif entity.dxftype() == "LWPOLYLINE":
                    pts = list(entity.get_points())
                    if len(pts) >= 2:
                        flat = [c for p in pts for c in self._d2c(p[0], p[1])]
                        self.create_line(flat, fill="#BBBBBB", width=1, tags="bg")
                        count += 1
            except Exception:
                pass

    def _draw_outline(self, poly: Polygon, color: str) -> None:
        coords = list(poly.exterior.coords)
        pts = [c for x, y in coords for c in self._d2c(x, y)]
        if len(pts) < 4:
            return
        self.create_polygon(pts, outline=color, fill="", width=2, tags="wall")

    def _draw_zone(self, poly: Polygon, color: str, name: str) -> None:
        coords = list(poly.exterior.coords)
        pts = [c for x, y in coords for c in self._d2c(x, y)]
        if len(pts) < 4:
            return
        self.create_polygon(pts, outline=color, fill=color,
                             stipple="gray25", width=2, tags="zone")
        self.create_polygon(pts, outline=color, fill="", width=2, tags="zone")
        # 중심 레이블
        cx_w = sum(x for x, y in coords) / len(coords)
        cy_w = sum(y for x, y in coords) / len(coords)
        lx, ly = self._d2c(cx_w, cy_w)
        self.create_text(lx, ly, text=name, fill=color,
                         font=("Arial", 9, "bold"), tags="zone_label")

    # ── 좌표 변환 ───────────────────────────────────────────────────────

    def _d2c(self, x: float, y: float) -> tuple[float, float]:
        """DXF → 캔버스 픽셀."""
        return (x * self._scale + self._offset_x,
                -y * self._scale + self._offset_y)

    def _c2d(self, cx: float, cy: float) -> tuple[float, float]:
        """캔버스 픽셀 → DXF 좌표."""
        return ((cx - self._offset_x) / self._scale,
                -(cy - self._offset_y) / self._scale)
