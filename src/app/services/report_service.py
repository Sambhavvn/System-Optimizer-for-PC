"""
ReportService - improved GPU stress + CPU benchmark helpers.

Features added in this iteration:
- Detect Optimus-like configuration via nvidia-smi parsing.
- Auto-download a sample stress video into reports/stress_video.mp4 (best-effort).
- Use mpv/ffplay to play the sample video as fallback renderer (higher chance to wake dGPU).
- Improved CPU worker intensity and safe stop/cleanup logic.
"""

from __future__ import annotations
import os
import time
import json
import shutil
import subprocess
import multiprocessing as mp
from multiprocessing import Process
from typing import Optional, Any, Dict, List
from pathlib import Path
import urllib.request

# Try to use project logger if available
try:
    from src.app.core.logger import logger
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("report_service")

# Optional runtime libs
try:
    import psutil
except Exception:
    psutil = None

# Ensure spawn context on Windows
try:
    mp_ctx = mp.get_context("spawn")
except Exception:
    mp_ctx = mp

REPORTS_DIR = Path.cwd() / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

def _now_ts():
    return int(time.time())

# ----- Low-level worker functions (run in child processes) -----

def _cpu_worker_main(duration_seconds: int, ops_counter_path: str, stop_event: mp.Event):
    """
    CPU-bound worker. Tight arithmetic loops to generate load.
    Writes operations count to ops_counter_path at the end.
    """
    start = time.time()
    ops = 0
    x = 0.0001
    try:
        while not stop_event.is_set() and (time.time() - start) < duration_seconds:
            # tuned inner loop size for aggressive CPU saturation but allowing scheduler fairness
            for _ in range(50000):
                x = x * 1.0000001 + 0.000001
                ops += 1
            # small sleep slice to reduce starvation of other system tasks
            time.sleep(0.001)
    except Exception:
        pass
    # append ops
    try:
        with open(ops_counter_path, "a", encoding="utf-8") as f:
            f.write(f"{ops}\n")
    except Exception:
        pass


def _moderngl_renderer_main(seconds: int, stop_event: mp.Event):
    """
    Minimal ModernGL shader renderer to stress GPU.
    Runs in a separate process. Raises ImportError if moderngl/pyglet missing.
    """
    try:
        import time
        import moderngl
        import pyglet
    except Exception as e:
        raise

    window = None
    try:
        window = pyglet.window.Window(width=1280, height=720, caption="GPU Stress", visible=True, resizable=False)
        ctx = moderngl.create_context()
        prog = ctx.program(
            vertex_shader='''
                #version 330
                in vec2 in_pos;
                void main() { gl_Position = vec4(in_pos, 0.0, 1.0); }
            ''',
            fragment_shader='''
                #version 330
                out vec4 color;
                uniform float t;
                void main() {
                    float v = fract(sin(gl_FragCoord.x * 12.9898 + gl_FragCoord.y * 78.233 + t) * 43758.5453);
                    color = vec4(v, v*0.5, 1.0 - v, 1.0);
                }
            '''
        )
        # big buffer to hammer GPU
        import math
        import struct
        data = b''.join([struct.pack('2f', (i % 3) - 1.0, ((i//3) % 3) - 1.0) for i in range(3 * 20000)])
        vbo = ctx.buffer(data)
        vao = ctx.simple_vertex_array(prog, vbo, 'in_pos')
        start = time.time()
        t = 0.0
        while not stop_event.is_set() and (time.time() - start) < seconds:
            prog['t'].value = t
            # multiple renders per frame
            for _ in range(60):
                vao.render(mode=moderngl.TRIANGLES)
            window.flip()
            t += 0.016
    finally:
        try:
            if window is not None:
                window.close()
        except Exception:
            pass


# ----- ReportService class -----

class ReportService:
    def __init__(self):
        self._stop_event = mp_ctx.Event()
        self._child_stop_event = None
        self._active_processes: List[mp_ctx.Process] = []
        self._last_report: Optional[Dict[str, Any]] = None

    def stop_benchmark(self):
        logger.info("ReportService: stop_benchmark called")
        try:
            self._stop_event.set()
            if self._child_stop_event:
                try:
                    self._child_stop_event.set()
                except Exception:
                    pass
            # terminate active processes
            for p in list(self._active_processes):
                try:
                    if isinstance(p, subprocess.Popen):
                        p.terminate()
                    else:
                        if p.is_alive():
                            p.terminate()
                except Exception:
                    pass
            self._active_processes = []
        except Exception:
            pass

    # ---------- CPU benchmark ----------
    def run_and_save(self, *, seconds: int = 10, iterations: int = 1, sample_queue: Optional[mp.Queue] = None) -> Dict[str, Any]:
        """
        Runs CPU benchmark: spawns one worker per logical CPU in separate processes
        and streams periodic cpu_percent samples to sample_queue.
        """
        logger.info("ReportService: run_and_save start seconds=%s iters=%s", seconds, iterations)
        ops_file = REPORTS_DIR / f"cpu_ops_{_now_ts()}.tmp"
        try:
            if ops_file.exists():
                ops_file.unlink()
        except Exception:
            pass

        child_stop = mp_ctx.Event()
        self._child_stop_event = child_stop
        cpu_count = mp.cpu_count()
        workers = []
        total_duration = seconds * iterations
        # spawn processes
        for _ in range(cpu_count):
            p = mp_ctx.Process(target=_cpu_worker_main, args=(total_duration, str(ops_file), child_stop), daemon=True)
            p.start()
            workers.append(p)
            self._active_processes.append(p)

        samples: List[Dict[str, Any]] = []
        try:
            t_end = time.time() + total_duration
            while time.time() < t_end and not self._stop_event.is_set() and not child_stop.is_set():
                cpu_pct = None
                try:
                    if psutil:
                        cpu_pct = psutil.cpu_percent(interval=1.0)
                    else:
                        time.sleep(1.0)
                except Exception:
                    cpu_pct = None
                sample = {"t": time.time(), "cpu_util_percent": cpu_pct}
                samples.append(sample)
                if sample_queue:
                    try:
                        sample_queue.put(sample)
                    except Exception:
                        pass
            # ensure children stop
            child_stop.set()
        except KeyboardInterrupt:
            child_stop.set()
        finally:
            # join and cleanup
            for w in workers:
                try:
                    w.join(timeout=1.0)
                except Exception:
                    try:
                        if w.is_alive():
                            w.terminate()
                    except Exception:
                        pass
            # read ops
            total_ops = 0
            try:
                if ops_file.exists():
                    with open(ops_file, "r", encoding="utf-8") as f:
                        for line in f:
                            try:
                                total_ops += int(line.strip())
                            except Exception:
                                pass
            except Exception:
                pass

            elapsed = max(1.0, total_duration)
            mean_ops = total_ops / elapsed if elapsed else 0.0
            stdev_ops = 0.0
            csv_path = REPORTS_DIR / f"cpu_benchmark_{_now_ts()}.csv"
            try:
                with open(csv_path, "w", encoding="utf-8") as fh:
                    fh.write("ts,cpu_util\n")
                    for s in samples:
                        fh.write(f"{s['t']},{s.get('cpu_util_percent')}\n")
            except Exception:
                pass

            meta = {"mean_ops_per_sec": mean_ops, "stdev_ops_per_sec": stdev_ops, "samples": samples, "csv": str(csv_path)}
            self._last_report = meta
            logger.info("ReportService: run_and_save finished mean_ops=%s", mean_ops)
            # reset stop_event for future runs
            self._stop_event.clear()
            return meta

    # ---------- GPU probe ----------
    def gpu_probe(self, *, seconds: int = 10, sample_interval: float = 1.0, sample_queue: Optional[mp.Queue] = None) -> Dict[str, Any]:
        logger.info("ReportService: gpu_probe start seconds=%s", seconds)
        samples: List[Dict[str, Any]] = []
        start = time.time()
        while (time.time() - start) < seconds and not self._stop_event.is_set():
            sample = {"t": time.time(), "gpu_util": None, "gpu_temp_c": None, "gpu_source": None}
            try:
                p = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"],
                                   capture_output=True, text=True, timeout=1.0)
                if p.returncode == 0 and p.stdout:
                    line = p.stdout.strip().splitlines()[0].strip()
                    parts = [x.strip() for x in line.split(",")]
                    if parts and parts[0]:
                        try:
                            sample["gpu_util"] = float(parts[0])
                        except Exception:
                            sample["gpu_util"] = None
                    if len(parts) > 1 and parts[1]:
                        try:
                            sample["gpu_temp_c"] = float(parts[1])
                        except Exception:
                            sample["gpu_temp_c"] = None
                    sample["gpu_source"] = "nvidia-smi"
            except Exception:
                pass
            samples.append(sample)
            if sample_queue:
                try:
                    sample_queue.put(sample)
                except Exception:
                    pass
            time.sleep(sample_interval)

        gpu_vals = [s["gpu_util"] for s in samples if isinstance(s.get("gpu_util"), (int, float))]
        temp_vals = [s["gpu_temp_c"] for s in samples if isinstance(s.get("gpu_temp_c"), (int, float))]
        summary = {"avg_gpu_util": (sum(gpu_vals) / len(gpu_vals)) if gpu_vals else None,
                   "avg_gpu_temp": (sum(temp_vals) / len(temp_vals)) if temp_vals else None}
        csv_path = REPORTS_DIR / f"gpu_probe_{_now_ts()}.csv"
        try:
            with open(csv_path, "w", encoding="utf-8") as fh:
                fh.write("ts,gpu_util,gpu_temp,source\n")
                for s in samples:
                    fh.write(f"{s['t']},{s.get('gpu_util')},{s.get('gpu_temp_c')},{s.get('gpu_source')}\n")
        except Exception:
            pass
        meta = {"samples": samples, "summary": summary, "csv": str(csv_path)}
        self._last_report = meta
        logger.info("ReportService: gpu_probe finished summary=%s", summary)
        return meta

    # ---------- Helper: detect Optimus (best-effort) ----------
    def detect_optimus(self) -> bool:
        """
        Heuristic: run nvidia-smi and check if display is Off for GPU(s).
        If NVIDIA present and display shows Off, likely Optimus (Intel primary).
        """
        try:
            p = subprocess.run(["nvidia-smi", "-q"], capture_output=True, text=True, timeout=1.0)
            if p.returncode != 0:
                return False
            out = p.stdout.lower()
            if "display active" in out:
                # try to parse Display Active / Display Mode
                if "display active : no" in out or "display active : off" in out:
                    return True
            # fallback: check for "disp.a" style quick output which sometimes contains Off
            q = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=1.0)
            if q.returncode == 0 and "off" in q.stdout.lower():
                return True
        except Exception:
            pass
        return False

    # ---------- Helper: download sample video (best-effort) ----------
    def ensure_sample_video(self, *, url: Optional[str] = None) -> Optional[str]:
        """
        Best-effort: download a sample video into REPORTS_DIR/stress_video.mp4.
        If url is None, uses a small default CDN-hosted test file (may fail).
        Returns path to file or None on failure.
        """
        target = REPORTS_DIR / "stress_video.mp4"
        # if already exists, return it
        if target.exists() and target.stat().st_size > 1024:
            return str(target)
        # default sample (a small test) - NOTE: network may fail
        default_url = url or "https://sample-videos.com/video123/mp4/1080/big_buck_bunny_1080p_1mb.mp4"
        try:
            logger.info("ReportService: downloading sample video from %s", default_url)
            with urllib.request.urlopen(default_url, timeout=12) as r:
                data = r.read()
                if not data:
                    return None
                with open(target, "wb") as fh:
                    fh.write(data)
            return str(target)
        except Exception as e:
            logger.info("ReportService: sample video download failed: %s", e)
            try:
                if target.exists():
                    target.unlink()
            except Exception:
                pass
            return None

    # ---------- GPU stress implementation ----------
    def run_gpu_stress_internal(self, *, seconds: int = 10, sample_queue: Optional[mp.Queue] = None) -> Dict[str, Any]:
        """
        Try to stress GPU:
         - prefer moderngl renderer (fastest, no external player)
         - fallback -> try mpv/ffplay + a downloaded sample video (best chance on Optimus)
         - while running, poll nvidia-smi every 0.5s and push samples to sample_queue
        """
        logger.info("ReportService: run_gpu_stress_internal start seconds=%s", seconds)
        samples: List[Dict[str, Any]] = []
        stop_evt = mp_ctx.Event()
        self._child_stop_event = stop_evt

        # Try moderngl renderer in a process
        renderer_proc = None
        used_method = None
        try:
            renderer_proc = mp_ctx.Process(target=_moderngl_renderer_main, args=(seconds, stop_evt), daemon=True)
            renderer_proc.start()
            self._active_processes.append(renderer_proc)
            # give it a short grace to fail fast if imports missing
            time.sleep(0.8)
            if renderer_proc.is_alive():
                used_method = "moderngl"
                logger.info("ReportService: moderngl renderer started")
            else:
                # clean join
                try:
                    renderer_proc.join(timeout=0.5)
                except Exception:
                    pass
                renderer_proc = None
        except Exception:
            renderer_proc = None

        fallback_proc = None
        # If moderngl failed, try video player
        if not renderer_proc:
            # attempt to ensure sample video exists
            video_path = None
            try:
                video_path = self.ensure_sample_video()
            except Exception:
                video_path = None

            # pick player
            player_cmd = None
            if shutil.which("mpv"):
                player_cmd = ["mpv", "--fs", "--loop=inf", "--no-terminal", "--really-quiet", "--hwdec=auto"]
            elif shutil.which("ffplay"):
                player_cmd = ["ffplay", "-autoexit", "-loop", "0", "-loglevel", "quiet"]
            # if player exists and video available, launch it
            if player_cmd and video_path:
                try:
                    cmd = player_cmd + [video_path]
                    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    fallback_proc = proc
                    used_method = "external-player"
                    self._active_processes.append(proc)
                except Exception as e:
                    logger.info("ReportService: external player launch failed: %s", e)
                    fallback_proc = None
            else:
                # as last resort try to spawn moderngl again (maybe imports available)
                try:
                    proc2 = mp_ctx.Process(target=_moderngl_renderer_main, args=(seconds, stop_evt), daemon=True)
                    proc2.start()
                    time.sleep(0.6)
                    if proc2.is_alive():
                        fallback_proc = proc2
                        used_method = "moderngl-fallback"
                        self._active_processes.append(proc2)
                    else:
                        try:
                            proc2.join(timeout=0.5)
                        except Exception:
                            pass
                except Exception:
                    pass

        # Monitor loop: poll nvidia-smi and stream samples
        start = time.time()
        try:
            while (time.time() - start) < seconds and not self._stop_event.is_set() and not stop_evt.is_set():
                sample = {"t": time.time(), "gpu_util": None, "gpu_temp_c": None, "gpu_source": None}
                try:
                    p = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"],
                                       capture_output=True, text=True, timeout=1.0)
                    if p.returncode == 0 and p.stdout:
                        line = p.stdout.strip().splitlines()[0].strip()
                        parts = [x.strip() for x in line.split(",")]
                        if parts and parts[0]:
                            try:
                                sample["gpu_util"] = float(parts[0])
                            except Exception:
                                sample["gpu_util"] = None
                        if len(parts) > 1 and parts[1]:
                            try:
                                sample["gpu_temp_c"] = float(parts[1])
                            except Exception:
                                sample["gpu_temp_c"] = None
                        sample["gpu_source"] = "nvidia-smi"
                except Exception:
                    pass

                samples.append(sample)
                if sample_queue:
                    try:
                        sample_queue.put(sample)
                    except Exception:
                        pass
                time.sleep(0.5)
        finally:
            # signal children to stop
            stop_evt.set()
            # kill fallback external subprocess if present
            try:
                if fallback_proc:
                    if isinstance(fallback_proc, subprocess.Popen):
                        try:
                            fallback_proc.terminate()
                        except Exception:
                            pass
                    else:
                        try:
                            if fallback_proc.is_alive():
                                fallback_proc.terminate()
                        except Exception:
                            pass
            except Exception:
                pass
            try:
                if renderer_proc and renderer_proc.is_alive():
                    try:
                        renderer_proc.terminate()
                    except Exception:
                        pass
            except Exception:
                pass

        # post-process summary and CSV
        gpu_vals = [s["gpu_util"] for s in samples if isinstance(s.get("gpu_util"), (int, float))]
        temp_vals = [s["gpu_temp_c"] for s in samples if isinstance(s.get("gpu_temp_c"), (int, float))]
        summary = {"avg_gpu_util": (sum(gpu_vals) / len(gpu_vals)) if gpu_vals else None,
                   "avg_gpu_temp": (sum(temp_vals) / len(temp_vals)) if temp_vals else None,
                   "method": used_method}
        csv_path = REPORTS_DIR / f"gpu_stress_{_now_ts()}.csv"
        try:
            with open(csv_path, "w", encoding="utf-8") as fh:
                fh.write("ts,gpu_util,gpu_temp,source\n")
                for s in samples:
                    fh.write(f"{s['t']},{s.get('gpu_util')},{s.get('gpu_temp_c')},{s.get('gpu_source')}\n")
        except Exception:
            pass

        meta = {"samples": samples, "summary": summary, "csv": str(csv_path)}
        self._last_report = meta
        # reset stop_event for next runs
        self._stop_event.clear()
        logger.info("ReportService: run_gpu_stress_internal finished summary=%s", summary)
        return meta

    # backward compatibility wrapper
    def run_gpu_benchmark(self, *, seconds: int = 10, iterations: int = 1, stress_cmd: Optional[str] = None, sample_queue: Optional[mp.Queue] = None) -> Dict[str, Any]:
        if stress_cmd:
            # try to run external command (split if string)
            try:
                cmd = stress_cmd if isinstance(stress_cmd, list) else stress_cmd.split()
                proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self._active_processes.append(proc)
            except Exception:
                raise
            samples = []
            start = time.time()
            try:
                while (time.time() - start) < seconds and proc.poll() is None and not self._stop_event.is_set():
                    sample = {"t": time.time(), "gpu_util": None, "gpu_temp_c": None, "gpu_source": None}
                    try:
                        p = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"],
                                           capture_output=True, text=True, timeout=1.0)
                        if p.returncode == 0 and p.stdout:
                            line = p.stdout.strip().splitlines()[0].strip()
                            parts = [x.strip() for x in line.split(",")]
                            if parts and parts[0]:
                                try:
                                    sample["gpu_util"] = float(parts[0])
                                except Exception:
                                    sample["gpu_util"] = None
                            if len(parts) > 1 and parts[1]:
                                try:
                                    sample["gpu_temp_c"] = float(parts[1])
                                except Exception:
                                    sample["gpu_temp_c"] = None
                            sample["gpu_source"] = "nvidia-smi"
                    except Exception:
                        pass
                    samples.append(sample)
                    if sample_queue:
                        try:
                            sample_queue.put(sample)
                        except Exception:
                            pass
                    time.sleep(0.5)
            finally:
                try:
                    proc.terminate()
                except Exception:
                    pass
            csv_path = REPORTS_DIR / f"gpu_benchmark_{_now_ts()}.csv"
            try:
                with open(csv_path, "w", encoding="utf-8") as fh:
                    fh.write("ts,gpu_util,gpu_temp,source\n")
                    for s in samples:
                        fh.write(f"{s['t']},{s.get('gpu_util')},{s.get('gpu_temp_c')},{s.get('gpu_source')}\n")
            except Exception:
                pass
            meta = {"samples": samples, "csv": str(csv_path)}
            self._last_report = meta
            return meta
        else:
            return self.run_gpu_stress_internal(seconds=seconds, sample_queue=sample_queue)

    def last_report(self) -> Optional[Dict[str, Any]]:
        return self._last_report
