import customtkinter as ctk
from ..theme import COLORS, FONTS

class Badge(ctk.CTkFrame):
    """
    Small pill badge for statuses (e.g., backends).
    Usage:
       Badge(parent, text="GPU: NVML", tone="ok"|"warn"|"danger"|"info")
    """
    def __init__(self, master, text:str, tone:str="info"):
        super().__init__(master, fg_color="transparent")
        colors = {
            "info":   ("#0B2536", COLORS["accent"]),
            "ok":     ("#0D2B22", COLORS["ok"]),
            "warn":   ("#2A230C", COLORS["warn"]),
            "danger": ("#331516", COLORS["danger"]),
        }.get(tone, ("#0B2536", COLORS["accent"]))

        pill = ctk.CTkFrame(self, fg_color=colors[0], corner_radius=999)
        pill.pack(side="left", padx=0, pady=0)
        ctk.CTkLabel(pill, text=text, text_color=colors[1], font=("Segoe UI", 11, "bold")).pack(padx=10, pady=4)

    def set_text(self, new_text: str):
        # Re-render label for simplicity (keeps API tiny)
        for w in self.winfo_children():
            w.destroy()
        self.__init__(self.master, new_text)
