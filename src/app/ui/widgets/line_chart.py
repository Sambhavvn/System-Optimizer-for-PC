import customtkinter as ctk
from datetime import datetime

class LineChart(ctk.CTkCanvas):
    """
    Compact line chart with:
    - Dark panel background
    - Y-axis ticks (0,25,50,75,100)
    - X-axis 'Time' + current hh:mm:ss
    """

    def __init__(self, master, width=300, height=210):
        super().__init__(master, width=width, height=height, bg="#161B22", highlightthickness=0)

        self.width = width
        self.height = height

        # Drawing area (graph boundaries)
        self.graph_left = 50
        self.graph_top = 10
        self.graph_right = width - 15
        self.graph_bottom = height - 35

        # Create line object (empty initially)
        self.line = self.create_line(0, 0, 0, 0, fill="#58A6FF", width=2, smooth=True)

    def draw_axes(self):
        """Redraw background axes, grid and time label"""
        self.delete("axis")

        # Draw axis lines
        self.create_line(
            self.graph_left, self.graph_bottom,
            self.graph_left, self.graph_top,
            fill="#8B949E", width=1, tags="axis"
        )
        self.create_line(
            self.graph_left, self.graph_bottom,
            self.graph_right, self.graph_bottom,
            fill="#8B949E", width=1, tags="axis"
        )

        # Y-axis labels and grid
        for val in (0, 25, 50, 75, 100):
            y = self.graph_bottom - (val / 100) * (self.graph_bottom - self.graph_top)
            if 0 < val < 100:
                self.create_line(self.graph_left, y, self.graph_right, y, fill="#30363D", tags="axis")
            self.create_text(self.graph_left - 10, y, text=f"{val}", fill="#8B949E", anchor="e", tags="axis", font=("Segoe UI", 9))

        # Axis labels
        self.create_text((self.graph_left + self.graph_right) / 2, self.graph_bottom + 15, text="Time", fill="#8B949E", font=("Segoe UI", 9), tags="axis")
        self.create_text(20, (self.graph_top + self.graph_bottom) / 2, text="Usage (%)", fill="#8B949E", font=("Segoe UI", 9), angle=90, tags="axis")

        # Time at bottom right
        self.create_text(self.graph_right, self.graph_bottom + 15, text=datetime.now().strftime("%H:%M:%S"),
                         fill="#8B949E", anchor="e", tags="axis", font=("Segoe UI", 9, "bold"))

    def draw(self, data):
        """Draw updated line from list of usage values"""
        self.draw_axes()

        if not data or len(data) < 2:
            self.coords(self.line, [])
            return

        points = []
        n = len(data) - 1
        for i, value in enumerate(data):
            x = self.graph_left + (i / n) * (self.graph_right - self.graph_left)
            y = self.graph_bottom - (float(value) / 100) * (self.graph_bottom - self.graph_top)
            points.extend([x, y])

        self.coords(self.line, *points)
