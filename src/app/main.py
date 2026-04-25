# main.py
# Robust elevation entrypoint that:
#  - preserves original argv (GetCommandLineW + CommandLineToArgvW)
#  - uses sys.executable (full path) as elevation target so venv is preserved
#  - uses ShellExecuteExW to get a process handle and waits briefly to detect immediate exits
#  - if elevated process dies almost immediately, continue running non-elevated and show messagebox
#  - otherwise exit original process (normal UAC flow)
#
# Replace your existing main.py with this content.

import sys
import os
import shlex
import logging
import ctypes
from ctypes import wintypes
import time

# Project logger fallback
try:
    from .core.logger import logger
except Exception:
    logger = logging.getLogger("system_optimizer")
    if not logger.handlers:
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s"))
        logger.addHandler(ch)
    logger.setLevel(logging.INFO)

def _is_windows() -> bool:
    return sys.platform.startswith("win")

def _is_elevated_windows() -> bool:
    if not _is_windows():
        return False
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        logger.exception("IsUserAnAdmin check failed")
        return False

def _get_original_argv_windows():
    """
    Return argv list as originally passed to the process (preserves quotes).
    Uses GetCommandLineW + CommandLineToArgvW.
    """
    try:
        kernel32 = ctypes.windll.kernel32
        shell32 = ctypes.windll.shell32

        kernel32.GetCommandLineW.restype = wintypes.LPWSTR
        cmdline = kernel32.GetCommandLineW()
        if not cmdline:
            return None

        argc = ctypes.c_int(0)
        shell32.CommandLineToArgvW.argtypes = [wintypes.LPWSTR, ctypes.POINTER(ctypes.c_int)]
        shell32.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
        argv_p = shell32.CommandLineToArgvW(cmdline, ctypes.byref(argc))
        if not argv_p:
            return None
        try:
            args = [argv_p[i] for i in range(argc.value)]
            return args
        finally:
            kernel32.LocalFree(argv_p)
    except Exception:
        logger.exception("Failed to read original argv via WinAPI")
        return None

def _shell_execute_ex_elevate(target: str, params: str):
    """
    Launch elevated using ShellExecuteExW and return process HANDLE on success or None on failure.
    """
    try:
        SEE_MASK_NOCLOSEPROCESS = 0x00000040

        class SHELLEXECUTEINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("fMask", wintypes.ULONG),
                ("hwnd", wintypes.HWND),
                ("lpVerb", wintypes.LPCWSTR),
                ("lpFile", wintypes.LPCWSTR),
                ("lpParameters", wintypes.LPCWSTR),
                ("lpDirectory", wintypes.LPCWSTR),
                ("nShow", ctypes.c_int),
                ("hInstApp", wintypes.HINSTANCE),
                ("lpIDList", wintypes.LPVOID),
                ("lpClass", wintypes.LPCWSTR),
                ("hkeyClass", wintypes.HKEY),
                ("dwHotKey", wintypes.DWORD),
                ("hIconOrMonitor", wintypes.HANDLE),
                ("hProcess", wintypes.HANDLE),
            ]

        ShellExecuteEx = ctypes.windll.shell32.ShellExecuteExW
        ShellExecuteEx.argtypes = [ctypes.POINTER(SHELLEXECUTEINFO)]
        ShellExecuteEx.restype = wintypes.BOOL

        sei = SHELLEXECUTEINFO()
        sei.cbSize = ctypes.sizeof(sei)
        sei.fMask = SEE_MASK_NOCLOSEPROCESS
        sei.hwnd = None
        sei.lpVerb = "runas"
        sei.lpFile = str(target)
        sei.lpParameters = str(params) if params else None
        sei.lpDirectory = None
        sei.nShow = 1  # SW_SHOWNORMAL

        ok = ShellExecuteEx(ctypes.byref(sei))
        if not ok:
            err = ctypes.GetLastError()
            logger.warning("ShellExecuteExW failed (BOOL=0). GetLastError=%s", err)
            return None
        if sei.hProcess:
            return int(sei.hProcess)
        return None
    except Exception:
        logger.exception("ShellExecuteExW attempt raised")
        return None

def _relaunch_elevated_and_maybe_exit():
    """
    Attempt an elevated relaunch that:
      - uses sys.executable as target
      - preserves original invocation (module or script args)
      - waits briefly to detect if elevated process dies immediately
      - only exit original if elevated process is still running (normal); otherwise continue
    """
    if not _is_windows():
        return

    if _is_elevated_windows():
        logger.info("Already elevated; continuing.")
        return

    # reconstruct original argv preserving quoting
    orig = _get_original_argv_windows()
    if orig:
        # orig[0] is the executable the OS used (may be 'python' or full path)
        # Use sys.executable to ensure venv python used
        target = sys.executable
        rest = orig[1:]
        # produce params string preserving quoting
        def quote_arg(a: str) -> str:
            if not a:
                return '""'
            if any(ch.isspace() for ch in a) or '"' in a:
                escaped = a.replace('"', '\\"')
                return f'"{escaped}"'
            return a
        params = " ".join(quote_arg(a) for a in rest)
    else:
        # fallback to sys.executable + sys.argv
        target = sys.executable
        params = " ".join([shlex.quote(a) for a in sys.argv[1:]])

    logger.info("Elevation relaunch target='%s' params='%s'", target, params)

    proc_handle = _shell_execute_ex_elevate(target, params)
    if proc_handle:
        # wait briefly to detect immediate exit (common when elevated process fails to start)
        try:
            kernel32 = ctypes.windll.kernel32
            INFINITE = 0xFFFFFFFF
            WAIT_TIMEOUT = 0x00000102
            # Wait up to 2000 ms for the process to become "active"; if it exits quickly, we'll see its exit code
            wait_ms = 2000
            ret = kernel32.WaitForSingleObject(proc_handle, wait_ms)
            STILL_ACTIVE = 259
            exit_code = wintypes.DWORD()
            got = kernel32.GetExitCodeProcess(proc_handle, ctypes.byref(exit_code))
            code = exit_code.value if got else None
            logger.info("WaitForSingleObject returned %s, GetExitCodeProcess -> %s", ret, code)
            # If process is still active (STILL_ACTIVE), we can safely exit the current instance
            if code == STILL_ACTIVE or (ret != 0 and ret == WAIT_TIMEOUT):
                logger.info("Elevated process still running; exiting original process.")
                try:
                    os._exit(0)
                except Exception:
                    os._exit(0)
            else:
                logger.warning("Elevated process exited immediately with exit code %s; continuing non-elevated instance.", code)
                # Let the current process continue so user can see logs / error messages
                try:
                    import tkinter as tk
                    from tkinter import messagebox
                    root = tk.Tk()
                    root.withdraw()
                    messagebox.showerror("Elevation failed", f"Elevated launch exited early (exit code {code}). Running without elevation so you can debug. Check logs.")
                    root.destroy()
                except Exception:
                    pass
                return
        except Exception:
            logger.exception("Error while waiting for elevated process; continuing non-elevated instance")
            return
    else:
        # ShellExecuteEx failed; try ShellExecuteW fallback (still using sys.executable)
        try:
            ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", str(target), str(params) if params else None, None, 1)
            ok = False
            try:
                ok = int(ret) > 32
            except Exception:
                ok = False
            logger.info("ShellExecuteW returned: %s -> ok=%s", ret, ok)
            if ok:
                # we can't get a handle from ShellExecuteW so assume elevated process will run; exit current
                try:
                    os._exit(0)
                except Exception:
                    os._exit(0)
            else:
                logger.info("ShellExecuteW failed or cancelled; continuing non-elevated instance.")
                try:
                    import tkinter as tk
                    from tkinter import messagebox
                    root = tk.Tk()
                    root.withdraw()
                    messagebox.showinfo("Administrator access", "App is running without administrator rights. Some features may be limited.")
                    root.destroy()
                except Exception:
                    pass
                return
        except Exception:
            logger.exception("ShellExecuteW fallback raised; continuing non-elevated")
            return

# Attempt elevation early (before importing GUI modules)
if _is_windows() and not _is_elevated_windows():
    _relaunch_elevated_and_maybe_exit()

# --- Normal app startup below ---
try:
    import customtkinter as ctk
    from .ui.app_shell import AppShell
except Exception as e:
    logger.exception("Failed to import GUI modules: %s", e)
    raise

def main():
    try:
        ctk.set_appearance_mode("dark")
    except Exception:
        pass

    app = ctk.CTk()
    app.title("System Optimizer")
    try:
        app.geometry("1200x700")
        app.resizable(False, False)
    except Exception:
        pass

    try:
        AppShell(app)
    except Exception as e:
        logger.exception("Failed to initialize AppShell: %s", e)
        raise

    try:
        app.mainloop()
    except Exception as e:
        logger.exception("Unhandled exception in mainloop: %s", e)
        raise

if __name__ == "__main__":
    main()
