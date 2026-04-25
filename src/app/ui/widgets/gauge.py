import customtkinter as ctk

class Gauge(ctk.CTkCanvas):
    """Circular gauge with thick track and cyan arc (stable)."""
    def __init__(self, master, size=240, caption: str | None = None):
        try:
            bg = master.cget("fg_color")
            if isinstance(bg, (tuple, list)):
                bg = bg[-1]
        except Exception:
            bg = "#0D1117"

        super().__init__(master, width=size, height=size, bg=bg, highlightthickness=0)
        self.size = size
        self.caption = caption or ""
        ring = 24
        pad = 20
        bbox = (pad, pad, size - pad, size - pad)

        # background ring
        self.create_arc(*bbox, start=90, extent=359.9, style="arc", width=ring, outline="#1F242C")
        # live arc
        self.arc = self.create_arc(*bbox, start=90, extent=0, style="arc", width=ring, outline="#58A6FF")
        # value
        self.txt = self.create_text(size/2, size/2 - 6, text="0%", font=("Segoe UI", 40, "bold"), fill="#C9D1D9")
        # caption (optional)
        if self.caption:
            self.create_text(size/2, size/2 + 28, text=self.caption, font=("Segoe UI", 12), fill="#9CA3AF")

    def set(self, v: float):
        v = max(0.0, min(100.0, float(v)))
        self.itemconfigure(self.arc, extent=-(v/100.0)*359.9)
        self.itemconfigure(self.txt, text=f"{int(v)}%")
