# app_shell.py
# Top navigation + page switching — adds a "Benchmark" tab wired to your existing BenchmarkPage.
# Keeps Hardware and User Scenario exactly as they were.

import customtkinter as ctk
from .theme import COLORS, FONTS, SPACING
from .pages.hardware import HardwarePage
from .pages.user_scenario import UserScenarioPage
from .pages.benchmark import BenchmarkPage  # use your existing benchmark page

class AppShell(ctk.CTkFrame):
    """
    Top navigation bar + page switching.
    Pages:
        - Hardware Monitoring
        - User Scenario
        - Benchmark
    """
    def __init__(self, master):
        super().__init__(master, fg_color=COLORS["bg"])
        self.pack(fill="both", expand=True)

        self.pages = {}
        self.active = None

        self._build_topnav()
        self._build_container()
        self._switch("Hardware Monitoring")

    def _build_topnav(self):
        self.top = ctk.CTkFrame(self, fg_color=COLORS["panel"])
        self.top.pack(fill="x")

        # Tabs mapping: keep existing pages intact, add Benchmark
        self.tabs = {
            "Hardware Monitoring": lambda parent: HardwarePage(parent),
            "User Scenario":       lambda parent: UserScenarioPage(parent),
            "Benchmark":           lambda parent: BenchmarkPage(parent),
        }

        self.btns = {}
        for name in self.tabs:
            b = ctk.CTkButton(
                self.top,
                text=name,
                fg_color="transparent",
                hover_color=COLORS["border"],
                text_color=COLORS["text"],
                command=lambda n=name: self._switch(n)
            )
            b.pack(side="left", padx=8, pady=8)
            self.btns[name] = b

        # Active underline
        self.active_bar = ctk.CTkFrame(
            self,
            height=2,
            fg_color=COLORS.get("accent", COLORS["bar_fill"])
        )
        self.active_bar.pack(fill="x")

    def _build_container(self):
        self.container = ctk.CTkFrame(self, fg_color=COLORS["bg"])
        self.container.pack(fill="both", expand=True,
                            padx=SPACING.get("pad", 16), pady=(SPACING.get("pad", 16), SPACING.get("pad", 16)))

    def _switch(self, name: str):
        if self.active == name:
            return

        # Destroy old frame(s)
        for w in self.container.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass

        # Create & show new frame
        try:
            page = self.tabs[name](self.container)
            page.pack(fill="both", expand=True)
        except Exception as e:
            # Fallback: show a simple error card if page construction fails
            err_card = ctk.CTkFrame(self.container, fg_color=COLORS["panel"], corner_radius=12)
            err_card.pack(fill="both", expand=True, padx=SPACING.get("pad", 16), pady=SPACING.get("pad", 16))
            ctk.CTkLabel(err_card, text=f"Failed to load {name}", font=(FONTS["h2"][0], 16, "bold"), text_color=COLORS["text"]).pack(pady=12)
            ctk.CTkLabel(err_card, text=str(e), text_color=COLORS["muted"], wraplength=900).pack(padx=12)
        self.active = name

        # Highlight active button
        for n, b in self.btns.items():
            try:
                b.configure(fg_color=(COLORS["border"] if n == name else "transparent"))
            except Exception:
                pass
