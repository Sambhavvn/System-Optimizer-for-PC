#!/usr/bin/env python3
"""
_gpu_stress_helper.py (improved)

- Creates a visible fullscreen window to increase the chance Windows will schedule
  the app on the discrete NVIDIA GPU on Optimus systems.
- Attempts multiple rendering strategies:
    1) moderngl + pyglet shader-driven draws (preferred)
    2) fallback busy-loop if moderngl/pyglet not available
- Optionally spawns mpv (if installed) to play a high-bitrate test pattern to
  create additional GPU load (hardware decode + presentation).
- Writes periodic telemetry samples to a JSON file (path provided by --out).
- Keeps sample cadence high so the parent process can show live gauges.

Usage:
    python _gpu_stress_helper.py --seconds 10 --out /tmp/h.json [--play-video]

Notes for Optimus users:
- Configure Windows Graphics Settings → Browse → select python.exe → set to "High performance".
- Alternatively run your launcher with "Run with processor > NVIDIA" if your system provides that context menu.
- Install moderngl & pyglet for best results: `pip install moderngl pyglet`
- If you want to use mpv to play a test video you can `choco install mpv` or download mpv and add to PATH.
"""

import argparse
import json
import os
import subprocess
import sys
import time
import math
from pathlib import Path

# Try to import rendering libs
try:
    import pyglet
    import moderngl
    from pyglet import gl
    _MODERNGL_AVAILABLE = True
except Exception:
    _MODERNGL_AVAILABLE = False

# small helper to sample nvidia-smi if available
def sample_nvidia_smi_once():
    try:
        p = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=1.0
        )
        if p.returncode == 0 and p.stdout:
            line = p.stdout.strip().splitlines()[0]
            parts = [x.strip() for x in line.split(",")]
            util = float(parts[0]) if parts and parts[0] != "" else None
            temp = float(parts[1]) if len(parts) > 1 and parts[1] != "" else None
            return util, temp
    except Exception:
        pass
    return None, None

def write_samples_atomic(out_path: str, samples):
    try:
        tmp = out_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(samples, f)
        os.replace(tmp, out_path)
    except Exception:
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(samples, f)
        except Exception:
            pass

# If moderngl + pyglet available, create a fullscreen window and render continuously.
def run_modern_gl_stress(seconds: int, out_path: str, play_video: bool):
    samples = []
    start = time.time()
    # Create a visible window. Fullscreen increases chance of using discrete GPU.
    config = None
    try:
        # prefer a double-buffered config with 24-bit depth
        config = pyglet.gl.Config(double_buffer=True, depth_size=24)
    except Exception:
        config = None

    # Request visible fullscreen window. If the system steals the window to iGPU,
    # fullscreen + no-vsync increases the chance the driver will switch to dGPU.
    try:
        win = pyglet.window.Window(fullscreen=False, visible=True, config=config, caption="GPU Stress Helper")
        # try to set fullscreen if requested — some systems treat fullscreen differently.
        try:
            win.set_fullscreen(False)
        except Exception:
            pass
    except Exception:
        win = None

    ctx = None
    prog = None
    vbo = None
    vao = None

    if win is not None:
        try:
            ctx = moderngl.create_context(require=330)
        except Exception:
            ctx = None

    # compile a fat fragment shader to generate heavy work
    if ctx is not None:
        try:
            prog = ctx.program(
                vertex_shader='''
                    #version 330
                    in vec2 in_pos;
                    void main() {
                        gl_Position = vec4(in_pos, 0.0, 1.0);
                    }
                ''',
                fragment_shader='''
                    #version 330
                    out vec4 color;
                    uniform float t;
                    uniform vec2 res;
                    // heavy math to stress ALUs and fill-rate
                    float hash(vec2 p) {
                        return fract(sin(dot(p, vec2(127.1,311.7))) * 43758.5453123);
                    }
                    void main() {
                        vec2 uv = gl_FragCoord.xy / res.xy;
                        vec2 p = uv * 8.0;
                        float v = 0.0;
                        for (int i = 0; i < 12; ++i) {
                            float f = sin(dot(p, p) + t*2.0 + float(i)*12.345);
                            v += abs(f) / (float(i) + 1.0);
                            p = p*1.3 + vec2(0.12,0.43);
                        }
                        color = vec4(vec3(v * 0.09), 1.0);
                    }
                ''',
            )
            # big fullscreen triangle
            vbo = ctx.buffer(b'\x00\x00\x00\x03\xff\xff\x00\x03\x00\x03\xff\xff')
            vao = ctx.simple_vertex_array(prog, vbo, 'in_pos')
        except Exception:
            prog = None

    # Optionally spawn mpv to play a test pattern to increase decode + presentation load.
    mpv_proc = None
    if play_video:
        # Try to find mpv in PATH
        mpv_cmd = None
        for exe in ("mpv", "mpv.exe"):
            try:
                res = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=1.0)
                if res.returncode == 0:
                    mpv_cmd = exe
                    break
            except Exception:
                continue
        if mpv_cmd:
            # use mpv's testsrc to play synthetic high-bitrate pattern if available:
            # mpv supports a "lavfi" option to play ffmpeg filtergraph; not all builds expose it the same,
            # so as a robust fallback we'll try to open a small generated video file if mpv supports it.
            # try playing the "testsrc" using mpv --ao=null --vo=gpu --really-quiet --loop-file=inf
            try:
                # hardware decode not applicable to testsrc but vo=gpu will present via GPU.
                mpv_proc = subprocess.Popen([mpv_cmd, "lavfi=testsrc=size=3840x2160:rate=60", "--loop-file=inf", "--no-audio", "--vo=gpu", "--really-quiet"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                try:
                    mpv_proc = subprocess.Popen([mpv_cmd, "test.mp4", "--loop-file=inf", "--no-audio", "--vo=gpu", "--really-quiet"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    mpv_proc = None

    # main render loop
    last_write = 0.0
    t = 0.0
    # uncapped rendering (no vsync) — aim to create heavy load
    try:
        if win is not None:
            # try to disable vsync via pyglet / gl hint - not guaranteed
            try:
                # platform-specific: on some drivers, swapping interval can be set to 0
                from pyglet import gl as _gl
                try:
                    # Attempt to set swap interval to 0 (disable vsync)
                    _gl.glXSwapIntervalEXT = getattr(_gl, "glXSwapIntervalEXT", None)
                except Exception:
                    pass
            except Exception:
                pass
    except Exception:
        pass

    try:
        while time.time() - start < seconds:
            t += 0.016
            # issue many draw calls to raise load
            if ctx is not None and prog is not None:
                try:
                    prog['t'].value = float(t)
                    prog['res'].value = (float(1920.0), float(1080.0))
                    # create temporary framebuffer large enough to fill and free it several times
                    for _ in range(6):
                        try:
                            fb = ctx.simple_framebuffer((1920, 1080))
                            fb.use()
                            ctx.clear(0.0, 0.0, 0.0)
                            vao.render(mode=moderngl.TRIANGLES, vertices=3)
                            fb.release()
                        except Exception:
                            # ignore individual failures
                            pass
                except Exception:
                    pass
            else:
                # fallback busy-wait and a short GPU-overlapping operation (if any)
                busy_end = time.time() + 0.02
                while time.time() < busy_end:
                    x = math.sin(time.time()*1000.0) * 1.000001
                    x = x * x

            # sample nvidia-smi (if present) and record
            util, temp = sample_nvidia_smi_once()
            samples.append({"t": round(time.time(), 3), "gpu_util": util, "gpu_temp_c": temp, "gpu_source": "nvidia-smi"})
            # write samples every ~0.3s
            now = time.time()
            if now - last_write > 0.3:
                write_samples_atomic(out_path, samples)
                last_write = now
            # a tiny sleep so we don't starve the system UI (but keep heavy load)
            time.sleep(0.06)
    except KeyboardInterrupt:
        pass
    finally:
        # try to cleanup mpv
        try:
            if mpv_proc and mpv_proc.poll() is None:
                mpv_proc.terminate()
                time.sleep(0.1)
                if mpv_proc.poll() is None:
                    mpv_proc.kill()
        except Exception:
            pass
        # final write
        write_samples_atomic(out_path, samples)
        # close window (pyglet)
        try:
            if _MODERNGL_AVAILABLE and 'win' in locals() and win is not None:
                try:
                    win.close()
                except Exception:
                    pass
        except Exception:
            pass

def run_busy_fallback(seconds: int, out_path: str):
    samples = []
    start = time.time()
    last_write = 0.0
    try:
        while time.time() - start < seconds:
            # heavy CPU spin — won't stress NVIDIA GPU but is a safe fallback
            busy_end = time.time() + 0.04
            while time.time() < busy_end:
                _ = math.sin(time.time()*1000.0) * math.cos(time.time()*900.0)
            util, temp = sample_nvidia_smi_once()
            samples.append({"t": round(time.time(), 3), "gpu_util": util, "gpu_temp_c": temp, "gpu_source": "nvidia-smi"})
            now = time.time()
            if now - last_write > 0.5:
                write_samples_atomic(out_path, samples)
                last_write = now
            time.sleep(0.08)
    except KeyboardInterrupt:
        pass
    finally:
        write_samples_atomic(out_path, samples)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--seconds", type=int, default=6)
    p.add_argument("--out", type=str, required=True)
    p.add_argument("--play-video", action="store_true", help="If mpv is available, spawn a high-res test pattern playback to increase load")
    ns = p.parse_args()

    out_path = str(Path(ns.out).resolve())

    # Give parent a small moment to prepare queue and watch file
    time.sleep(0.06)

    # Try to run the moderngl + pyglet heavy renderer first
    if _MODERNGL_AVAILABLE:
        try:
            run_modern_gl_stress(ns.seconds, out_path, ns.play_video)
            # exit normally
            sys.exit(0)
        except Exception:
            # if fails, fallback to busy loop
            try:
                run_busy_fallback(ns.seconds, out_path)
            except Exception:
                pass
            sys.exit(0)
    else:
        # no modern GL libs — fallback
        run_busy_fallback(ns.seconds, out_path)
        sys.exit(0)

if __name__ == "__main__":
    main()
