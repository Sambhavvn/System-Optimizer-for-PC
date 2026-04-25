from __future__ import annotations
import threading
from PIL import Image, ImageDraw
import pystray

def _default_icon(size: int = 64) -> Image.Image:
    # Simple cyan circle icon
    img = Image.new("RGBA", (size, size), (13, 17, 23, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((8, 8, size-8, size-8), outline=(88, 166, 255, 255), width=4)
    d.ellipse((16, 16, size-16, size-16), fill=(0, 255, 255, 180))
    return img

class TrayController:
    def __init__(self, app):
        self.app = app
        self.icon = pystray.Icon(
            "SystemOptimizer",
            _default_icon(),
            "System Optimizer",
            menu=pystray.Menu(
                pystray.MenuItem("Show", self._on_show),
                pystray.MenuItem("Exit", self._on_exit)
            )
        )

    def show_tray(self):
        # Withdraw Tk window and start tray thread
        self.app.withdraw()
        t = threading.Thread(target=self.icon.run, daemon=True)
        t.start()

    def _on_show(self, _):
        self.app.after(0, self._restore)

    def _restore(self):
        try:
            self.icon.stop()
        except Exception:
            pass
        self.app.deiconify()
        self.app.lift()

    def _on_exit(self, _):
        self.app.after(0, self._quit)

    def _quit(self):
        try:
            self.icon.stop()
        except Exception:
            pass
        self.app.quit()
