import customtkinter as ctk

class PillToggle(ctk.CTkSwitch):
    """Modern rounded toggle switch for AI Mode."""
    def __init__(self, master, text="", command=None):
        super().__init__(master, text=text, command=command, switch_width=60, switch_height=28)
