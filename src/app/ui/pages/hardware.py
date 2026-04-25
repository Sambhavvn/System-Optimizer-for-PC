import customtkinter as ctk
import time, threading, psutil
from ..theme import COLORS, FONTS, SPACING
from ...core.collector import get_collector, restart_collector
from ...services.cleaner_service import CleanerService
from ..widgets.gauge import Gauge

PAD = SPACING["page"]
R   = SPACING["card_r"]

def Card(master, **kwargs):
    return ctk.CTkFrame(master, fg_color=COLORS["panel"], corner_radius=R, **kwargs)

def HRule(master):
    return ctk.CTkFrame(master, height=1, fg_color=COLORS["border"])

def make_bar(parent, height=SPACING["bar_h"]):
    return ctk.CTkProgressBar(
        parent,
        height=height,
        corner_radius=height//2,
        fg_color=COLORS["bar_track"],
        progress_color=COLORS["bar_fill"],
        mode="determinate",
    )

class HardwarePage(ctk.CTkFrame):
    """Hardware dashboard with live gauges, heartbeat, and on-card actions."""
    def __init__(self, master):
        super().__init__(master, fg_color=COLORS["bg"])
        self.collector = get_collector()
        self.cleaner = CleanerService()
        self._last_ts = 0.0
        self._build()
        self.after(100, self._tick)  # start quickly

    # ---------- layout ----------
    def _build(self):
        left  = ctk.CTkFrame(self, fg_color=COLORS["bg"])
        right = ctk.CTkFrame(self, fg_color=COLORS["bg"], width=560)
        left.pack(side="left", fill="both", expand=True, padx=(PAD, PAD), pady=(PAD, PAD))
        right.pack(side="right", fill="both", padx=(0, PAD), pady=(PAD, PAD))
        right.pack_propagate(False)

        # Gauges row
        gauges = ctk.CTkFrame(left, fg_color=COLORS["bg"])
        gauges.pack(fill="x", pady=(0, SPACING["gap"]))

        cpu_card = Card(gauges); cpu_card.pack(side="left", padx=(0, SPACING["gap"]))
        ctk.CTkLabel(cpu_card, text="CPU", font=FONTS["h2"], text_color=COLORS["text"]).pack(anchor="w", padx=SPACING["pad"], pady=(SPACING["pad"], 8))
        self.cpu_g = Gauge(cpu_card, size=240, caption="Usage"); self.cpu_g.pack(padx=SPACING["pad"], pady=(0, SPACING["pad"]))

        gpu_card = Card(gauges); gpu_card.pack(side="left", padx=(SPACING["gap"], 0))
        ctk.CTkLabel(gpu_card, text="GPU", font=FONTS["h2"], text_color=COLORS["text"]).pack(anchor="w", padx=SPACING["pad"], pady=(SPACING["pad"], 8))
        self.gpu_g = Gauge(gpu_card, size=240, caption="Usage"); self.gpu_g.pack(padx=SPACING["pad"], pady=(0, SPACING["pad"]))

        # Disk card
        disk = Card(left); disk.pack(fill="x", pady=(0, SPACING["gap"]))
        header = ctk.CTkFrame(disk, fg_color="transparent"); header.pack(fill="x", padx=SPACING["pad"], pady=(SPACING["pad"], 0))
        ctk.CTkLabel(header, text="Disk", font=FONTS["h2"], text_color=COLORS["text"]).pack(side="left")
        self.disk_pct = ctk.CTkLabel(header, text="0%", font=FONTS["h2"], text_color=COLORS["text"]); self.disk_pct.pack(side="right")

        self.disk_bar = make_bar(disk, height=16); self.disk_bar.pack(fill="x", padx=SPACING["pad"], pady=(10, 6)); self.disk_bar.set(0.02)
        self.disk_line = ctk.CTkLabel(disk, text="—", text_color=COLORS["muted"], font=FONTS["body"]); self.disk_line.pack(anchor="w", padx=SPACING["pad"], pady=(0, 4))
        self.disk_io = ctk.CTkLabel(disk, text="Read 0.0 MB/s • Write 0.0 MB/s", text_color=COLORS["muted"], font=FONTS["body"]); self.disk_io.pack(anchor="w", padx=SPACING["pad"], pady=(0, 10))
        self.btn_disk = ctk.CTkButton(disk, text="Clean up disk", command=self._on_clean_disk); self.btn_disk.pack(anchor="w", padx=SPACING["pad"], pady=(0, SPACING["pad"]))

        # Memory card
        mem = Card(left); mem.pack(fill="x")
        header2 = ctk.CTkFrame(mem, fg_color="transparent"); header2.pack(fill="x", padx=SPACING["pad"], pady=(SPACING["pad"], 0))
        ctk.CTkLabel(header2, text="Memory", font=FONTS["h2"], text_color=COLORS["text"]).pack(side="left")
        self.mem_pct = ctk.CTkLabel(header2, text="0%", font=FONTS["h2"], text_color=COLORS["text"]); self.mem_pct.pack(side="right")

        self.mem_bar = make_bar(mem, height=18); self.mem_bar.pack(fill="x", padx=SPACING["pad"], pady=(10, 6)); self.mem_bar.set(0.05)
        self.mem_line = ctk.CTkLabel(mem, text="—", text_color=COLORS["muted"], font=FONTS["body"]); self.mem_line.pack(anchor="w", padx=SPACING["pad"], pady=(0, 10))
        self.btn_mem = ctk.CTkButton(mem, text="Free up memory", command=self._on_free_mem); self.btn_mem.pack(anchor="w", padx=SPACING["pad"], pady=(0, SPACING["pad"]))

        # RIGHT details + heartbeat
        info = Card(right); info.pack(fill="both", expand=True)
        info.grid_columnconfigure(0, weight=1); info.grid_columnconfigure(1, weight=1)

        hb = ctk.CTkFrame(info, fg_color="transparent")
        hb.grid(row=0, column=0, columnspan=2, sticky="ew", padx=SPACING["pad"], pady=(SPACING["pad"], 6))
        ctk.CTkLabel(hb, text="Details", font=FONTS["h2"], text_color=COLORS["text"]).pack(side="left")
        self.last_update = ctk.CTkLabel(hb, text="Last update —:—:—", font=FONTS["body"], text_color=COLORS["muted"]); self.last_update.pack(side="right")

        HRule(info).grid(row=1, column=0, columnspan=2, sticky="ew", padx=SPACING["pad"])

        r = 2
        r = self._row(info, r, "GPU Name");        self.gpu_name = self._val(info, r); r += 1
        r = self._row(info, r, "GPU Clock");       self.gpu_clk  = self._val(info, r); r += 1
        r = self._row(info, r, "VRAM Clock");      self.vram_clk = self._val(info, r); r += 1
        r = self._row(info, r, "GPU Temperature"); self.gpu_temp = self._val(info, r); r += 1

        HRule(info).grid(row=r, column=0, columnspan=2, sticky="ew", padx=SPACING["pad"]); r += 1

        r = self._row(info, r, "CPU Name");        self.cpu_name = self._val(info, r); r += 1
        r = self._row(info, r, "CPU Temperature"); self.cpu_temp = self._val(info, r); r += 1

        HRule(info).grid(row=r, column=0, columnspan=2, sticky="ew", padx=SPACING["pad"]); r += 1

        r = self._row(info, r, "RAM Total");       self.ram_total = self._val(info, r); r += 1

        HRule(info).grid(row=r, column=0, columnspan=2, sticky="ew", padx=SPACING["pad"]); r += 1

        ctk.CTkLabel(info, text="Drives", font=FONTS["h3"], text_color=COLORS["text"]).grid(row=r, column=0, sticky="w", padx=SPACING["pad"], pady=(10, 4))
        self.drives_frame = ctk.CTkFrame(info, fg_color="transparent"); self.drives_frame.grid(row=r, column=1, sticky="ew", padx=(8, SPACING["pad"]), pady=(10, SPACING["pad"]))

    def _row(self, parent, r, label):
        ctk.CTkLabel(parent, text=label, text_color=COLORS["muted"], font=FONTS["body"]).grid(row=r, column=0, sticky="w", padx=(SPACING["pad"], 8), pady=(8, 8))
        return r

    def _val(self, parent, r):
        w = ctk.CTkLabel(parent, text="—", text_color=COLORS["bar_fill"], font=FONTS["bold"])
        w.grid(row=r, column=1, sticky="e", padx=(8, SPACING["pad"]), pady=(8, 8))
        return w

    # ---------- actions ----------
    def _on_clean_disk(self):
        def job():
            self.btn_disk.configure(state="disabled", text="Cleaning…")
            try:
                res = self.cleaner.clean_temp()
                freed = (res.bytes_freed + res.recycle_bin_bytes) / 1048576
                self.btn_disk.configure(text=f"Cleaned • {freed:.1f} MB")
                # immediately refresh the Disk card to reflect new free space
                self._refresh_disk_now()
            finally:
                self.btn_disk.configure(state="normal")
                # revert label after 3s
                self.after(3000, lambda: self.btn_disk.configure(text="Clean up disk"))
        threading.Thread(target=job, daemon=True).start()

    def _refresh_disk_now(self):
        """Compute disk aggregate right now and paint the tile (used when cleanup finishes)."""
        try:
            total = used = free = 0
            for p in psutil.disk_partitions(all=False):
                if not p.fstype or 'cdrom' in (p.opts or "").lower():
                    continue
                try:
                    u = psutil.disk_usage(p.mountpoint)
                    total += u.total; used += u.used; free += u.free
                except Exception:
                    continue
            if total > 0:
                used_pct = (used/total)*100
                free_gb  = free/(1024**3)
                total_gb = total/(1024**3)
                self.disk_pct.configure(text=f"{int(used_pct)}%")
                self.disk_bar.set(max(0.0, min(1.0, used_pct/100.0)))
                self.disk_line.configure(text=f"{free_gb:.2f} GB of {total_gb:.2f} GB free")
        except Exception:
            pass

    def _on_free_mem(self):
        def job():
            self.btn_mem.configure(state="disabled", text="Freeing…")
            try:
                res = self.cleaner.free_memory()
                self.btn_mem.configure(text=f"Freed ~{res.freed_mb:.1f} MB")
            finally:
                self.btn_mem.configure(state="normal")
                self.after(3000, lambda: self.btn_mem.configure(text="Free up memory"))
        threading.Thread(target=job, daemon=True).start()

    # ---------- live updates ----------
    def _tick(self):
        try:
            d = self.collector.get_data()
            ts = float(d.get("ts", 0.0))
            gpu  = d.get("gpu", {})
            cpu  = d.get("cpu", {})
            mem  = d.get("memory", {})
            disk = d.get("disk", {})
            drives = d.get("drives", [])

            # Heartbeat
            if ts > 0:
                t = time.localtime(ts)
                self.last_update.configure(text=f"Last update {t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}")

            # If the collector stops, restart it
            if ts <= self._last_ts and (time.time() - self._last_ts) > 2.0:
                self.collector = restart_collector()
            self._last_ts = ts if ts else self._last_ts

            # Gauges
            try: self.cpu_g.set(float(cpu.get("usage_percent", 0) or 0))
            except: pass
            try: self.gpu_g.set(float(gpu.get("usage_percent", 0) or 0))
            except: pass

            # Memory
            try:
                mem_pct = float(mem.get("usage_percent", 0) or 0)
                used_gb = float(mem.get("used_gb", 0) or 0)
                total_gb = float(mem.get("total_gb", 0) or 0)
                self.mem_pct.configure(text=f"{int(mem_pct)}%")
                self.mem_bar.set(max(0.0, min(1.0, mem_pct/100.0)))
                self.mem_line.configure(text=f"Used {used_gb:.1f} GB / {total_gb:.1f} GB")
                self.ram_total.configure(text=f"{total_gb:.0f} GB")
            except: pass

            # Disk
            try:
                used_pct = float(disk.get("usage_percent", 0) or 0)
                free_gb  = float(disk.get("free_gb", 0) or 0)
                total_gb = float(disk.get("total_gb", 0) or 0)
                self.disk_pct.configure(text=f"{int(used_pct)}%")
                self.disk_bar.set(max(0.0, min(1.0, used_pct/100.0)))
                self.disk_line.configure(text=f"{free_gb:.2f} GB of {total_gb:.2f} GB free")
                self.disk_io.configure(text=f"Read {disk.get('read_mb_s',0):.1f} MB/s • Write {disk.get('write_mb_s',0):.1f} MB/s")
            except: pass

            # Right info
            try:
                self.gpu_name.configure(text=str(gpu.get("name", "N/A")))
                self.gpu_clk.configure(text=str(gpu.get("core_clock", "N/A")))
                self.vram_clk.configure(text=str(gpu.get("memory_clock", "N/A")))
                self.gpu_temp.configure(text=str(gpu.get("temperature", "—")))
                self.cpu_name.configure(text=str(cpu.get("name", "N/A")))
                self.cpu_temp.configure(text=str(cpu.get("temperature", "—")))  # now fed by WMI/psutil if available
            except: pass

            # Drives
            try:
                for w in self.drives_frame.winfo_children(): w.destroy()
                if drives:
                    for drow in drives:
                        row = ctk.CTkFrame(self.drives_frame, fg_color="transparent"); row.pack(fill="x", pady=3)
                        ctk.CTkLabel(row, text=f"{drow['letter']}:  {drow['free_gb']:.1f} GB free / {drow['total_gb']:.1f} GB",
                                     text_color=COLORS["muted"], font=FONTS["body"]).pack(side="left", padx=(0, 8))
                        pbar = make_bar(row, height=10); pbar.pack(side="left", fill="x", expand=True, padx=(0, 8))
                        pbar.set(max(0.0, min(1.0, drow['used_pct']/100.0)))
                        ctk.CTkLabel(row, text=f"{int(drow['used_pct'])} %",
                                     text_color=COLORS["muted"], font=FONTS["body"]).pack(side="right")
                else:
                    ctk.CTkLabel(self.drives_frame, text="No drives", text_color=COLORS["muted"], font=FONTS["body"]).pack(anchor="e")
            except: pass

        finally:
            self.after(500, self._tick)
