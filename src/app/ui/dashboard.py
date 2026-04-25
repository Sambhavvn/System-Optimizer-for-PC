import customtkinter as ctk
from datetime import datetime
from collections import deque

from ..core.collector import get_collector
from ..core.power_manager import PowerManager
from ..services.ai_optimizer_service import AiOptimizerService
from ..services.game_mode_service import GameModeService
from ..services.cleaner_service import CleanerService
from ..services.report_service import ReportService
from ..system_tray import TrayController

from .widgets.gauge import Gauge
from .widgets.line_chart import LineChart
from .widgets.pill_toggle import PillToggle


class Dashboard(ctk.CTkFrame):
    """Main UI screen for system monitoring + tools."""

    def __init__(self, master):
        super().__init__(master, fg_color="#0D1117")
        self.pack(fill="both", expand=True)

        self.master = master
        # Components
        self.collector = get_collector()
        self.power_manager = PowerManager()
        self.ai_optimizer = AiOptimizerService()
        self.game_mode = GameModeService()
        self.cleaner = CleanerService()
        self.reporter = ReportService()
        self.tray = TrayController(self.master)

        # History buffers
        self.cpu_history = deque([0] * 50, maxlen=50)
        self.gpu_history = deque([0] * 50, maxlen=50)
        self.gpu_temp_history = deque([0] * 50, maxlen=50)

        self._build_ui()
        self.update_data()

    def _build_ui(self):
        # Top navigation bar (static labels)
        nav = ctk.CTkFrame(self, fg_color="#0D1117")
        nav.pack(fill="x", pady=15, padx=15)
        for name in ["Hardware Monitor", "AI Optimize", "Gaming Centre", "Benchmark", "Settings"]:
            ctk.CTkLabel(nav, text=name, font=("Segoe UI", 12, "bold"), text_color="#C9D1D9").pack(side="left", padx=10)

        # Minimize to Tray button
        ctk.CTkButton(nav, text="Minimize to Tray", command=self.minimize_to_tray).pack(side="right", padx=10)

        # Main Frame
        main = ctk.CTkFrame(self, fg_color="#0D1117")
        main.pack(fill="both", expand=True, padx=20, pady=10)

        # Left: CPU & GPU display
        left = ctk.CTkFrame(main, fg_color="#0D1117")
        left.pack(side="left", fill="both", expand=True)

        self.gpu_gauge = Gauge(left); self.gpu_gauge.pack(pady=10)
        self.gpu_line = LineChart(left); self.gpu_line.pack(pady=5)

        self.cpu_gauge = Gauge(left); self.cpu_gauge.pack(pady=10)
        self.cpu_line = LineChart(left); self.cpu_line.pack(pady=5)

        # GPU Temp graph
        self.gpu_temp_line = LineChart(left); self.gpu_temp_line.pack(pady=5)

        # Right Panel: Info & Controls
        right = ctk.CTkFrame(main, fg_color="#0D1117", width=420)
        right.pack(side="right", fill="y")

        # GPU/CPU Info
        info = ctk.CTkFrame(right, fg_color="#161B22", corner_radius=12)
        info.pack(fill="x", pady=10)

        self.gpu_name_label = ctk.CTkLabel(info, text="GPU: --", anchor="w", text_color="#C9D1D9")
        self.gpu_name_label.pack(fill="x", padx=12, pady=6)

        self.gpu_clock_label = ctk.CTkLabel(info, text="Clock: --", anchor="w", text_color="#8B949E")
        self.gpu_clock_label.pack(fill="x", padx=12)

        self.gpu_temp_label = ctk.CTkLabel(info, text="Temp: --", anchor="w", text_color="#8B949E")
        self.gpu_temp_label.pack(fill="x", padx=12, pady=(0, 8))

        self.cpu_name_label = ctk.CTkLabel(info, text="CPU: --", anchor="w", text_color="#C9D1D9")
        self.cpu_name_label.pack(fill="x", padx=12, pady=6)

        self.cpu_temp_label = ctk.CTkLabel(info, text="CPU Temp: --", anchor="w", text_color="#8B949E")
        self.cpu_temp_label.pack(fill="x", padx=12, pady=(0, 10))

        # AI Mode Toggle & Manual Buttons
        controls = ctk.CTkFrame(right, fg_color="#0D1117")
        controls.pack(fill="x", pady=6)

        self.ai_toggle = PillToggle(controls, text="AI Optimize", command=self.use_ai_mode)
        self.ai_toggle.pack(anchor="w", padx=10, pady=5)

        ctk.CTkButton(controls, text="Performance", command=lambda: self.set_mode("High performance")).pack(side="left", padx=5)
        ctk.CTkButton(controls, text="Balanced", command=lambda: self.set_mode("Balanced")).pack(side="left", padx=5)
        ctk.CTkButton(controls, text="Power Saver", command=lambda: self.set_mode("Power saver")).pack(side="left", padx=5)

        # Gaming Centre actions
        gaming = ctk.CTkFrame(right, fg_color="#161B22", corner_radius=12)
        gaming.pack(fill="x", pady=10)
        ctk.CTkLabel(gaming, text="Gaming Centre", text_color="#C9D1D9", font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=12, pady=(10, 0))
        self.lbl_game_status = ctk.CTkLabel(gaming, text="Status: Off", anchor="w", text_color="#8B949E")
        self.lbl_game_status.pack(fill="x", padx=12, pady=4)
        btnrow = ctk.CTkFrame(gaming, fg_color="#161B22")
        btnrow.pack(fill="x", padx=10, pady=8)
        ctk.CTkButton(btnrow, text="Enable Game Mode", command=self.enable_game_mode).pack(side="left", padx=6)
        ctk.CTkButton(btnrow, text="Disable Game Mode", command=self.disable_game_mode).pack(side="left", padx=6)

        # Cleaner
        cleaner = ctk.CTkFrame(right, fg_color="#161B22", corner_radius=12)
        cleaner.pack(fill="x", pady=10)
        ctk.CTkLabel(cleaner, text="PC Cleaner", text_color="#C9D1D9", font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=12, pady=(10, 0))
        self.lbl_clean_status = ctk.CTkLabel(cleaner, text="Ready", anchor="w", text_color="#8B949E")
        self.lbl_clean_status.pack(fill="x", padx=12, pady=4)
        ctk.CTkButton(cleaner, text="Free Temp Files", command=self.clean_temp).pack(padx=12, pady=8)

        # Benchmark
        bench = ctk.CTkFrame(right, fg_color="#161B22", corner_radius=12)
        bench.pack(fill="x", pady=10)
        ctk.CTkLabel(bench, text="Benchmark", text_color="#C9D1D9", font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=12, pady=(10, 0))
        self.lbl_bench_status = ctk.CTkLabel(bench, text="No report yet", anchor="w", text_color="#8B949E")
        self.lbl_bench_status.pack(fill="x", padx=12, pady=4)
        ctk.CTkButton(bench, text="Run CPU Test & Save Report", command=self.run_benchmark_report).pack(padx=12, pady=8)

        # Bottom Time Clock
        self.time_label = ctk.CTkLabel(self, text="", text_color="#8B949E")
        self.time_label.pack(side="bottom", pady=5)

    def minimize_to_tray(self):
        self.tray.show_tray()

    def set_mode(self, plan: str):
        self.power_manager.set_active_plan(plan)

    def use_ai_mode(self):
        data = self.collector.get_data()
        cpu = float(data.get("cpu", {}).get("usage_percent", 0))
        mem = float(data.get("memory", {}).get("usage_percent", 0))
        decision = self.ai_optimizer.decide(cpu, mem)
        self.ai_optimizer.apply(decision)

    def enable_game_mode(self):
        res = self.game_mode.enable()
        self.lbl_game_status.configure(text=f"Status: On | Closed {res['closed']} apps (skipped {res['skipped']})")

    def disable_game_mode(self):
        res = self.game_mode.disable()
        self.lbl_game_status.configure(text=f"Status: Off | Mode: {res['mode']}")

    def clean_temp(self):
        res = self.cleaner.clean_temp()
        mb = res.bytes_freed / (1024 * 1024)
        self.lbl_clean_status.configure(text=f"Cleaned {res.files_deleted} items, freed {mb:.2f} MB (skipped {res.files_skipped})")

    def run_benchmark_report(self):
        res = self.reporter.run_and_save(seconds=10)
        self.lbl_bench_status.configure(text=f"Score: {res['score']} | Saved: {res['csv'].split('/')[-1]}")

    def update_data(self):
        data = self.collector.get_data()
        gpu = data.get("gpu", {})
        cpu = data.get("cpu", {})

        # Update Gauges & Graphs
        self.cpu_history.append(cpu.get("usage_percent", 0) or 0)
        self.gpu_history.append(gpu.get("usage_percent", 0) or 0)

        # GPU temp parse
        def _parse_temp(s):
            try:
                if not s: return 0.0
                return float(str(s).split()[0])
            except Exception:
                return 0.0

        self.gpu_temp_history.append(_parse_temp(gpu.get("temperature")))

        self.cpu_gauge.set(self.cpu_history[-1])
        self.gpu_gauge.set(self.gpu_history[-1])
        self.cpu_line.draw(list(self.cpu_history))
        self.gpu_line.draw(list(self.gpu_history))
        self.gpu_temp_line.draw(list(self.gpu_temp_history))

        # Update Labels
        self.gpu_name_label.configure(text=f"GPU: {gpu.get('name', 'N/A')}")
        self.gpu_clock_label.configure(text=f"Clock: {gpu.get('core_clock','N/A')} / {gpu.get('memory_clock','N/A')}")
        self.gpu_temp_label.configure(text=f"Temp: {gpu.get('temperature','N/A')}")
        self.cpu_name_label.configure(text=f"CPU: {cpu.get('name','N/A')}")
        self.cpu_temp_label.configure(text=f"CPU Temp: {cpu.get('temperature','N/A')}")

        # Time Update
        self.time_label.configure(text=datetime.now().strftime("%H:%M:%S"))

        # Repeat every 500ms
        self.after(500, self.update_data)
