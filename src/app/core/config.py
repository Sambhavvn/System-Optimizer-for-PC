from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

# App constants
APP_NAME = "System Optimizer"

# Keep paths simple & robust (project-root relative)
PROJECT_ROOT = Path.cwd()
LOG_DIR = PROJECT_ROOT / "logs"
ASSETS_DIR = PROJECT_ROOT / "assets"

LOG_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

@dataclass(slots=True)
class Thresholds:
    CPU_HIGH: float = 80.0
    MEM_HIGH: float = 85.0
    BATTERY_LOW: float = 20.0

@dataclass(slots=True)
class Settings:
    auto_optimize: bool = True
    update_interval_ms: int = 500
    # IMPORTANT: use default_factory for dataclass fields that are objects
    thresholds: Thresholds = field(default_factory=Thresholds)

# Global settings instance
SETTINGS = Settings()
