"""
Benchmark UI (CPU benchmark + GPU stress) with live per-core CPU bars.

Drop this file at: src/app/ui/pages/benchmark.py
"""

import os
import threading
import time
import subprocess
import multiprocessing as mp
from pathlib import Path
from typing import Optional, List, Dict, Any

import customtkinter as ctk

from src.app.services.report_service import ReportService
try:
    from src.app.core.logger import logger
except Exception:
    import logging
    logger = logging.getLogger("benchmark_ui")

# Theme fallback
try:
    from ..theme import COLORS, FONTS, SPACING
except Exception:
    try:
        from src.app.ui.theme import COLORS, FONTS, SPACING
    except Exception:
        COLORS = {
            "bg": "#071018", "panel": "#0d1114", "muted": "#9aa",
            "text": "#e6eef6", "border": "#17202a", "accent": "#ff6a00"
        }
        FONTS = {"h1": ("Segoe UI", 22), "h2": ("Segoe UI", 18), "h3": ("Segoe UI", 14), "body": ("Segoe UI", 12)}
        SPACING = {"page": 14, "pad": 16}

PAD = SPACING.get("page", 14)

# optional
try:
    import psutil
except Exception:
    psutil = None

# Safe canvas mixin
class SafeCanvasMixin:
    @staticmethod
    def _safe_bg(master):
        try:
            candidate = master.cget("fg_color")
        except Exception:
            candidate = None
        if not candidate or str(candidate).lower() == "transparent":
            return COLORS.get("bg", "#071018")
        return candidate

class CircularGauge(SafeCanvasMixin, ctk.CTkCanvas):
    def __init__(self, master, size=90, label="", **kwargs):
        bg = self._safe_bg(master)
        super().__init__(master, width=size, height=size, bg=bg, highlightthickness=0, **kwargs)
        self.size = size
        self.label = label
        self._value = 0.0
        self._draw_base()

    def _draw_base(self):
        s = self.size
        try:
            self.delete("all")
        except Exception:
            pass
        self.create_oval(6, 6, s - 6, s - 6, outline="#1a2b2f", width=8)
        self.create_text(s / 2, s / 2, text=f"{int(self._value)}%", fill=COLORS["accent"],
                         font=(FONTS["h3"][0], 12, "bold"), tags=("val",))
        self.create_text(s / 2, s - 12, text=self.label, fill=COLORS["muted"], font=(FONTS["body"][0], 9))

    def set_value(self, v: Optional[float]):
        if v is None:
            v = 0.0
        try:
            v = max(0.0, min(100.0, float(v)))
        except Exception:
            v = 0.0
        self._value = v
        self._draw_base()
        s = self.size
        angle = int(v / 100.0 * 359)
        self.create_arc(6, 6, s - 6, s - 6, start=90, extent=-angle, style="arc", outline=COLORS["accent"], width=8)
        try:
            self.itemconfigure("val", text=f"{int(v)}%")
        except Exception:
            pass

class Sparkline(SafeCanvasMixin, ctk.CTkCanvas):
    def __init__(self, master, width=360, height=56, **kwargs):
        bg = self._safe_bg(master)
        super().__init__(master, width=width, height=height, bg=bg, highlightthickness=0, **kwargs)
        self.w, self.h = width, height
        self.values: List[float] = []

    def push(self, v: Optional[float], maxlen: int = 120):
        if v is None:
            v = self.values[-1] if self.values else 0.0
        try:
            self.values.append(float(v))
        except Exception:
            self.values.append(0.0)
        if len(self.values) > maxlen:
            self.values = self.values[-maxlen:]
        self._draw()

    def _draw(self):
        try:
            self.delete("all")
        except Exception:
            pass
        if not self.values:
            return
        vals = self.values
        w, h = self.w, self.h
        vmin, vmax = min(vals), max(vals)
        if vmax == vmin:
            vmax = vmin + 1.0
        pts = []
        for i, v in enumerate(vals):
            x = int(i / max(1, len(vals) - 1) * (w - 6) + 3)
            y = int(h - ((v - vmin) / (vmax - vmin) * (h - 8)) - 2)
            pts.append((x, y))
        for i in range(2):
            y = 4 + i * (h - 8) / 2
            self.create_line(0, y, w, y, fill="#0f2224")
        for i in range(1, len(pts)):
            x1, y1 = pts[i - 1]; x2, y2 = pts[i]
            self.create_line(x1, y1, x2, y2, fill=COLORS["accent"], width=2)
        last = vals[-1]
        self.create_text(w - 6, 8, anchor="ne", text=f"{last:.0f}", fill=COLORS["muted"], font=(FONTS["body"][0], 9))

def make_sample_queue():
    try:
        ctx = mp.get_context("spawn")
        return ctx.Queue()
    except Exception:
        return mp.Queue()

def tile_style(frame, text, subtitle, icon):
    card = ctk.CTkFrame(frame, fg_color=COLORS["panel"], corner_radius=12)
    lbl_icon = ctk.CTkLabel(card, text=icon, font=(FONTS["h2"][0], 28), text_color=COLORS["accent"])
    lbl_icon.pack(anchor="w", padx=12, pady=(12, 0))
    ctk.CTkLabel(card, text=text, font=(FONTS["h3"][0], 14, "bold"), text_color=COLORS["text"]).pack(anchor="w", padx=12)
    ctk.CTkLabel(card, text=subtitle, font=(FONTS["body"][0], 11),
                 text_color=COLORS["muted"], wraplength=340, justify="left").pack(anchor="w", padx=12, pady=(6, 12))
    return card

# ---------- Base page ----------
class BaseBenchmarkPage(ctk.CTkFrame):
    def __init__(self, master, on_back):
        super().__init__(master, fg_color=COLORS["bg"])
        self.on_back = on_back
        self.rs = ReportService()
        self.sample_queue: Optional[mp.Queue] = None
        self._stream_thread: Optional[threading.Thread] = None
        self._stream_running = False
        self._local_probe_thread: Optional[threading.Thread] = None
        self._local_probe_running = False
        self._hist_cpu: List[float] = []
        self._hist_gpu: List[float] = []
        self._hist_temp: List[float] = []
        self.low_overlay = None

    def _start_stream(self):
        try:
            self.sample_queue = make_sample_queue()
        except Exception:
            self.sample_queue = None
        self._stream_running = True
        self._stream_thread = threading.Thread(target=self._stream_poller, daemon=True)
        self._stream_thread.start()
        self._start_local_probe()

    def _stop_stream(self):
        self._stream_running = False
        self.sample_queue = None
        self._stop_local_probe()

    def _stream_poller(self):
        q = self.sample_queue
        while self._stream_running and q:
            try:
                s = q.get(timeout=0.6)
                if isinstance(s, dict):
                    try:
                        self.after(10, lambda s=s: self._on_sample_received(s))
                    except Exception:
                        break
            except Exception:
                continue

    def _start_local_probe(self):
        if self._local_probe_running:
            return
        self._local_probe_running = True
        self._local_probe_thread = threading.Thread(target=self._local_probe_loop, daemon=True)
        self._local_probe_thread.start()

    def _stop_local_probe(self):
        self._local_probe_running = False

    def _local_probe_loop(self):
        """
        Collects per-core and overall CPU % if psutil available,
        and GPU telemetry via nvidia-smi. Posts samples to _on_local_probe.
        """
        while self._local_probe_running:
            try:
                cpu_u = None; cpu_t = None; cpu_percents = None
                gpu_u = None; gpu_t = None; src = None
                if psutil:
                    try:
                        # non-blocking percents: psutil requires an interval for accurate percore;
                        # call with small interval=0.1 for per-core sampling but keep it short to avoid blocking UI.
                        cpu_percents = psutil.cpu_percent(interval=0.1, percpu=True)
                        if cpu_percents:
                            cpu_u = sum(cpu_percents) / len(cpu_percents)
                    except Exception:
                        try:
                            cpu_u = psutil.cpu_percent(interval=None)
                        except Exception:
                            cpu_u = None
                        cpu_percents = None
                    try:
                        temps = psutil.sensors_temperatures()
                        found = []
                        if temps:
                            for _, vals in temps.items():
                                for v in vals:
                                    cur = getattr(v, "current", None)
                                    if cur is not None:
                                        found.append(cur)
                        if found:
                            cpu_t = float(sum(found) / len(found))
                    except Exception:
                        cpu_t = None
                # GPU probe via nvidia-smi (best-effort)
                try:
                    p = subprocess.run(
                        ["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"],
                        capture_output=True, text=True, timeout=0.6
                    )
                    if p.returncode == 0 and p.stdout:
                        s = p.stdout.strip().splitlines()[0].strip()
                        parts = [x.strip() for x in s.split(",")]
                        if parts and parts[0]:
                            try:
                                gpu_u = float(parts[0])
                            except Exception:
                                gpu_u = None
                        if len(parts) > 1 and parts[1]:
                            try:
                                gpu_t = float(parts[1])
                            except Exception:
                                gpu_t = None
                        src = "nvidia-smi"
                except Exception:
                    gpu_u, gpu_t, src = None, None, None

                sample = {
                    "t": round(time.time(), 2),
                    "cpu_util_percent": cpu_u,
                    "cpu_temp_c": cpu_t,
                    "cpu_percents": cpu_percents,   # may be None
                    "gpu_util": gpu_u,
                    "gpu_temp_c": gpu_t,
                    "gpu_source": src
                }
                try:
                    self.after(20, lambda s=sample: self._on_local_probe(s))
                except Exception:
                    break
            except Exception:
                logger.debug("local_probe exception", exc_info=True)
            # keep loop at a reasonable cadence
            time.sleep(0.4)

    def _on_local_probe(self, sample: Dict[str, Any]):
        cpu = sample.get("cpu_util_percent"); gpu = sample.get("gpu_util"); temp_cpu = sample.get("cpu_temp_c"); temp_gpu = sample.get("gpu_temp_c")
        if cpu is not None:
            self._hist_cpu.append(cpu)
            if len(self._hist_cpu) > 300: self._hist_cpu.pop(0)
        if gpu is not None:
            self._hist_gpu.append(gpu)
            if len(self._hist_gpu) > 300: self._hist_gpu.pop(0)
        temp = temp_cpu if temp_cpu is not None else temp_gpu
        if temp is not None:
            self._hist_temp.append(temp)
            if len(self._hist_temp) > 300: self._hist_temp.pop(0)
        try:
            self._on_sample_received(sample)
        except Exception:
            logger.debug("page _on_sample_received failed", exc_info=True)

    def _on_sample_received(self, s: Dict[str, Any]):
        pass

    def _show_low_util_overlay(self, txt: str):
        if self.low_overlay:
            try:
                self.low_overlay.configure(text=txt)
            except Exception:
                pass
            return
        self.low_overlay = ctk.CTkLabel(self, text=txt, fg_color="#221212", text_color="#ffce9e",
                                        corner_radius=8, font=(FONTS["h2"][0], 12, "bold"))
        self.low_overlay.place(relx=0.5, rely=0.02, anchor="n")

    def _hide_low_util_overlay(self):
        if self.low_overlay:
            try:
                self.low_overlay.destroy()
            except Exception:
                pass
            self.low_overlay = None

# ---------- CPU Page (with per-core bars) ----------
class CPUPage(BaseBenchmarkPage):
    def __init__(self, master, on_back):
        super().__init__(master, on_back)
        self._running = False
        self.core_bars: List[ctk.CTkProgressBar] = []
        self.core_labels: List[ctk.CTkLabel] = []
        self.num_cores = psutil.cpu_count(logical=True) if psutil else mp.cpu_count()
        self._build()

    def _build(self):
        header = ctk.CTkFrame(self, fg_color="transparent"); header.pack(fill="x", padx=PAD, pady=(12, 10))
        ctk.CTkButton(header, text="← Back", width=90, fg_color="transparent", command=self.on_back).pack(side="left")
        ctk.CTkLabel(header, text="CPU Benchmark", font=(FONTS["h2"][0], 18, "bold"), text_color=COLORS["text"]).pack(side="left", padx=(10, 0))

        card = ctk.CTkFrame(self, fg_color=COLORS["panel"], corner_radius=12); card.pack(fill="x", padx=PAD, pady=(8, 8))
        ctk.CTkLabel(card, text="CPU benchmark — live CPU usage and CPU temperature.", text_color=COLORS["muted"]).pack(anchor="w", padx=12, pady=(12, 6))

        ctrl = ctk.CTkFrame(card, fg_color="transparent"); ctrl.pack(fill="x", padx=12, pady=(8, 8))
        self.btn10 = ctk.CTkButton(ctrl, text="Run 10s", width=140, command=lambda: self.start(10)); self.btn10.pack(side="left")
        self.btn20 = ctk.CTkButton(ctrl, text="Run 20s", width=140, command=lambda: self.start(20)); self.btn20.pack(side="left", padx=(8, 0))
        self.cancel_btn = ctk.CTkButton(ctrl, text="Cancel", width=120, fg_color="#ff7a45", command=self.cancel, state="disabled"); self.cancel_btn.pack(side="left", padx=(12,0))

        vis = ctk.CTkFrame(card, fg_color="transparent"); vis.pack(fill="both", padx=12, pady=(6,12))
        left_col = ctk.CTkFrame(vis, fg_color="transparent"); left_col.pack(side="left", padx=(0,12), fill="y")
        ctk.CTkLabel(left_col, text="CPU Usage", font=(FONTS["body"][0], 11, "bold"), text_color=COLORS["muted"]).pack()
        self.cpu_gauge = CircularGauge(left_col, size=120, label="CPU"); self.cpu_gauge.pack(pady=(6,0))

        right_col = ctk.CTkFrame(vis, fg_color="transparent"); right_col.pack(side="left", fill="both", expand=True)
        ctk.CTkLabel(right_col, text="CPU Temperature (°C) & Per-core (%)", font=(FONTS["body"][0], 11, "bold"), text_color=COLORS["muted"]).pack(anchor="w")
        self.cpu_temp_spark = Sparkline(right_col, width=420, height=64); self.cpu_temp_spark.pack(anchor="w", pady=(6,0))

        # Per-core bars area
        self.cores_frame = ctk.CTkFrame(right_col, fg_color="transparent")
        self.cores_frame.pack(fill="both", expand=False, pady=(8,6))
        # Build per-core bars (two columns if many)
        cols = 2 if self.num_cores > 8 else 1
        for c in range(self.num_cores):
            col = c % cols
            row = c // cols
            # container for this core
            core_row = ctk.CTkFrame(self.cores_frame, fg_color="transparent")
            core_row.grid(row=row, column=col, sticky="we", padx=(0,8), pady=4)
            # label + percent
            lbl = ctk.CTkLabel(core_row, text=f"Core {c}", width=100, anchor="w", text_color=COLORS["muted"])
            lbl.pack(side="left")
            pb = ctk.CTkProgressBar(core_row, width=220)
            pb.set(0.0)
            pb.pack(side="left", padx=(8,8))
            pct_lbl = ctk.CTkLabel(core_row, text="0%", width=48, anchor="e", text_color=COLORS["muted"])
            pct_lbl.pack(side="left")
            self.core_bars.append(pb)
            self.core_labels.append(pct_lbl)

        lbls = ctk.CTkFrame(right_col, fg_color="transparent"); lbls.pack(fill="x", pady=(6,0))
        self.cpu_temp_min = ctk.CTkLabel(lbls, text="Min: --°C", text_color=COLORS["muted"], anchor="w"); self.cpu_temp_min.pack(side="left")
        self.cpu_temp_cur = ctk.CTkLabel(lbls, text="Current: --°C", text_color=COLORS["muted"]); self.cpu_temp_cur.pack(side="left", padx=12)
        self.cpu_temp_max = ctk.CTkLabel(lbls, text="Max: --°C", text_color=COLORS["muted"], anchor="e"); self.cpu_temp_max.pack(side="right")

        self.progress = ctk.CTkProgressBar(card, width=640); self.progress.set(0.0); self.progress.pack(anchor="w", padx=12, pady=(8,6))
        self.status = ctk.CTkLabel(card, text="Ready", text_color=COLORS["muted"]); self.status.pack(anchor="w", padx=12, pady=(6,12))
        self.result = ctk.CTkLabel(self, text="No report yet", text_color=COLORS["muted"], wraplength=920, justify="left"); self.result.pack(anchor="w", padx=PAD, pady=(6,0))

    def start(self, seconds: int):
        if self._running: return
        self._running = True
        self._hist_cpu.clear(); self._hist_temp.clear()
        self._start_stream()
        self.progress.set(0.01)
        self.status.configure(text=f"Running {seconds}s (single pass)...")
        self.btn10.configure(state="disabled"); self.btn20.configure(state="disabled"); self.cancel_btn.configure(state="normal")

        def worker():
            try:
                meta = self.rs.run_and_save(seconds=seconds, iterations=1, sample_queue=self.sample_queue)
                try:
                    self.after(50, lambda m=meta: self._on_done(m))
                except Exception:
                    pass
            except Exception as e:
                logger.exception("CPU run failed: %s", e)
                msg = str(e)
                try:
                    self.after(50, lambda m=msg: self._on_error(m))
                except Exception:
                    pass
            finally:
                self._running = False
                try:
                    self._stop_stream()
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()
        self.after(150, self._tick)

    def cancel(self):
        if not self._running: return
        try:
            self.rs.stop_benchmark()
            self.status.configure(text="Cancelling...")
        except Exception:
            pass

    def _tick(self):
        if not self._running: return
        try:
            self.progress.set(min(0.95, self.progress.get() + 0.01))
            self.after(300, self._tick)
        except Exception:
            pass

    def _on_done(self, meta):
        mean = meta.get("mean_ops_per_sec") or 0.0
        stdev = meta.get("stdev_ops_per_sec") or 0.0
        try:
            self.status.configure(text=f"Done — mean {mean:.3f} ops/sec")
            self.result.configure(text=f"Mean: {mean:.3f} | Stddev: {stdev:.3f}\nCSV: {meta.get('csv')}")
            self.progress.set(1.0)
            self.btn10.configure(state="normal"); self.btn20.configure(state="normal"); self.cancel_btn.configure(state="disabled")
            self._hide_low_util_overlay()
        except Exception:
            pass

    def _on_error(self, msg):
        try:
            self.status.configure(text=f"Error — {msg}")
            self.progress.set(0.0)
            self.btn10.configure(state="normal"); self.btn20.configure(state="normal"); self.cancel_btn.configure(state="disabled")
            self._hide_low_util_overlay()
        except Exception:
            pass

    def _on_sample_received(self, s: Dict[str, Any]):
        # update overall gauge & temp as before
        cpu_u = s.get("cpu_util_percent")
        cpu_t = s.get("cpu_temp_c")
        cpu_percents = s.get("cpu_percents")  # list or None
        # overall gauge
        if cpu_u is not None:
            try:
                self.cpu_gauge.set_value(cpu_u)
            except Exception:
                pass
            self._hist_cpu.append(cpu_u)
            if len(self._hist_cpu) > 300: self._hist_cpu.pop(0)
        # temp spark
        if cpu_t is not None:
            try:
                self.cpu_temp_spark.push(cpu_t)
            except Exception:
                pass
            self._hist_temp.append(cpu_t)
            if len(self._hist_temp) > 300: self._hist_temp.pop(0)
        # per-core bars update
        if cpu_percents and isinstance(cpu_percents, (list, tuple)):
            # may be more/less cores than UI expects; clamp accordingly
            for i in range(min(len(cpu_percents), len(self.core_bars))):
                val = 0.0
                try:
                    val = float(cpu_percents[i])
                except Exception:
                    val = 0.0
                try:
                    self.core_bars[i].set(val / 100.0)
                    self.core_labels[i].configure(text=f"{int(val)}%")
                except Exception:
                    pass
        # update temp labels
        if self._hist_temp:
            try:
                mn = min(self._hist_temp); mx = max(self._hist_temp); cur = self._hist_temp[-1]
                self.cpu_temp_min.configure(text=f"Min: {mn:.1f}°C"); self.cpu_temp_max.configure(text=f"Max: {mx:.1f}°C"); self.cpu_temp_cur.configure(text=f"Current: {cur:.1f}°C")
            except Exception:
                pass
        else:
            try:
                self.cpu_temp_min.configure(text="Min: --°C"); self.cpu_temp_max.configure(text="Max: --°C"); self.cpu_temp_cur.configure(text="Current: --°C")
            except Exception:
                pass
        # low util overlay check
        if len(self._hist_cpu) >= 6:
            recent = sum(self._hist_cpu[-6:]) / 6.0
            if recent < 60.0:
                self._show_low_util_overlay("⚠️ CPU load low (<60%). Results may be inaccurate.")
            else:
                self._hide_low_util_overlay()

# ---------- GPU Stress Page ----------
class GPUStressPage(BaseBenchmarkPage):
    def __init__(self, master, on_back):
        super().__init__(master, on_back)
        self._running = False
        self._local_test_running = False
        self._build()

    def _build(self):
        header = ctk.CTkFrame(self, fg_color="transparent"); header.pack(fill="x", padx=PAD, pady=(12, 10))
        ctk.CTkButton(header, text="← Back", width=90, fg_color="transparent", command=self.on_back).pack(side="left")
        ctk.CTkLabel(header, text="GPU Stress Test", font=(FONTS["h2"][0], 18, "bold"), text_color=COLORS["text"]).pack(side="left", padx=(10, 0))

        card = ctk.CTkFrame(self, fg_color=COLORS["panel"], corner_radius=12); card.pack(fill="x", padx=PAD, pady=(8,8))
        ctk.CTkLabel(card, text="Run a GPU stress using built-in renderer or external tool. Use Local Test first.", text_color=COLORS["muted"]).pack(anchor="w", padx=12, pady=(12,6))

        ctrl = ctk.CTkFrame(card, fg_color="transparent"); ctrl.pack(fill="x", padx=12, pady=(8,8))
        self.btn_local_test = ctk.CTkButton(ctrl, text="Local GPU Render Test (10s)", width=220, command=self._start_local_test); self.btn_local_test.pack(side="left")
        self.btn_force = ctk.CTkButton(ctrl, text="Force dGPU / Download video", width=220, fg_color="#2a7a5f", command=self._force_dgpu_and_download); self.btn_force.pack(side="left", padx=(8,0))
        self.btn_run = ctk.CTkButton(ctrl, text="Run 30s Stress", width=160, command=lambda: self._start(30)); self.btn_run.pack(side="left", padx=(8,0))
        self.cancel_btn = ctk.CTkButton(ctrl, text="Cancel", width=120, fg_color="#ff7a45", command=self._cancel, state="disabled"); self.cancel_btn.pack(side="left", padx=(12,0))
        self.btn_diag = ctk.CTkButton(ctrl, text="GPU Diagnostics", width=140, command=self._run_diagnostics); self.btn_diag.pack(side="left", padx=(12,0))

        vis = ctk.CTkFrame(card, fg_color="transparent"); vis.pack(fill="x", padx=12, pady=(6,12))
        left_col = ctk.CTkFrame(vis, fg_color="transparent"); left_col.pack(side="left", padx=(0,12))
        ctk.CTkLabel(left_col, text="GPU Usage", font=(FONTS["body"][0], 11, "bold"), text_color=COLORS["muted"]).pack()
        self.gpu_gauge = CircularGauge(left_col, size=120, label="GPU"); self.gpu_gauge.pack(pady=(6,0))

        right_col = ctk.CTkFrame(vis, fg_color="transparent"); right_col.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(right_col, text="GPU Temperature (°C)", font=(FONTS["body"][0], 11, "bold"), text_color=COLORS["muted"]).pack(anchor="w")
        self.gpu_temp_spark = Sparkline(right_col, width=420, height=64); self.gpu_temp_spark.pack(anchor="w", pady=(6,0))
        lbls = ctk.CTkFrame(right_col, fg_color="transparent"); lbls.pack(fill="x", pady=(6,0))
        self.gpu_temp_min = ctk.CTkLabel(lbls, text="Min: --°C", text_color=COLORS["muted"]); self.gpu_temp_min.pack(side="left")
        self.gpu_temp_cur = ctk.CTkLabel(lbls, text="Current: --°C", text_color=COLORS["muted"]); self.gpu_temp_cur.pack(side="left", padx=12)
        self.gpu_temp_max = ctk.CTkLabel(lbls, text="Max: --°C", text_color=COLORS["muted"]); self.gpu_temp_max.pack(side="right")

        self.progress = ctk.CTkProgressBar(card, width=640); self.progress.set(0.0); self.progress.pack(anchor="w", padx=12, pady=(8,6))
        self.status = ctk.CTkLabel(card, text="Ready", text_color=COLORS["muted"]); self.status.pack(anchor="w", padx=12, pady=(6,12))
        self.result = ctk.CTkLabel(self, text="No stress run yet", text_color=COLORS["muted"], wraplength=920, justify="left"); self.result.pack(anchor="w", padx=PAD, pady=(6,0))

    def _run_diagnostics(self):
        try:
            import pynvml as _p; _p.nvmlInit(); _p.nvmlShutdown(); nvml_ok = True
        except Exception:
            nvml_ok = False
        try:
            p = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=1.0)
            smi_ok = (p.returncode == 0)
        except Exception:
            smi_ok = False
        msg = f"Diagnostics — pynvml_installed={nvml_ok}, nvidia-smi_present={smi_ok}."
        self.status.configure(text=msg)
        if not (nvml_ok or smi_ok):
            self.result.configure(text="No GPU telemetry found. Ensure drivers and nvidia-smi are installed and on PATH.")
        else:
            self.result.configure(text="GPU telemetry present. Use Local Test and/or Force dGPU if on Optimus.")

    def _force_dgpu_and_download(self):
        self.btn_force.configure(state="disabled"); self.status.configure(text="Attempting to download sample video and detect Optimus...")
        def task():
            try:
                optimus = False
                try:
                    optimus = self.rs.detect_optimus()
                except Exception:
                    optimus = False
                video_path = None
                try:
                    video_path = self.rs.ensure_sample_video()
                except Exception:
                    video_path = None
                info = []
                if optimus:
                    info.append("Optimus-like configuration detected (Intel+iGPU + NVIDIA discrete).")
                if video_path:
                    info.append(f"Sample video available: {video_path}")
                if not video_path:
                    info.append("Could not download sample video. External player stress fallback may be limited.")
                text = "\n".join(info)
                try:
                    self.after(50, lambda t=text: self._on_force_done(t))
                except Exception:
                    pass
            finally:
                try:
                    self.after(200, lambda: self.btn_force.configure(state="normal"))
                except Exception:
                    pass
        threading.Thread(target=task, daemon=True).start()

    def _on_force_done(self, text):
        try:
            self.status.configure(text="Force/detect finished")
            self.result.configure(text=text + "\n\nIf you're on Windows Optimus, set 'SystemOptimizer' or the player to use 'High performance NVIDIA' in Settings → Graphics, or right-click the exe -> Run with graphics processor -> NVIDIA GPU.")
        except Exception:
            pass

    def _start_local_test(self):
        if self._local_test_running: return
        self._start_stream()
        self._local_test_running = True
        self.btn_local_test.configure(state="disabled")
        self.status.configure(text="Starting local GPU render test (10s)...")
        self.progress.set(0.01)

        def local_worker():
            try:
                meta = self.rs.run_gpu_stress_internal(seconds=10, sample_queue=self.sample_queue)
                try:
                    self.after(50, lambda m=meta: self._on_local_test_done(m))
                except Exception:
                    pass
            except Exception as e:
                logger.exception("Local GPU render test failed: %s", e)
                msg = str(e)
                try:
                    self.after(50, lambda m=msg: self._on_local_test_error(m))
                except Exception:
                    pass
            finally:
                self._local_test_running = False
                try:
                    self.after(500, lambda: self._stop_stream())
                except Exception:
                    pass

        threading.Thread(target=local_worker, daemon=True).start()
        self.after(150, self._tick)

    def _start(self, seconds: int):
        if self._running: return
        self._running = True
        self._hist_gpu.clear(); self._hist_temp.clear()
        self._start_stream()
        self.progress.set(0.01); self.status.configure(text=f"Running stress for {seconds}s...")
        self.btn_run.configure(state="disabled"); self.btn_local_test.configure(state="disabled"); self.cancel_btn.configure(state="normal")

        def worker():
            try:
                meta = self.rs.run_gpu_stress_internal(seconds=seconds, sample_queue=self.sample_queue)
                try:
                    self.after(50, lambda m=meta: self._on_done(m))
                except Exception:
                    pass
            except Exception as e:
                logger.exception("Stress failed: %s", e)
                msg = str(e)
                try:
                    self.after(50, lambda m=msg: self._on_error(m))
                except Exception:
                    pass
            finally:
                self._running = False
                try:
                    self._stop_stream()
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()
        self.after(150, self._tick)

    def _cancel(self):
        if not self._running and not self._local_test_running: return
        try:
            self.rs.stop_benchmark()
            self.status.configure(text="Cancelling...")
        except Exception:
            pass

    def _tick(self):
        if not self._running and not self._local_test_running: return
        try:
            self.progress.set(min(0.95, self.progress.get() + 0.01))
            self.after(300, self._tick)
        except Exception:
            pass

    def _on_local_test_done(self, meta):
        s = meta.get("samples", [])
        gpu_utils = [x.get("gpu_util") for x in s if isinstance(x.get("gpu_util"), (int, float))]
        avg = (sum(gpu_utils) / len(gpu_utils)) if gpu_utils else None
        try:
            self.status.configure(text=f"Local render test finished — avg GPU util: {avg}% (method={meta.get('summary',{}).get('method')})")
            self.result.configure(text=f"Local render test: avg GPU util: {avg}\nCSV: {meta.get('csv')}\nMethod: {meta.get('summary',{}).get('method')}")
            self.btn_local_test.configure(state="normal")
            self.progress.set(1.0)
            self._hide_low_util_overlay()
        except Exception:
            pass

    def _on_local_test_error(self, msg):
        try:
            self.status.configure(text=f"Local render test failed — {msg}")
            self.btn_local_test.configure(state="normal")
            self.progress.set(0.0)
            self._hide_low_util_overlay()
        except Exception:
            pass

    def _on_done(self, meta):
        samples = meta.get("samples", [])
        gpu_utils = [s.get("gpu_util") for s in samples if isinstance(s.get("gpu_util"), (int, float))]
        avg = (sum(gpu_utils) / len(gpu_utils)) if gpu_utils else None
        try:
            self.status.configure(text=f"Done — avg GPU util: {avg}% (method={meta.get('summary',{}).get('method')})")
            self.result.configure(text=f"Avg GPU util: {avg}\nCSV: {meta.get('csv')}\nMethod: {meta.get('summary',{}).get('method')}")
            self.progress.set(1.0)
            self.btn_run.configure(state="normal"); self.btn_local_test.configure(state="normal"); self.cancel_btn.configure(state="disabled")
            self._hide_low_util_overlay()
        except Exception:
            pass

    def _on_error(self, msg):
        try:
            self.status.configure(text=f"Error — {msg}")
            self.progress.set(0.0)
            self.btn_run.configure(state="normal"); self.btn_local_test.configure(state="normal"); self.cancel_btn.configure(state="disabled")
            self._hide_low_util_overlay()
        except Exception:
            pass

    def _on_sample_received(self, s: Dict[str, Any]):
        gpu_u = s.get("gpu_util")
        gpu_t = s.get("gpu_temp_c")
        src = s.get("gpu_source", None) or s.get("source", None)
        if gpu_u is not None:
            try:
                self.gpu_gauge.set_value(gpu_u)
            except Exception:
                pass
            self._hist_gpu.append(gpu_u)
            if len(self._hist_gpu) > 300: self._hist_gpu.pop(0)
        if gpu_t is not None:
            try:
                self.gpu_temp_spark.push(gpu_t)
            except Exception:
                pass
            self._hist_temp.append(gpu_t)
            if len(self._hist_temp) > 300: self._hist_temp.pop(0)
        if self._hist_temp:
            try:
                mn = min(self._hist_temp); mx = max(self._hist_temp); cur = self._hist_temp[-1]
                self.gpu_temp_min.configure(text=f"Min: {mn:.1f}°C"); self.gpu_temp_max.configure(text=f"Max: {mx:.1f}°C"); self.gpu_temp_cur.configure(text=f"Current: {cur:.1f}°C")
            except Exception:
                pass
        if src:
            try:
                self.status.configure(text=f"Live telemetry source: {src}")
            except Exception:
                pass
        if len(self._hist_gpu) >= 6:
            recent = sum(self._hist_gpu[-6:]) / 6.0
            if recent < 30.0:
                self._show_low_util_overlay("⚠️ GPU load low (<30%). Results may be inaccurate.")
            else:
                self._hide_low_util_overlay()

# ---------- Top-level ----------
class BenchmarkPage(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color=COLORS["bg"])
        self._build()

    def _build(self):
        header = ctk.CTkFrame(self, fg_color="transparent"); header.pack(fill="x", padx=PAD, pady=(16,8))
        ctk.CTkLabel(header, text="Benchmark", font=(FONTS["h1"][0], 22, "bold"), text_color=COLORS["text"]).pack(anchor="w")
        ctk.CTkLabel(header, text="Pick a benchmark", text_color=COLORS["muted"]).pack(anchor="w")

        sel = ctk.CTkFrame(self, fg_color="transparent"); sel.pack(fill="x", padx=PAD, pady=(8,12)); sel.grid_columnconfigure((0,1), weight=1)
        cpu_tile = tile_style(sel, "CPU Benchmark", "Accurate multi-core CPU benchmark.", "🧭"); cpu_tile.grid(row=0, column=0, padx=(0,12))
        stress_tile = tile_style(sel, "GPU Stress Test", "Run a stress renderer or external tool.", "🔥"); stress_tile.grid(row=0, column=1)

        cpu_tile.bind("<Button-1>", lambda e: self._show_page("cpu"))
        for w in cpu_tile.winfo_children(): w.bind("<Button-1>", lambda e: self._show_page("cpu"))
        stress_tile.bind("<Button-1>", lambda e: self._show_page("stress"))
        for w in stress_tile.winfo_children(): w.bind("<Button-1>", lambda e: self._show_page("stress"))

        self.container = ctk.CTkFrame(self, fg_color="transparent"); self.container.pack(fill="both", expand=True, padx=PAD, pady=(0,PAD))
        self.current_page = None

    def _clear_container(self):
        for w in self.container.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass
        self.current_page = None

    def _show_page(self, key: str):
        self._clear_container()
        if key == "cpu":
            page = CPUPage(self.container, on_back=self._back_to_main)
        elif key == "stress":
            page = GPUStressPage(self.container, on_back=self._back_to_main)
        else:
            return
        page.pack(fill="both", expand=True)
        self.current_page = page

    def _back_to_main(self):
        self._clear_container()

    def on_show(self): pass
