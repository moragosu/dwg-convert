"""
메인 GUI 애플리케이션.
파일 선택 → 캔버스에서 영역 드래그 선택 → 존 목록 → 3D 미리보기 → STEP 변환
"""
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from core.layout_analyzer import ZONE_COLORS
from gui.canvas_preview import PreviewCanvas


class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DWG → 3D STEP 변환기")
        self.geometry("980x780")
        self.resizable(True, True)
        self.minsize(760, 600)

        self._doc = None
        self._zones: list = []           # [(name, Polygon), ...]
        self._zone_vars: list[tk.BooleanVar] = []
        self._selecting = False

        self._build_ui()
        self.after(100, self._canvas.clear)

    # ------------------------------------------------------------------ #
    # UI 구성
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        pad = {"padding": (8, 4)}

        # 1. 파일 선택
        file_frm = ttk.LabelFrame(self, text="1. 파일 선택 (DWG / DXF)", **pad)
        file_frm.pack(fill="x", padx=10, pady=(8, 2))

        self._file_var = tk.StringVar()
        ttk.Entry(file_frm, textvariable=self._file_var,
                  state="readonly", width=60).pack(side="left", padx=(4, 6))
        ttk.Button(file_frm, text="파일 선택...",
                   command=self._on_file_select).pack(side="left")

        # 2. 캔버스 (영역 선택 포함)
        canvas_frm = ttk.LabelFrame(
            self,
            text="2. 도면 미리보기  —  일반: 휠 줌 / 드래그 패닝   |   선택 모드: 드래그로 라인 영역 지정",
            **pad)
        canvas_frm.pack(fill="both", expand=True, padx=10, pady=2)

        self._canvas = PreviewCanvas(canvas_frm)
        self._canvas.pack(fill="both", expand=True, padx=4, pady=4)

        # 캔버스 하단 버튼 바
        canvas_btn = ttk.Frame(canvas_frm)
        canvas_btn.pack(fill="x", padx=4, pady=(0, 4))

        self._sel_btn = ttk.Button(
            canvas_btn, text="영역 선택 모드 ON",
            command=self._toggle_selection)
        self._sel_btn.pack(side="left", padx=(0, 6))

        ttk.Button(canvas_btn, text="전체 보기",
                   command=self._on_fit).pack(side="left", padx=(0, 6))

        self._canvas_status = tk.StringVar(value="파일을 로드하면 도면이 표시됩니다.")
        ttk.Label(canvas_btn, textvariable=self._canvas_status,
                  foreground="#555555").pack(side="left", padx=8)

        # 3. 존 목록
        zone_frm = ttk.LabelFrame(self, text="3. 라인 존 목록", **pad)
        zone_frm.pack(fill="x", padx=10, pady=2)

        zone_ctrl = ttk.Frame(zone_frm)
        zone_ctrl.pack(fill="x", pady=(0, 4))

        ttk.Button(zone_ctrl, text="전체 선택",
                   command=self._select_all_zones).pack(side="left", padx=(4, 2))
        ttk.Button(zone_ctrl, text="전체 해제",
                   command=self._deselect_all_zones).pack(side="left", padx=(0, 6))
        ttk.Button(zone_ctrl, text="선택 존 삭제",
                   command=self._delete_selected_zones).pack(side="left", padx=(0, 6))
        ttk.Button(zone_ctrl, text="전체 초기화",
                   command=self._clear_zones).pack(side="left")

        self._zone_list_frm = ttk.Frame(zone_frm)
        self._zone_list_frm.pack(fill="x", padx=4, pady=2)

        self._zone_count_var = tk.StringVar(value="존 없음")
        ttk.Label(zone_frm, textvariable=self._zone_count_var,
                  foreground="#555555").pack(anchor="w", padx=4, pady=(0, 2))

        # 4. 변환 설정
        conv_frm = ttk.LabelFrame(self, text="4. 변환 설정", **pad)
        conv_frm.pack(fill="x", padx=10, pady=2)

        ttk.Label(conv_frm, text="압출 높이:").pack(side="left", padx=(4, 2))
        self._height_var = tk.StringVar(value="3000")
        ttk.Entry(conv_frm, textvariable=self._height_var, width=8).pack(side="left")

        self._unit_var = tk.StringVar(value="mm")
        for u in ("mm", "m", "inch"):
            ttk.Radiobutton(conv_frm, text=u, variable=self._unit_var,
                            value=u).pack(side="left", padx=3)

        ttk.Separator(conv_frm, orient="vertical").pack(
            side="left", fill="y", padx=8, pady=2)
        ttk.Label(conv_frm, text="출력 파일:").pack(side="left", padx=(0, 2))
        self._output_var = tk.StringVar()
        ttk.Entry(conv_frm, textvariable=self._output_var,
                  width=36).pack(side="left")
        ttk.Button(conv_frm, text="...",
                   command=self._on_output_select, width=3).pack(side="left", padx=2)

        # 5. 실행
        bottom = ttk.Frame(self, padding=4)
        bottom.pack(fill="x", padx=10, pady=(2, 8))

        self._preview3d_btn = ttk.Button(
            bottom, text="3D 미리보기", command=self._on_preview_3d)
        self._preview3d_btn.pack(side="left", padx=(0, 6))

        self._convert_btn = ttk.Button(
            bottom, text="STEP 변환", command=self._on_convert)
        self._convert_btn.pack(side="left", padx=(0, 10))

        self._progress = ttk.Progressbar(bottom, length=240, mode="determinate")
        self._progress.pack(side="left")

        self._status_var = tk.StringVar(value="파일을 선택하세요.")
        ttk.Label(bottom, textvariable=self._status_var,
                  foreground="#444444").pack(side="left", padx=10)

    # ------------------------------------------------------------------ #
    # 파일 로드
    # ------------------------------------------------------------------ #

    def _on_file_select(self) -> None:
        path = filedialog.askopenfilename(
            title="DWG 또는 DXF 파일 선택",
            filetypes=[
                ("CAD 파일", "*.dwg *.dxf *.DWG *.DXF"),
                ("DWG", "*.dwg *.DWG"),
                ("DXF", "*.dxf *.DXF"),
                ("모든 파일", "*.*"),
            ],
        )
        if not path:
            return
        self._file_var.set(path)
        self._output_var.set(str(Path(path).with_suffix(".stp")))
        self._set_ui(0, "파일 로딩 중...")
        threading.Thread(target=self._load_file, args=(path,), daemon=True).start()

    def _load_file(self, path: str) -> None:
        try:
            from core.dwg_reader import read_dwg_or_dxf
            self._set_ui(20, "파일 읽는 중... (대용량은 수분 소요)")
            doc = read_dwg_or_dxf(path)
            self._doc = doc

            self._set_ui(70, "도면 미리보기 준비 중...")
            # 배경 샘플링을 여기서 미리 수행 (UI 스레드 블로킹 방지)
            self._canvas._doc = doc
            self._canvas._cached_bounds = None
            self._canvas._bg_segments = []
            self._canvas._sample_background(doc)

            self.after(0, lambda: self._canvas.draw(doc=doc))
            self._set_ui(100, "로드 완료.  '영역 선택 모드'로 라인 영역을 드래그하세요.")
            self.after(0, lambda: self._canvas_status.set(
                "영역 선택 모드를 켜고 라인 영역을 드래그하세요."))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("파일 오류", str(e)))
            self._set_ui(0, f"오류: {e}")

    # ------------------------------------------------------------------ #
    # 영역 선택 모드
    # ------------------------------------------------------------------ #

    def _toggle_selection(self) -> None:
        if self._doc is None:
            messagebox.showwarning("알림", "먼저 파일을 선택하세요.")
            return
        if self._selecting:
            self._canvas.disable_selection_mode()
            self._selecting = False
            self._sel_btn.configure(text="영역 선택 모드 ON")
            self._canvas_status.set("선택 모드 해제.")
        else:
            self._canvas.enable_selection_mode(self._on_region_selected)
            self._selecting = True
            self._sel_btn.configure(text="영역 선택 모드 OFF")
            self._canvas_status.set("라인 영역을 드래그하세요. 완료 후 버튼으로 해제.")

    def _on_region_selected(self, x0: float, y0: float, x1: float, y1: float) -> None:
        """캔버스 드래그 완료 → 영역 내 hull 계산 (별도 스레드)."""
        w_m = abs(x1 - x0) / 1000
        h_m = abs(y1 - y0) / 1000
        self._canvas_status.set(f"선택 영역: {w_m:.1f}m × {h_m:.1f}m  |  hull 계산 중...")
        self._set_ui(20, "hull 계산 중...")
        threading.Thread(
            target=self._compute_hull,
            args=(x0, y0, x1, y1), daemon=True).start()

    def _compute_hull(self, x0, y0, x1, y1) -> None:
        try:
            from core.layout_analyzer import extract_hull_in_region
            poly = extract_hull_in_region(self._doc, x0, y0, x1, y1)
            if poly is None:
                self.after(0, lambda: messagebox.showwarning(
                    "알림", "선택 영역 내에 충분한 엔티티가 없습니다.\n더 넓게 드래그하세요."))
                self._set_ui(0, "엔티티 부족.")
                self.after(0, lambda: self._canvas_status.set("엔티티 부족. 다시 드래그하세요."))
                return

            name = f"LINE_{len(self._zones) + 1}"
            self._zones.append((name, poly))
            self.after(0, lambda: self._refresh_zone_display())
            b = poly.bounds
            info = (f"{name} 추가 — hull {len(list(poly.exterior.coords))-1}꼭짓점  "
                    f"{(b[2]-b[0])/1000:.1f}m × {(b[3]-b[1])/1000:.1f}m")
            self._set_ui(100, info)
            self.after(0, lambda: self._canvas_status.set(
                "존 추가 완료. 계속 드래그하거나 모드를 해제하세요."))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("오류", str(e)))
            self._set_ui(0, f"오류: {e}")

    # ------------------------------------------------------------------ #
    # 존 목록 관리
    # ------------------------------------------------------------------ #

    def _refresh_zone_display(self) -> None:
        """존 목록 UI 및 캔버스 갱신."""
        # 체크박스 목록 재구성
        for w in self._zone_list_frm.winfo_children():
            w.destroy()
        self._zone_vars = []

        for i, (name, poly) in enumerate(self._zones):
            color = ZONE_COLORS[i % len(ZONE_COLORS)]
            b = poly.bounds
            w_m = (b[2] - b[0]) / 1000
            h_m = (b[3] - b[1]) / 1000

            var = tk.BooleanVar(value=True)
            self._zone_vars.append(var)

            row = ttk.Frame(self._zone_list_frm)
            row.pack(fill="x", pady=1)

            tk.Label(row, bg=color, width=2, relief="flat").pack(side="left", padx=(2, 4))
            ttk.Checkbutton(
                row,
                text=f"{name}   {w_m:.1f}m × {h_m:.1f}m   ({poly.area/1e6:.0f}m²)",
                variable=var,
            ).pack(side="left")

        count = len(self._zones)
        self._zone_count_var.set(f"총 {count}개 존" if count else "존 없음")

        # 캔버스에 존 폴리곤 표시
        self._canvas.draw(zones=self._zones, doc=self._doc)

    def _select_all_zones(self):
        for v in self._zone_vars:
            v.set(True)

    def _deselect_all_zones(self):
        for v in self._zone_vars:
            v.set(False)

    def _delete_selected_zones(self):
        keep = [(z, v) for z, v in zip(self._zones, self._zone_vars) if not v.get()]
        self._zones = [z for z, _ in keep]
        # 이름 재정렬
        self._zones = [(f"LINE_{i+1}", poly) for i, (_, poly) in enumerate(self._zones)]
        self._refresh_zone_display()

    def _clear_zones(self):
        self._zones = []
        self._zone_vars = []
        for w in self._zone_list_frm.winfo_children():
            w.destroy()
        self._zone_count_var.set("존 없음")
        self._canvas.draw(doc=self._doc)

    # ------------------------------------------------------------------ #
    # 전체 보기
    # ------------------------------------------------------------------ #

    def _on_fit(self) -> None:
        if self._doc or self._zones:
            self._canvas.draw(zones=self._zones or None, doc=self._doc)

    # ------------------------------------------------------------------ #
    # 3D 미리보기 / 변환
    # ------------------------------------------------------------------ #

    def _get_height_mm(self) -> Optional[float]:
        try:
            h = float(self._height_var.get())
        except ValueError:
            messagebox.showerror("입력 오류", "높이는 숫자여야 합니다.")
            return None
        unit = self._unit_var.get()
        if unit == "m":
            h *= 1000.0
        elif unit == "inch":
            h *= 25.4
        return h

    def _on_preview_3d(self) -> None:
        selected = [z for z, v in zip(self._zones, self._zone_vars) if v.get()]
        if not selected:
            messagebox.showwarning("알림", "미리볼 존을 하나 이상 선택하세요.")
            return
        h = self._get_height_mm()
        if h is None:
            return
        from gui.preview_3d import show_3d_preview
        show_3d_preview(selected, h, parent=self)

    def _on_convert(self) -> None:
        selected = [z for z, v in zip(self._zones, self._zone_vars) if v.get()]
        if not selected:
            messagebox.showwarning("알림", "변환할 존을 하나 이상 선택하세요.")
            return
        h = self._get_height_mm()
        if h is None:
            return
        output = self._output_var.get().strip()
        if not output:
            messagebox.showwarning("알림", "출력 파일 경로를 설정하세요.")
            return
        self._convert_btn.configure(state="disabled")
        threading.Thread(target=self._run_convert,
                         args=(selected, h, output), daemon=True).start()

    def _run_convert(self, zones, height_mm, output) -> None:
        try:
            from exporters.step_writer import export_step_multi
            self._set_ui(20, f"STEP 생성 중... ({len(zones)}개 존)")
            export_step_multi(zones, height_mm, output)
            self._set_ui(100, f"완료 → {Path(output).name}")
            self.after(0, lambda: messagebox.showinfo(
                "변환 완료",
                f"STEP 파일 저장:\n{output}\n({len(zones)}개 존)"))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("변환 오류", str(e)))
            self._set_ui(0, f"실패: {e}")
        finally:
            self.after(0, lambda: self._convert_btn.configure(state="normal"))

    def _on_output_select(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".stp",
            filetypes=[("STEP 파일", "*.stp *.step"), ("모든 파일", "*.*")])
        if path:
            self._output_var.set(path)

    # ------------------------------------------------------------------ #

    def _set_ui(self, progress: int, message: str) -> None:
        self.after(0, lambda: self._progress.configure(value=progress))
        self.after(0, lambda: self._status_var.set(message))
