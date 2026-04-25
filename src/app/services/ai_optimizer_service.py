from __future__ import annotations
from dataclasses import dataclass
from ..core.config import SETTINGS
from ..core.power_manager import PowerManager
from ..core.logger import logger

@dataclass
class AiDecision:
    """Stores AI decision result."""
    mode: str
    reason: str

class AiOptimizerService:
    """Automatically decides best power mode based on CPU/MEM activity."""

    def __init__(self):
        self.pm = PowerManager()

    def decide(self, cpu_usage: float, memory_usage: float, on_battery: bool = False) -> AiDecision:
        """
        Simple rule-based AI:
        - If on battery → Power Saver
        - If CPU or Memory crosses threshold → High Performance
        - Else → Balanced mode
        """
        thresholds = SETTINGS.thresholds

        if on_battery:
            return AiDecision("Power saver", "Battery mode detected")

        if cpu_usage > thresholds.CPU_HIGH or memory_usage > thresholds.MEM_HIGH:
            return AiDecision("High performance", "High load detected")

        return AiDecision("Balanced", "Normal usage")

    def apply(self, decision: AiDecision) -> bool:
        """Applies power plan based on decision."""
        logger.info(f"⚙ Applying AI Decision: {decision.mode} ({decision.reason})")
        return self.pm.set_active_plan(decision.mode)
