from __future__ import annotations
import platform, subprocess, threading, time, os
from typing import Dict, Any, List, Optional
import psutil

# Optional backends
try:
    import wmi as _wmi  # CPU temp fallback
except Exception:
    _wmi = None

try:
    import requests as _requests  # LibreHardwareMonitor (optional)
except Exception:
    _requests = None

# NVIDIA NVML (preferred GPU backend)
try:
    import pynvml as _nvml  # nvidia-ml-py3
    _HAS_NVML = True
except Exception:
    _nvml = None
    _HAS_NVML = False


def _ema(prev: Optional[float], new: float, alpha: float = 0.65) -> float:
    """Light smoothing so gauges follow reality closely."""
    return new if prev is None else (alpha * new + (1 - alpha) * prev)


class DataCollector:
    """
    Cross-laptop live system collector (Windows-friendly):
      • CPU: usage % (short 0.2s sample), name, freq, temperature with multi-fallback:
          psutil -> WMI(ACPI) -> LibreHardwareMonitor (web JSON)
      • GPU (NVIDIA): NVML (preferred) -> nvidia-smi -> blanks
      • Memory: used/total, percent
      • Disk: aggregate used %, free/total GB, live R/W MB/s
      • Drives: per-letter rows
    Adds 'ts' + 'status' (backend info). Prints debug lines every ~2s.
    """

    def __init__(self, interval: float = 0.5):
        self.interval = interval
        self._running = True
        self._data: Dict[str, Any] = {"ts": time.time(), "status": {}}
        self._lock = threading.Lock()

        self._cpu_pct: Optional[float] = None
        self._gpu_pct: Optional[float] = None

        # Disk IO baseline
        self._last_io = psutil.disk_io_counters()
        self._last_t = time.time()

        # LHM endpoint (optional)
        self._lhm_url = os.environ.get("LHM_URL", "http://127.0.0.1:8085/data.json")

        # GPU backends
        self._gpu_backend = "none"
        self._nvml_handle = None
        self._nvml_device = None
        self._nvidia_smi_ok = False

        # Init NVML if available
        if _HAS_NVML:
            try:
                _nvml.nvmlInit()
                count = _nvml.nvmlDeviceGetCount()
                if count > 0:
                    self._nvml_device = _nvml.nvmlDeviceGetHandleByIndex(0)
                    self._gpu_backend = "nvml"
            except Exception:
                self._nvml_device = None

        # Fallback: nvidia-smi
        if self._gpu_backend == "none" and platform.system() == "Windows":
            try:
                subprocess.check_output("nvidia-smi -L", shell=True, stderr=subprocess.DEVNULL)
                self._nvidia_smi_ok = True
                self._gpu_backend = "nvidia-smi"
            except Exception:
                self._nvidia_smi_ok = False

        # Start thread
        threading.Thread(target=self._loop, daemon=True).start()

    # ---------------- Loop ----------------
    def _loop(self):
        last_print = 0.0
        while self._running:
            cpu = self._safe(self._cpu, self._data.get("cpu", {}))
            gpu = self._safe(self._gpu, self._data.get("gpu", {}))
            memory = self._safe(self._memory, self._data.get("memory", {}))
            disk = self._safe(self._disk_with_io, self._data.get("disk", {}))
            drives = self._safe(self._drives, self._data.get("drives", []))
            status = {
                "cpu_temp_backend": self._cpu_temp_backend,
                "gpu_backend": self._gpu_backend,
            }

            payload = {"ts": time.time(), "cpu": cpu, "gpu": gpu, "memory": memory, "disk": disk, "drives": drives, "status": status}
            with self._lock:
                self._data = payload

            # Console heartbeat (every ~2s)
            now = time.time()
            if now - last_print > 2.0:
                last_print = now
                try:
                    print(f"[collector] CPU {cpu.get('usage_percent',0)}% | GPU {gpu.get('usage_percent',0)}% | backends CPUtemp={status['cpu_temp_backend']} GPU={status['gpu_backend']}")
                except Exception:
                    pass

            time.sleep(self.interval)

    def _safe(self, fn, default):
        try:
            return fn()
        except Exception:
            return default

    # ---------------- CPU ----------------
    def _cpu(self) -> Dict[str, Any]:
        # Short blocking sample to get real delta; avoids 0% spikes on Windows
        raw = float(psutil.cpu_percent(interval=0.2))
        self._cpu_pct = _ema(self._cpu_pct, raw)
        freq = psutil.cpu_freq()
        return {
            "name": platform.processor() or "CPU",
            "usage_percent": round(self._cpu_pct or raw, 1),
            "temperature": self._cpu_temperature_any(),  # sets self._cpu_temp_backend
            "current_frequency": round(freq.current if freq else 0),
        }

    def _cpu_temperature_any(self) -> str:
        # Default backend marker
        self._cpu_temp_backend = "none"

        # 1) psutil
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for key, arr in temps.items():
                    for e in arr:
                        lbl = (e.label or "").lower()
                        if "cpu" in lbl or "package" in lbl or key.lower().startswith(("coretemp", "k10temp", "amdgpu")):
                            if e.current is not None and 0 < e.current < 120:
                                self._cpu_temp_backend = "psutil"
                                return f"{e.current:.0f} °C"
                # fallback any sensor
                for arr in temps.values():
                    for e in arr:
                        if e.current is not None and 0 < e.current < 120:
                            self._cpu_temp_backend = "psutil:any"
                            return f"{e.current:.0f} °C"
        except Exception:
            pass

        # 2) WMI ACPI
        if _wmi is not None and platform.system() == "Windows":
            try:
                c = _wmi.WMI(namespace="root\\wmi")
                best = None
                for z in c.MSAcpi_ThermalZoneTemperature():
                    t_c = (float(z.CurrentTemperature) / 10.0) - 273.15
                    if 0 < t_c < 120:
                        best = max(best, t_c) if best is not None else t_c
                if best is not None:
                    self._cpu_temp_backend = "wmi-acpi"
                    return f"{best:.0f} °C"
            except Exception:
                pass

        # 3) LibreHardwareMonitor JSON
        if _requests is not None:
            try:
                r = _requests.get(self._lhm_url, timeout=0.25)
                j = r.json()
                def find_temp(node) -> Optional[float]:
                    if isinstance(node, dict):
                        if node.get("SensorType") == "Temperature":
                            name = (node.get("Text") or "").lower()
                            if any(k in name for k in ("package", "cpu", "tctl", "die", "tdie")):
                                val = node.get("Value")
                                if isinstance(val, (int, float)) and 0 < float(val) < 120:
                                    return float(val)
                        for child in node.get("Children", []):
                            v = find_temp(child)
                            if v is not None:
                                return v
                    elif isinstance(node, list):
                        for ch in node:
                            v = find_temp(ch)
                            if v is not None:
                                return v
                    return None
                val = find_temp(j)
                if val is not None:
                    self._cpu_temp_backend = "lhm"
                    return f"{val:.0f} °C"
            except Exception:
                pass

        self._cpu_temp_backend = "none"
        return "—"

    # ---------------- GPU ----------------
    def _gpu(self) -> Dict[str, Any]:
        # NVML first
        if self._gpu_backend == "nvml" and _nvml and self._nvml_device:
            try:
                name = _nvml.nvmlDeviceGetName(self._nvml_device).decode("utf-8", errors="ignore")
                util = _nvml.nvmlDeviceGetUtilizationRates(self._nvml_device).gpu  # %
                temp = _nvml.nvmlDeviceGetTemperature(self._nvml_device, _nvml.NVML_TEMPERATURE_GPU)
                core_clock = _nvml.nvmlDeviceGetClockInfo(self._nvml_device, _nvml.NVML_CLOCK_SM)  # MHz
                mem_clock = _nvml.nvmlDeviceGetClockInfo(self._nvml_device, _nvml.NVML_CLOCK_MEM) # MHz
                self._gpu_pct = _ema(self._gpu_pct, float(util))
                return {
                    "name": name or "GPU",
                    "usage_percent": round(self._gpu_pct or float(util), 1),
                    "temperature": f"{float(temp):.0f} °C",
                    "core_clock": f"{float(core_clock):.0f} MHz",
                    "memory_clock": f"{float(mem_clock):.0f} MHz",
                }
            except Exception:
                # fallback to nvidia-smi if available
                pass

        # nvidia-smi fallback
        if self._gpu_backend in ("nvidia-smi", "nvml") and self._nvidia_smi_ok:
            try:
                out = subprocess.check_output(
                    "nvidia-smi --query-gpu=name,utilization.gpu,temperature.gpu,clocks.gr,clocks.mem "
                    "--format=csv,noheader,nounits",
                    shell=True, text=True, stderr=subprocess.DEVNULL
                ).strip().splitlines()[0]
                name, usage, temp, core, mem = [p.strip() for p in out.split(",")]
                u = float(usage)
                self._gpu_pct = _ema(self._gpu_pct, u)
                return {
                    "name": name or "GPU",
                    "usage_percent": round(self._gpu_pct or u, 1),
                    "temperature": f"{float(temp):.0f} °C",
                    "core_clock": f"{float(core):.0f} MHz",
                    "memory_clock": f"{float(mem):.0f} MHz",
                }
            except Exception:
                pass

        # No backend
        self._gpu_backend = "none"
        return {
            "name": "GPU",
            "usage_percent": 0.0,
            "temperature": "—",
            "core_clock": "N/A",
            "memory_clock": "N/A",
        }

    # ---------------- Memory/Disk/Drives ----------------
    def _memory(self) -> Dict[str, Any]:
        m = psutil.virtual_memory()
        used = (m.total - m.available) / (1024**3)
        total = m.total / (1024**3)
        return {"usage_percent": float(m.percent), "used_gb": used, "total_gb": total}

    def _disk_with_io(self) -> Dict[str, Any]:
        total = used = free = 0
        for p in psutil.disk_partitions(all=False):
            if not p.fstype or 'cdrom' in (p.opts or "").lower():
                continue
            try:
                u = psutil.disk_usage(p.mountpoint)
                total += u.total; used += u.used; free += u.free
            except Exception:
                continue

        now = time.time()
        io = psutil.disk_io_counters()
        dt = max(0.001, now - self._last_t)
        read_mb = (io.read_bytes - self._last_io.read_bytes) / (1024**2) / dt
        write_mb = (io.write_bytes - self._last_io.write_bytes) / (1024**2) / dt
        self._last_io = io; self._last_t = now

        out = {"read_mb_s": read_mb, "write_mb_s": write_mb}
        if total > 0:
            out.update({
                "usage_percent": (used/total)*100,
                "free_gb": free/(1024**3),
                "total_gb": total/(1024**3),
            })
        return out

    def _drives(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for p in psutil.disk_partitions(all=False):
            if not p.fstype or 'cdrom' in (p.opts or "").lower():
                continue
            try:
                u = psutil.disk_usage(p.mountpoint)
                letter = p.device.strip("\\:")[:1].upper()
                rows.append({
                    "letter": letter,
                    "fs": p.fstype,
                    "total_gb": u.total/(1024**3),
                    "free_gb": u.free/(1024**3),
                    "used_pct": (u.used/u.total)*100,
                })
            except Exception:
                continue
        rows.sort(key=lambda r: (r["letter"] not in ("C","D"), r["letter"]))
        return rows

    # --------------- API ---------------
    def get_data(self) -> Dict[str, Any]:
        with self._lock:
            return self._data

    def stop(self) -> None:
        self._running = False


# Singleton helpers
_instance: Optional[DataCollector] = None

def get_collector() -> DataCollector:
    global _instance
    if _instance is None:
        _instance = DataCollector()
    return _instance

def stop_collector() -> None:
    global _instance
    if _instance:
        _instance.stop(); _instance = None

def restart_collector() -> DataCollector:
    stop_collector()
    return get_collector()
