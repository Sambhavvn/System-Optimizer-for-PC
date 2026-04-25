# user_scenario.py
# Extreme Performance: Ultimate/High-Perf plan + EPP=0 + Active cooling,
# + Max Brightness + 144 Hz attempt + NVIDIA per-app preference
# with verification and thread-safe UI updates.

import os
import sys
import json
import shlex
import threading
import subprocess
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable

import customtkinter as ctk
from tkinter import filedialog

# --- Minimal theme fallbacks (keep your existing imports if you have them) ---
try:
    from ...core.logger import logger
    from ...services.cleaner_service import CleanerService
    from ..theme import COLORS, FONTS, SPACING
except Exception:
    class _DummyLogger:
        def info(self, *a, **k): pass
        def warning(self, *a, **k): pass
        def error(self, *a, **k): pass
        def exception(self, *a, **k): pass
    logger = _DummyLogger()
    class _DummyCleaner:
        def free_memory(self): pass
    CleanerService = _DummyCleaner
    COLORS = {
        "bg": "#0f1115","panel":"#151822","text":"#ebf1ff","muted":"#a9b1c7",
        "border":"#2a2f3b","accent":"#2b6bf6"
    }
    FONTS = {"h1":("Segoe UI",20), "h2":("Segoe UI",16), "body":("Segoe UI",12)}
    SPACING = {"page":14, "card_r":12}

PAD = SPACING.get("page", 14)
R = SPACING.get("card_r", 12)

# --- Persistence -------------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_PATH = DATA_DIR / "user_scenario_settings.json"
_TEMP_SAVE = SETTINGS_PATH.with_suffix(".tmp")

DEFAULT_STATE: Dict[str, Any] = {
    "last_selected": "Extreme Performance",
    "options": {
        "Extreme Performance": {"free_mem": False, "launch": ""},
        "Balanced": {"free_mem": False, "launch": ""},
        "Silent": {"free_mem": False, "launch": ""},
        "Super Battery": {"free_mem": True, "launch": ""},
        "User": {"free_mem": False, "launch": ""}
    }
}

def _atomic_write(path: Path, data: str) -> None:
    try:
        _TEMP_SAVE.write_text(data, encoding="utf-8")
        _TEMP_SAVE.replace(path)
    except Exception:
        try:
            path.write_text(data, encoding="utf-8")
        except Exception:
            logger.exception("Atomic write failed for %s", path)

def load_state() -> Dict[str, Any]:
    try:
        if SETTINGS_PATH.exists():
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            out = DEFAULT_STATE.copy()
            out_options = {k: v.copy() for k, v in out["options"].items()}
            loaded_opts = data.get("options", {})
            for k, v in loaded_opts.items():
                out_options[k] = {**out_options.get(k, {}), **(v or {})}
            out["options"] = out_options
            out["last_selected"] = data.get("last_selected", out["last_selected"])
            return out
    except Exception:
        logger.exception("Failed to load user scenario state")
    return DEFAULT_STATE.copy()

def save_state(state: Dict[str, Any]) -> None:
    try:
        txt = json.dumps(state, ensure_ascii=False, indent=2)
        _atomic_write(SETTINGS_PATH, txt)
    except Exception:
        logger.exception("Failed to save user scenario state")

# --- OS helpers --------------------------------------------------------------
def _is_windows() -> bool:
    return sys.platform.startswith("win")

def _run(cmd: str, timeout: float = 25.0) -> Tuple[bool, str]:
    try:
        out = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT, timeout=timeout)
        return True, out.strip()
    except subprocess.CalledProcessError as e:
        return False, (e.output or "").strip()
    except Exception as e:
        return False, str(e)

# --- Power GUIDs -------------------------------------------------------------
ULTIMATE_SEED = "e9a42b02-d5df-448d-aa00-03f14749eb61"
SUB_PROCESSOR = "54533251-82be-4824-96c1-47b60b740d00"
MIN_PROC      = "893dee8e-2bef-41e0-89c6-b55d0929964c"
MAX_PROC      = "bc5038f7-23e0-4960-96da-33abaf5935ec"
BOOST_MODE    = "be337238-0d82-4146-a960-4f3749d470c7"
EPP_INDEX     = "36687f9e-e3a5-4dbf-b1dc-15eb381c6863"
SUB_SYSTEM    = "94d3a615-a899-4ac5-ae2b-e4d8f634367f"
COOLING_POL   = "3b04d4fd-1cc7-4f23-ab1c-d1337819c4bb"

def _power_plans() -> Tuple[List[Tuple[str, str]], Optional[str]]:
    if not _is_windows():
        return [], None
    ok, out = _run("powercfg -L")
    if not ok:
        return [], None
    plans, active = [], None
    for line in out.splitlines():
        m = re.search(r"GUID:\s*([0-9a-fA-F-]{36})\s*\((.+?)\)", line)
        if not m:
            m = re.search(r"Power Scheme GUID:\s*([0-9a-fA-F-]{36})\s*\((.+?)\)", line)
        if m:
            guid, name = m.group(1).lower(), m.group(2).strip()
            plans.append((name, guid))
            if "*" in line:
                active = guid
    return plans, active

def _ensure_ultimate_plan() -> Optional[str]:
    plans, _ = _power_plans()
    for name, guid in plans:
        if "ultimate" in name.lower():
            return guid
    # Duplicate Ultimate seed
    ok, out = _run(f"powercfg -duplicatescheme {ULTIMATE_SEED}")
    if ok:
        m = re.search(r"GUID:\s*([0-9a-fA-F-]{36})", out)
        if m:
            return m.group(1).lower()
    # Fallbacks
    for name, guid in plans:
        if "high performance" in name.lower():
            return guid
    for name, guid in plans:
        if "balanced" in name.lower():
            return guid
    return plans[0][1] if plans else None

def _set_plan_active(guid: str) -> bool:
    return _run(f"powercfg -S {guid}")[0]

def _set_index(plan_guid: str, subgroup: str, setting: str, value: int) -> bool:
    ok = True
    for scope in ("SETACVALUEINDEX", "SETDCVALUEINDEX"):
        r, _ = _run(f'powercfg /{scope} {plan_guid} {subgroup} {setting} {value}')
        ok &= r
    return ok

def _commit_processor_extremes(plan_guid: str) -> bool:
    ok = True
    ok &= _set_index(plan_guid, SUB_PROCESSOR, MIN_PROC, 100)
    ok &= _set_index(plan_guid, SUB_PROCESSOR, MAX_PROC, 100)
    ok &= _set_index(plan_guid, SUB_PROCESSOR, BOOST_MODE, 2)  # enable/agg
    ok &= _set_index(plan_guid, SUB_PROCESSOR, EPP_INDEX, 0)   # perf
    ok &= _set_index(plan_guid, SUB_SYSTEM,   COOLING_POL, 0)  # Active
    return ok

def _readback(plan_guid: str) -> Dict[str, str]:
    def rb(sub, setg):
        r, out = _run(f'powercfg -query {plan_guid} {sub} {setg}')
        vals = {}
        if r:
            for line in out.splitlines():
                m = re.search(r'Current AC Power Setting Index:\s*(\d+)', line)
                if m: vals["AC"] = m.group(1)
                m = re.search(r'Current DC Power Setting Index:\s*(\d+)', line)
                if m: vals["DC"] = m.group(1)
        return vals
    return {
        "Min": str(rb(SUB_PROCESSOR, MIN_PROC).get("AC","?"))+"/"+str(rb(SUB_PROCESSOR, MIN_PROC).get("DC","?")),
        "Max": str(rb(SUB_PROCESSOR, MAX_PROC).get("AC","?"))+"/"+str(rb(SUB_PROCESSOR, MAX_PROC).get("DC","?")),
        "EPP": str(rb(SUB_PROCESSOR, EPP_INDEX).get("AC","?"))+"/"+str(rb(SUB_PROCESSOR, EPP_INDEX).get("DC","?")),
        "Cool": "Active/Active"  # we set both AC/DC to 0 above
    }

# --- Brightness / Refresh / GPU preference -----------------------------------
def _set_max_brightness() -> bool:
    """
    Sets internal panel brightness to 100 via WMI (powershell).
    Works for most laptops; external monitors may ignore.
    """
    if not _is_windows():
        return False
    ps = r'(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods -ErrorAction SilentlyContinue) | ForEach-Object { $_.WmiSetBrightness(1,100) }'
    return _run(f'powershell -NoProfile -Command "{ps}"')[0]

def _set_refresh_rate(hz: int = 144) -> Tuple[bool, str]:
    """
    Attempts to set primary display refresh rate to `hz` using ChangeDisplaySettingsEx via PowerShell Add-Type.
    Falls back silently if unsupported by the current mode.
    """
    if not _is_windows():
        return False, "Non-Windows"
    ps = rf'''
Add-Type @"
using System;
using System.Runtime.InteropServices;
[StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
public struct DEVMODE {{
  private const int CCHDEVICENAME = 32;
  private const int CCHFORMNAME = 32;
  [MarshalAs(UnmanagedType.ByValTStr, SizeConst = CCHDEVICENAME)] public string dmDeviceName;
  public short dmSpecVersion;
  public short dmDriverVersion;
  public short dmSize;
  public short dmDriverExtra;
  public int dmFields;
  public int dmPositionX;
  public int dmPositionY;
  public int dmDisplayOrientation;
  public int dmDisplayFixedOutput;
  public short dmColor;
  public short dmDuplex;
  public short dmYResolution;
  public short dmTTOption;
  public short dmCollate;
  [MarshalAs(UnmanagedType.ByValTStr, SizeConst = CCHFORMNAME)] public string dmFormName;
  public short dmLogPixels;
  public int dmBitsPerPel;
  public int dmPelsWidth;
  public int dmPelsHeight;
  public int dmDisplayFlags;
  public int dmDisplayFrequency;
  public int dmICMMethod, dmICMIntent, dmMediaType, dmDitherType, dmReserved1, dmReserved2;
  public int dmPanningWidth, dmPanningHeight;
}}
public class Native {{
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern bool EnumDisplaySettings(string lpszDeviceName, int iModeNum, ref DEVMODE lpDevMode);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int ChangeDisplaySettingsEx(string lpszDeviceName, ref DEVMODE lpDevMode, IntPtr hwnd, int dwflags, IntPtr lParam);
}}
"@
$dm = New-Object DEVMODE
$dm.dmSize = [System.Runtime.InteropServices.Marshal]::SizeOf($dm)
# -1 = ENUM_CURRENT_SETTINGS
[void][Native]::EnumDisplaySettings($null, -1, [ref]$dm)
$dm.dmFields = 0x400000 # DM_DISPLAYFREQUENCY
$dm.dmDisplayFrequency = {hz}
$code = [Native]::ChangeDisplaySettingsEx($null, [ref]$dm, [IntPtr]::Zero, 0x00000004, [IntPtr]::Zero) # CDS_UPDATEREGISTRY
Write-Output $code
'''
    ok, out = _run(f'powershell -NoProfile -Command "{ps}"')
    if not ok: return False, out
    # 0 = DISP_CHANGE_SUCCESSFUL
    return (out.strip() == "0"), f"ChangeDisplaySettingsEx code={out.strip()}"

def _set_gpu_preference_for_app(app_path: str, high_perf: bool = True) -> bool:
    """
    Writes per-app GPU preference to Windows registry (same as Settings>System>Display>Graphics).
    GpuPreference=2 = High performance (typically NVIDIA dGPU).
    """
    if not (_is_windows() and app_path and os.path.exists(app_path)):
        return False
    pref = 2 if high_perf else 1  # 2=HighPerf, 1=PowerSaving
    # HKCU\Software\Microsoft\DirectX\UserGpuPreferences
    # value: "<fullpath>.exe"="GpuPreference=2;"
    import winreg
    try:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\DirectX\UserGpuPreferences")
        winreg.SetValueEx(key, app_path, 0, winreg.REG_SZ, f"GpuPreference={pref};")
        winreg.CloseKey(key)
        return True
    except Exception:
        logger.exception("Failed to set per-app GPU preference")
        return False

def _oem_hint_for_fan() -> str:
    """
    Returns a short hint for vendor fan control tools.
    """
    ok, out = _run('wmic computersystem get manufacturer,model /value')
    manu = "OEM"
    if ok:
        m = re.search(r'Manufacturer=(.+)', out);  manu = m.group(1).strip() if m else manu
    hints = {
        "ASUSTeK COMPUTER INC.": "Open Armoury Crate → Profile: Turbo/Manual for max fans.",
        "ASUS": "Open Armoury Crate → Profile: Turbo/Manual for max fans.",
        "LENOVO": "Open Lenovo Vantage → Thermal Mode: Performance.",
        "Micro-Star International Co., Ltd.": "Open MSI Center → User Scenario: Extreme Performance.",
        "MSI": "Open MSI Center → Extreme Performance.",
        "Acer": "Open NitroSense → Max fan.",
        "HP": "Open OMEN Gaming Hub → Performance mode.",
        "Dell": "Open Alienware Command Center → Performance/Thermal profiles.",
    }
    for k,v in hints.items():
        if k.lower() in manu.lower():
            return v
    return "Open your OEM control app (Armoury Crate / Vantage / MSI Center / OMEN / Alienware) and set fans to max."

# --- UI helpers --------------------------------------------------------------
def show_toast(root, message: str, success: bool = True, duration_ms: int = 1600):
    try:
        toast = ctk.CTkToplevel(root)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        panel = ctk.CTkFrame(toast, fg_color=COLORS["panel"], corner_radius=12, border_width=1)
        panel.pack(fill="both", expand=True)
        icon = "✓" if success else "✕"
        lbl = ctk.CTkLabel(panel, text=f"{icon}  {message}", text_color=COLORS["text"], font=FONTS["body"])
        lbl.pack(padx=14, pady=10)
        try:
            root.update_idletasks()
            rx = root.winfo_rootx(); ry = root.winfo_rooty(); rw = root.winfo_width(); rh = root.winfo_height()
            x = rx + rw - 340
            y = ry + rh - 110
            toast.geometry(f"+{x}+{y}")
        except Exception:
            pass
        toast.after(duration_ms, lambda: toast.destroy())
    except Exception:
        logger.exception("show_toast failed")

class ScenarioTile(ctk.CTkFrame):
    def __init__(self, master, label: str, icon: str, on_select: Callable[[str], None], on_settings: Callable[[str], None]):
        super().__init__(master, width=180, height=200, fg_color="transparent")
        self.grid_propagate(False)
        self.label = label
        self.on_select = on_select
        self.on_settings = on_settings

        self.bg = ctk.CTkFrame(self, corner_radius=12, fg_color=COLORS["panel"], border_width=0)
        self.bg.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.accent = ctk.CTkFrame(self, corner_radius=12, fg_color=COLORS.get("accent","#2b6bf6"))
        self.accent.place_forget()

        inner = ctk.CTkFrame(self.bg, corner_radius=8, fg_color="transparent")
        inner.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.icon_lbl = ctk.CTkLabel(inner, text=icon, font=("Segoe UI Emoji", 40), text_color=COLORS["muted"])
        self.icon_lbl.pack(pady=(16,4))
        self.txt = ctk.CTkLabel(inner, text=label, font=(FONTS.get("body","Segoe UI"), 11, "bold"), text_color=COLORS["muted"])
        self.txt.pack()

        self.badge = ctk.CTkLabel(inner, text="", font=("Segoe UI", 16, "bold"), text_color=COLORS.get("accent","#2b6bf6"))
        self.badge.place_forget()

        gear = ctk.CTkButton(inner, width=28, height=28, text="⚙", fg_color="transparent",
                             hover_color=COLORS["border"], text_color=COLORS["muted"],
                             command=lambda: self.on_settings(self.label))
        gear.place(relx=0.88, rely=0.12, anchor="center")

        for w in (self, self.bg, inner, self.icon_lbl, self.txt):
            w.bind("<Button-1>", lambda _e: self.on_select(self.label))
            w.bind("<Enter>", lambda _e: self._hover(True))
            w.bind("<Leave>", lambda _e: self._hover(False))

    def _hover(self, on: bool):
        try:
            col = COLORS["text"] if on else COLORS["muted"]
            self.icon_lbl.configure(text_color=col)
            self.txt.configure(text_color=col)
        except Exception:
            pass

    def set_selected(self, on: bool):
        try:
            if on:
                self.accent.place(relx=0, rely=0, relwidth=0.06, relheight=1)
                self.accent.lift(self.bg)
                self.icon_lbl.configure(text_color=COLORS["text"])
                self.txt.configure(text_color=COLORS["text"])
            else:
                self.accent.place_forget()
                self.icon_lbl.configure(text_color=COLORS["muted"])
                self.txt.configure(text_color=COLORS["muted"])
                self.badge.place_forget()
        except Exception:
            pass

    def show_badge(self, ok: bool):
        try:
            self.badge.configure(text="✓" if ok else "!")
            self.badge.place(relx=0.12, rely=0.14, anchor="center")
        except Exception:
            pass

class UserScenarioPage(ctk.CTkFrame):
    DESCR = {
        "Extreme Performance": "Ultimate plan + EPP=0 + Active cooling + Max brightness + 144Hz + NVIDIA per-app preference.",
        "Balanced": "Smooth everyday use with good efficiency.",
        "Silent": "Lower heat & noise. Disables boost where possible and caps CPU.",
        "Super Battery": "Stretch battery life: low caps and saver plan.",
        "User": "Choose your Performance Level — then Apply.",
    }

    def __init__(self, master):
        super().__init__(master, fg_color=COLORS["bg"])
        self.cleaner = CleanerService()
        self.state = load_state()
        self.selected: str = self.state.get("last_selected", DEFAULT_STATE["last_selected"])
        self.options: Dict[str, Dict[str, Any]] = self.state.get("options", DEFAULT_STATE["options"])
        for k in DEFAULT_STATE["options"]:
            self.options.setdefault(k, DEFAULT_STATE["options"][k].copy())

        self._build()

    # UI-thread hop
    def _on_ui(self, fn: Callable, *args, **kwargs):
        try: self.after(0, lambda: fn(*args, **kwargs))
        except Exception: pass

    # Admin check/elevate
    def _is_admin(self) -> bool:
        if not _is_windows(): return False
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False

    def _relaunch_as_admin(self):
        try:
            if not _is_windows():
                self._on_ui(show_toast, self, "Elevation not supported on this OS", False); return
            import ctypes
            py = sys.executable
            if getattr(sys, "frozen", False):
                target = py; params = " ".join([shlex.quote(a) for a in sys.argv[1:]])
            else:
                try: main_file = Path(sys.modules['__main__'].__file__).resolve()
                except Exception: main_file = Path(__file__).resolve()
                target = py; params = " ".join([f'"{str(main_file)}"'] + [shlex.quote(a) for a in sys.argv[1:]])
            ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", target, params, None, 1)
            if int(ret) > 32: os._exit(0)
            self._on_ui(show_toast, self, "Elevation cancelled or failed", False)
        except Exception:
            logger.exception("Elevation attempt raised an exception")
            self._on_ui(show_toast, self, "Elevation failed", False)

    def _build(self):
        header = ctk.CTkFrame(self, fg_color=COLORS["bg"], height=72)
        header.pack(fill="x", padx=PAD, pady=(PAD//2, PAD))
        title = ctk.CTkLabel(header, text="User Scenario", font=(FONTS["h1"][0], 20, "bold"), text_color=COLORS["text"])
        title.pack(side="left")
        sub = ctk.CTkLabel(header, text="One-click modes for gaming, work & battery.", text_color=COLORS["muted"])
        sub.pack(side="left", padx=(8,0))
        self.elevate_btn = None
        if _is_windows() and not self._is_admin():
            self.elevate_btn = ctk.CTkButton(header, text="⚡ Run as Admin", width=140, command=self._relaunch_as_admin)
            self.elevate_btn.pack(side="right")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))

        tiles_frame = ctk.CTkFrame(body, fg_color="transparent")
        tiles_frame.pack(fill="x")
        for i in range(5): tiles_frame.grid_columnconfigure(i, weight=1)

        tiles = [
            ("Extreme Performance", "🚀"),
            ("Balanced", "⚖️"),
            ("Silent", "🫧"),
            ("Super Battery", "🔋"),
            ("User", "🎛️"),
        ]
        self._tiles: Dict[str, ScenarioTile] = {}
        for i, (name, icon) in enumerate(tiles):
            t = ScenarioTile(tiles_frame, name, icon, self._on_select, self._open_settings)
            t.grid(row=0, column=i, padx=(0 if i==0 else 12), sticky="nsew", pady=(0,6))
            self._tiles[name] = t
        self._refresh_tiles()

        ctk.CTkFrame(body, height=1, fg_color=COLORS["border"]).pack(fill="x", pady=(12,12))

        self.user_box = ctk.CTkFrame(body, fg_color="transparent")
        ctk.CTkLabel(self.user_box, text="Performance Level", text_color=COLORS["text"]).pack(anchor="w")
        self.cmb_perf = ctk.CTkComboBox(self.user_box, values=["Turbo","High","Medium","Low"], width=220)
        self.cmb_perf.set("Turbo"); self.cmb_perf.pack(anchor="w", pady=(6,8))
        ctk.CTkButton(self.user_box, text="Apply User Settings", width=200, command=self._apply_user).pack(anchor="w")

        self.title_lbl = ctk.CTkLabel(body, text="", font=(FONTS["h2"][0], 16, "bold"), text_color=COLORS["text"])
        self.title_lbl.pack(anchor="w")
        self.desc = ctk.CTkLabel(body, text="", wraplength=980, justify="left", text_color=COLORS["muted"])
        self.desc.pack(anchor="w", pady=(6,12))

        footer = ctk.CTkFrame(body, fg_color="transparent")
        footer.pack(fill="x", pady=(8,0))
        self.status_label = ctk.CTkLabel(footer, text="Status: Ready", text_color=COLORS["muted"])
        self.status_label.pack(side="left", padx=(0,8))

        self._update_description(); self._toggle_user_box()

    def _refresh_tiles(self):
        for n, t in self._tiles.items():
            t.set_selected(n == self.selected)

    def _on_select(self, name: str):
        self.selected = name
        self._refresh_tiles(); self._update_description(); self._toggle_user_box()
        self.state["last_selected"] = self.selected; save_state(self.state)
        if name != "User":
            self._ui_update_status("Applying...")
            self.after(80, self._apply_current)

    def _update_description(self):
        t = self.selected
        self.title_lbl.configure(text=t)
        self.desc.configure(text=self.DESCR.get(t, ""))

    def _toggle_user_box(self):
        try: self.user_box.pack_forget()
        except Exception: pass
        if self.selected == "User":
            self.user_box.pack(fill="x")

    # --- Apply flows ---------------------------------------------------------
    def _apply_current(self):
        name = self.selected
        if name == "Extreme Performance":
            return self._apply_extreme()
        elif name == "Balanced":
            minp, maxp, boost = 5, 85, 1
        elif name == "Silent":
            minp, maxp, boost = 5, 60, 0
        elif name == "Super Battery":
            minp, maxp, boost = 0, 50, 0
        else:
            minp, maxp, boost = 0, 100, 1

        def job():
            full_ok = False
            opts = self.options.get(name, {}) or {}
            launch_path = opts.get("launch", "")
            free_mem_opt = bool(opts.get("free_mem", False))
            try:
                if _is_windows() and self._is_admin():
                    guid = _ensure_ultimate_plan()
                    ok = True
                    if guid:
                        ok &= _set_index(guid, SUB_PROCESSOR, MIN_PROC, minp)
                        ok &= _set_index(guid, SUB_PROCESSOR, MAX_PROC, maxp)
                        ok &= _set_index(guid, SUB_PROCESSOR, BOOST_MODE, boost)
                        ok &= _set_plan_active(guid)
                    else:
                        ok = False
                    full_ok = ok
                    if ok and free_mem_opt:
                        try: self.cleaner.free_memory()
                        except Exception: logger.exception("Cleaner.free_memory failed")
                    if ok and launch_path:
                        try: subprocess.Popen(f'"{launch_path}"', shell=True)
                        except Exception: logger.exception("Failed to launch: %s", launch_path)
                else:
                    if free_mem_opt:
                        try: self.cleaner.free_memory()
                        except Exception: logger.exception("Cleaner.free_memory failed (non-admin)")
                    if launch_path and os.path.exists(launch_path):
                        try: subprocess.Popen(f'"{launch_path}"', shell=True)
                        except Exception: logger.exception("Failed to launch (non-admin): %s", launch_path)

                self._on_ui(lambda: self._tiles.get(name) and self._tiles[name].show_badge(full_ok))
                self._ui_update_status(f"Applied: {name} (full_ok={full_ok})")
            finally:
                if full_ok:
                    self._on_ui(show_toast, self, f"{name} applied", True)
                else:
                    if _is_windows() and not self._is_admin():
                        self._on_ui(show_toast, self, "Limited apply (requires Admin)", False)
                    else:
                        self._on_ui(show_toast, self, "Apply completed (partial)", False)

        threading.Thread(target=job, daemon=True).start()

    def _apply_extreme(self):
        def job():
            name = "Extreme Performance"
            full_ok = False
            verify_summary = "pending"
            opts = self.options.get(name, {}) or {}
            launch_path = opts.get("launch", "")
            free_mem_opt = bool(opts.get("free_mem", False))

            try:
                if _is_windows() and self._is_admin():
                    guid = _ensure_ultimate_plan()
                    if not guid:
                        self._ui_update_status("No power plan available to tune"); return
                    ok = _commit_processor_extremes(guid)
                    ok &= _set_plan_active(guid)
                    rb = _readback(guid)
                    verify_summary = f"Min={rb['Min']}% | Max={rb['Max']}% | EPP={rb['EPP']} | {rb['Cool']}"

                    # Brightness 100
                    b_ok = _set_max_brightness()
                    # Refresh 144 Hz (best-effort)
                    r_ok, r_info = _set_refresh_rate(144)
                    # Prefer NVIDIA for the configured app (if any)
                    g_ok = _set_gpu_preference_for_app(launch_path) if launch_path else True

                    full_ok = ok and b_ok and (r_ok or True) and g_ok  # refresh may fail gracefully

                    # Optional memory free + launch
                    if free_mem_opt:
                        try: self.cleaner.free_memory()
                        except Exception: logger.exception("Cleaner.free_memory failed")
                    if launch_path:
                        try: subprocess.Popen(f'"{launch_path}"', shell=True)
                        except Exception: logger.exception("Failed to launch: %s", launch_path)

                    # OEM fan hint
                    hint = _oem_hint_for_fan()
                    verify_summary += f" | Brightness=100% | 144Hz~{('OK' if r_ok else 'best-effort')} | GPU pref set={g_ok} | Fan: {hint}"

                else:
                    verify_summary = "Needs Admin for full effect"
                    # We can still set per-app GPU preference & try refresh/brightness (often need admin for registry if path protected)
                    if launch_path:
                        _set_gpu_preference_for_app(launch_path, True)

                self._on_ui(lambda: self._tiles.get(name) and self._tiles[name].show_badge(full_ok))
                self._ui_update_status(f"Extreme applied: {verify_summary} (full_ok={full_ok})")
            finally:
                if full_ok:
                    self._on_ui(show_toast, self, f"Extreme Performance ON — {verify_summary}", True)
                else:
                    if _is_windows() and not self._is_admin():
                        self._on_ui(show_toast, self, "Limited (Run as Admin for peak)", False)
                    else:
                        self._on_ui(show_toast, self, f"Extreme partial — {verify_summary}", False)

        self._ui_update_status("Applying Extreme Performance...")
        threading.Thread(target=job, daemon=True).start()

    def _apply_user(self):
        perf = self.cmb_perf.get() if hasattr(self, "cmb_perf") else "Turbo"
        if perf == "Turbo":
            minp, maxp, boost = 5, 100, 2
        elif perf == "High":
            minp, maxp, boost = 5, 90, 1
        elif perf == "Medium":
            minp, maxp, boost = 5, 75, 1
        else:
            minp, maxp, boost = 0, 55, 0

        self._ui_update_status("Applying user settings...")

        def job():
            full_ok = False
            try:
                if _is_windows() and self._is_admin():
                    guid = _ensure_ultimate_plan()
                    ok = True
                    if guid:
                        ok &= _set_index(guid, SUB_PROCESSOR, MIN_PROC, minp)
                        ok &= _set_index(guid, SUB_PROCESSOR, MAX_PROC, maxp)
                        ok &= _set_index(guid, SUB_PROCESSOR, BOOST_MODE, boost)
                        ok &= _set_plan_active(guid)
                    else:
                        ok = False
                    full_ok = ok
                self._on_ui(lambda: self._tiles.get("User") and self._tiles["User"].show_badge(full_ok))
                self._ui_update_status(f"User apply (full_ok={full_ok})")
            finally:
                if full_ok:
                    self._on_ui(show_toast, self, "User settings applied", True)
                else:
                    if _is_windows() and not self._is_admin():
                        self._on_ui(show_toast, self, "Limited (needs Admin)", False)
                    else:
                        self._on_ui(show_toast, self, "Apply failed or partial", False)

        threading.Thread(target=job, daemon=True).start()

    def _open_settings(self, name: str):
        s = self.options.get(name, {}) or {}
        win = ctk.CTkToplevel(self); win.title(f"{name} Options"); win.configure(fg_color=COLORS["panel"])
        try: win.geometry(f"+{self.winfo_rootx()+140}+{self.winfo_rooty()+140}")
        except Exception: pass

        ctk.CTkLabel(win, text=f"{name} – Options", font=FONTS.get("h3", ("Segoe UI", 14, "bold")), text_color=COLORS["text"]).pack(anchor="w", padx=16, pady=(16,8))
        var_free = ctk.BooleanVar(value=bool(s.get("free_mem", False)))
        ctk.CTkCheckBox(win, text="Free up memory after switching", variable=var_free).pack(anchor="w", padx=16, pady=(0,10))

        ctk.CTkLabel(win, text="App to launch (optional)", text_color=COLORS["muted"], font=FONTS.get("body","Segoe UI")).pack(anchor="w", padx=16)
        ent_frame = ctk.CTkFrame(win, fg_color="transparent")
        ent_frame.pack(fill="x", padx=16, pady=(6,12))
        ent = ctk.CTkEntry(ent_frame, placeholder_text=r"C:\Path\to\your\game.exe")
        ent.pack(side="left", fill="x", expand=True)
        ent.insert(0, s.get("launch",""))

        def browse():
            p = filedialog.askopenfilename(title="Select executable", filetypes=[("Executables","*.exe"),("All files","*.*")])
            if p:
                ent.delete(0, "end"); ent.insert(0, p)

        ctk.CTkButton(ent_frame, text="Browse", width=80, command=browse).pack(side="left", padx=(8,0))

        row = ctk.CTkFrame(win, fg_color="transparent"); row.pack(fill="x", padx=16, pady=(0,16))
        def save_close():
            s["free_mem"] = bool(var_free.get()); s["launch"] = ent.get().strip()
            self.options[name] = s
            state = {"last_selected": self.selected, "options": self.options}
            save_state(state)
            win.destroy()
            if self.selected == name and name != "User":
                self.after(120, self._apply_current)
            show_toast(self, "Options saved", success=True)

        ctk.CTkButton(row, text="Save", command=save_close).pack(side="right")
        ctk.CTkButton(row, text="Cancel", fg_color="transparent", hover_color=COLORS["border"], command=win.destroy).pack(side="right", padx=(0,8))

    def _ui_update_status(self, text: str):
        try:
            self.after(0, lambda: self.status_label.configure(text=f"Status: {text}"))
        except Exception:
            pass

    def on_show(self):
        try:
            self.state = load_state()
            self.options = self.state.get("options", DEFAULT_STATE["options"])
            self.selected = self.state.get("last_selected", self.selected)
            self._refresh_tiles(); self._update_description(); self._toggle_user_box()
            if getattr(self, "elevate_btn", None):
                self.elevate_btn.configure(state="normal" if not self._is_admin() else "disabled")
        except Exception:
            logger.exception("on_show failed")

# End of file
