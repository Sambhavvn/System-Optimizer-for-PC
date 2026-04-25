from __future__ import annotations
import subprocess
import re
from .logger import logger

class PowerManager:
    """Handles switching between Windows power plans (Balanced, High Performance, Power Saver)."""

    def __init__(self):
        self.plans = {}  # Stores {'Balanced': 'GUID', 'High performance': 'GUID', ...}
        self.active_guid = None
        self._load_plans()

    def _get_startup_info(self):
        """Hide the CMD window when running subprocess on Windows."""
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = subprocess.SW_HIDE
        return info

    def _load_plans(self):
        """Reads all available power plans from the system."""
        try:
            output = subprocess.check_output(
                ["powercfg", "/list"], 
                text=True, 
                stderr=subprocess.DEVNULL, 
                startupinfo=self._get_startup_info()
            )
            pattern = re.compile(r"GUID: ([0-9a-f\-]+)\s+\((.+?)\)(.*\*?)")
            for line in output.splitlines():
                match = pattern.search(line)
                if match:
                    guid, name, is_active = match.groups()
                    if "Balanced" in name:
                        self.plans["Balanced"] = guid
                    elif "High performance" in name:
                        self.plans["High performance"] = guid
                    elif "Power saver" in name:
                        self.plans["Power saver"] = guid

                    if "*" in is_active:
                        self.active_guid = guid

            logger.info("Power plans loaded: %s", self.plans)

        except Exception as e:
            logger.error("⚠ Failed to load power plans: %s", e)

    def get_active_plan_name(self) -> str:
        """Returns the name of the currently active power plan."""
        try:
            output = subprocess.check_output(
                ["powercfg", "/getactivescheme"], 
                text=True, 
                stderr=subprocess.DEVNULL,
                startupinfo=self._get_startup_info()
            )
            match = re.search(r"GUID: ([0-9a-f\-]+)", output)
            if match:
                active_guid = match.group(1)
                for name, guid in self.plans.items():
                    if guid == active_guid:
                        return name
        except Exception as e:
            logger.error("⚠ Failed to get active power plan: %s", e)

        return "Unknown"

    def set_active_plan(self, plan_name: str) -> bool:
        """Activates the given power plan (Balanced, High performance, Power saver)."""
        guid = self.plans.get(plan_name)
        if not guid:
            logger.error("❌ Power plan '%s' not found.", plan_name)
            return False

        try:
            subprocess.run(
                ["powercfg", "/setactive", guid], 
                check=True, 
                stderr=subprocess.DEVNULL,
                startupinfo=self._get_startup_info()
            )
            logger.info("✅ Switched to power plan: %s", plan_name)
            return True
        except Exception as e:
            logger.error("❌ Failed to set power plan '%s': %s", plan_name, e)
            return False
