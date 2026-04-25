from __future__ import annotations
import psutil
from typing import Iterable
from ..core.power_manager import PowerManager
from ..core.logger import logger

SAFE_CLOSE_PROCESSES: list[str] = [
    # 👍 Add only user apps here (never Windows/system services)
    "OneDrive.exe",
    "Discord.exe",
    "Steam.exe",
    "EpicGamesLauncher.exe",
    "Chrome.exe",
    "ms-teams.exe",
    "Teams.exe",
    "Spotify.exe",
    "Code.exe",           # VS Code
]

class GameModeService:
    """
    Game Mode:
    - Switches power plan to High performance
    - Tries to close known background apps safely
    """

    def __init__(self) -> None:
        self.pm = PowerManager()

    def enable(self) -> dict:
        self.pm.set_active_plan("High performance")
        closed, skipped = self._close_background_processes(SAFE_CLOSE_PROCESSES)
        logger.info("Game Mode: enabled (closed=%d, skipped=%d)", closed, skipped)
        return {"closed": closed, "skipped": skipped, "mode": "High performance"}

    def disable(self) -> dict:
        self.pm.set_active_plan("Balanced")
        logger.info("Game Mode: disabled (Balanced)")
        return {"mode": "Balanced"}

    def _close_background_processes(self, names: Iterable[str]) -> tuple[int, int]:
        closed = 0
        skipped = 0
        name_set = {n.lower() for n in names}
        for proc in psutil.process_iter(["name", "exe"]):
            try:
                pname = (proc.info.get("name") or "").lower()
                if pname in name_set:
                    proc.terminate()  # send polite terminate
                    closed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                skipped += 1
        return closed, skipped
