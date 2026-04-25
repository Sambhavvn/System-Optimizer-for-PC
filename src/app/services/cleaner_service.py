from __future__ import annotations
import os, glob, shutil, tempfile, gc, ctypes
from dataclasses import dataclass
import psutil

@dataclass
class CleanResult:
    files_deleted: int
    files_skipped: int
    bytes_freed: int
    recycle_bin_bytes: int

@dataclass
class MemResult:
    processes_trimmed: int
    skipped: int
    freed_mb: float

def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

class CleanerService:
    """
    Safe cleaner targets:
      • %TEMP%
      • LocalAppData\\Temp
      • Recycle Bin
      • If admin: C:\\Windows\\Temp and C:\\Windows\\Prefetch
    """

    def clean_temp(self) -> CleanResult:
        user_temp = tempfile.gettempdir()
        local_temp = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Temp")
        targets = [p for p in [user_temp, local_temp] if p and os.path.exists(p)]

        if _is_admin():
            for extra in (r"C:\Windows\Temp", r"C:\Windows\Prefetch"):
                if os.path.exists(extra):
                    targets.append(extra)

        files_deleted = 0
        files_skipped = 0
        bytes_freed = 0

        for root in targets:
            for path in glob.glob(os.path.join(root, "*")):
                try:
                    if os.path.isfile(path) or os.path.islink(path):
                        try:
                            size = os.path.getsize(path)
                        except Exception:
                            size = 0
                        os.unlink(path)
                        bytes_freed += size; files_deleted += 1
                    elif os.path.isdir(path):
                        size = 0
                        for dp, _, fnames in os.walk(path):
                            for f in fnames:
                                fp = os.path.join(dp, f)
                                try:
                                    size += os.path.getsize(fp)
                                except Exception:
                                    pass
                        shutil.rmtree(path, ignore_errors=True)
                        bytes_freed += size; files_deleted += 1
                except (OSError, PermissionError):
                    files_skipped += 1

        rb_freed = self._empty_recycle_bin()
        gc.collect()
        return CleanResult(files_deleted, files_skipped, bytes_freed, rb_freed)

    def _empty_recycle_bin(self) -> int:
        try:
            before = psutil.disk_usage("C:\\").free
            SHERB_NOCONFIRMATION = 0x1
            SHERB_NOPROGRESSUI  = 0x2
            SHERB_NOSOUND       = 0x4
            ctypes.windll.shell32.SHEmptyRecycleBinW(
                None, None, SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND
            )
            after = psutil.disk_usage("C:\\").free
            return max(0, int(after - before))
        except Exception:
            return 0

    def free_memory(self) -> MemResult:
        before = psutil.virtual_memory().available
        trimmed = 0; skipped = 0
        PROCESS_SET_QUOTA = 0x0100
        PROCESS_QUERY_INFORMATION = 0x0400
        for p in psutil.process_iter(["pid", "name"]):
            try:
                h = ctypes.windll.kernel32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_QUERY_INFORMATION, False, int(p.pid))
                if h:
                    try:
                        ctypes.windll.psapi.EmptyWorkingSet(h)
                        trimmed += 1
                    finally:
                        ctypes.windll.kernel32.CloseHandle(h)
            except Exception:
                skipped += 1
        gc.collect()
        after = psutil.virtual_memory().available
        freed_mb = max(0.0, (after - before)/1048576)
        return MemResult(trimmed, skipped, freed_mb)
