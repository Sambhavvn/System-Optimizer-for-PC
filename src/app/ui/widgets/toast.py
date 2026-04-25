import customtkinter as ctk
from ..theme import COLORS, FONTS

def show_toast(root, message: str, ms=2200):
    """
    Tiny toast (top-right) that auto-dismisses. root is a toplevel (app window).
    """
    try:
        x = root.winfo_rootx() + root.winfo_width() - 320
        y = root.winfo_rooty() + 24
    except Exception:
        x, y = 100, 100

    win = ctk.CTkToplevel(root)
    win.overrideredirect(True)
    win.attributes("-topmost", True)
    win.configure(fg_color=COLORS["panel"])
    ctk.CTkLabel(win, text=message, text_color=COLORS["text"], font=FONTS["body"]).pack(padx=14, pady=10)
    win.update_idletasks()
    win.geometry(f"+{int(x)}+{int(y)}")
    win.after(ms, win.destroy)
