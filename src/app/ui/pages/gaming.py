import customtkinter as ctk
from ..theme import COLORS
from ...services.game_mode_service import GameModeService

class GamingPage(ctk.CTkFrame):
    """Gaming Centre page: enable/disable game mode."""
    def __init__(self, master):
        super().__init__(master, fg_color=COLORS["bg"])
        self.gm = GameModeService()

        ctk.CTkLabel(self, text="Gaming Centre", font=("Segoe UI", 28, "bold"), text_color=COLORS["text"]).pack(pady=(24, 4))
        ctk.CTkLabel(self, text="Optimize power & close background apps for best FPS.", text_color=COLORS["muted"]).pack()

        row = ctk.CTkFrame(self, fg_color=COLORS["bg"])
        row.pack(pady=16)
        ctk.CTkButton(row, text="Enable Game Mode", command=self.on_enable).pack(side="left", padx=6)
        ctk.CTkButton(row, text="Disable Game Mode", command=self.on_disable).pack(side="left", padx=6)

        self.status = ctk.CTkLabel(self, text="Status: Off", text_color=COLORS["muted"])
        self.status.pack(pady=8)

    def on_enable(self):
        res = self.gm.enable()
        self.status.configure(text=f"Status: On | Closed {res['closed']} apps (skipped {res['skipped']})")

    def on_disable(self):
        res = self.gm.disable()
        self.status.configure(text=f"Status: Off | Mode: {res['mode']}")

    def on_show(self):
        pass
