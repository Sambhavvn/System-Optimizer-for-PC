import customtkinter as ctk
from ..theme import COLORS
from ...core.config import SETTINGS
from ...core.power_manager import PowerManager

class SettingsPage(ctk.CTkFrame):
    """Settings page: show active power plan and thresholds."""
    def __init__(self, master):
        super().__init__(master, fg_color=COLORS["bg"])
        self.pm = PowerManager()

        ctk.CTkLabel(self, text="Settings", font=("Segoe UI", 28, "bold"), text_color=COLORS["text"]).pack(pady=(24, 4))
        ctk.CTkLabel(self, text="General application settings & info.", text_color=COLORS["muted"]).pack()

        card = ctk.CTkFrame(self, fg_color=COLORS["panel"], corner_radius=12)
        card.pack(pady=16, padx=24, fill="x")

        self.lbl_plan = ctk.CTkLabel(card, text="Active Power Plan: --", text_color=COLORS["text"])
        self.lbl_plan.pack(anchor="w", padx=16, pady=8)

        t = SETTINGS.thresholds
        ctk.CTkLabel(card, text=f"CPU High Threshold: {t.CPU_HIGH:.0f}%", text_color=COLORS["muted"]).pack(anchor="w", padx=16)
        ctk.CTkLabel(card, text=f"Memory High Threshold: {t.MEM_HIGH:.0f}%", text_color=COLORS["muted"]).pack(anchor="w", padx=16)
        ctk.CTkLabel(card, text=f"Battery Low Threshold: {t.BATTERY_LOW:.0f}%", text_color=COLORS["muted"]).pack(anchor="w", padx=16, pady=(0, 10))

    def on_show(self):
        self.lbl_plan.configure(text=f"Active Power Plan: {self.pm.get_active_plan_name()}")
