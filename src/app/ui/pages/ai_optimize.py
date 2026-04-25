import customtkinter as ctk
from ..theme import COLORS
from ...core.collector import get_collector
from ...services.ai_optimizer_service import AiOptimizerService
from ..widgets.pill_toggle import PillToggle

class AiOptimizePage(ctk.CTkFrame):
    """AI Optimize page: toggle & manual plan buttons only on this page."""
    def __init__(self, master):
        super().__init__(master, fg_color=COLORS["bg"])
        self.collector = get_collector()
        self.ai = AiOptimizerService()

        ctk.CTkLabel(self, text="AI Optimization", font=("Segoe UI", 28, "bold"), text_color=COLORS["text"]).pack(pady=(24, 4))
        ctk.CTkLabel(self, text="Let AI choose the best power plan for your workload.", text_color=COLORS["muted"]).pack()

        box = ctk.CTkFrame(self, fg_color=COLORS["panel"], corner_radius=12)
        box.pack(pady=24, padx=24)

        self.toggle = PillToggle(box, text="AI Mode", command=self._apply_ai)
        self.toggle.pack(padx=16, pady=16)

        btns = ctk.CTkFrame(self, fg_color=COLORS["bg"])
        btns.pack(pady=8)
        ctk.CTkButton(btns, text="Performance", command=lambda: self._set("High performance")).pack(side="left", padx=6)
        ctk.CTkButton(btns, text="Balanced", command=lambda: self._set("Balanced")).pack(side="left", padx=6)
        ctk.CTkButton(btns, text="Power Saver", command=lambda: self._set("Power saver")).pack(side="left", padx=6)

        self.status = ctk.CTkLabel(self, text="Status: Idle", text_color=COLORS["muted"])
        self.status.pack(pady=8)

    def _apply_ai(self):
        d = self.collector.get_data()
        cpu = float(d.get("cpu", {}).get("usage_percent", 0) or 0)
        mem = float(d.get("memory", {}).get("usage_percent", 0) or 0)
        decision = self.ai.decide(cpu, mem)
        ok = self.ai.apply(decision)
        self.status.configure(text=f"AI set: {decision.mode} ({decision.reason})" if ok else "Failed to apply AI decision")

    def _set(self, name: str):
        from ...core.power_manager import PowerManager
        pm = PowerManager()
        ok = pm.set_active_plan(name)
        self.status.configure(text=f"Switched to {name}" if ok else f"Failed to switch to {name}")

    def on_show(self):
        pass
