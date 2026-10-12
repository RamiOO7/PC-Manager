"""PC Manager - Rendimiento, Procesos, Limpieza y Prueba de render.
Requisitos: pip install psutil customtkinter
Ejecutar:   python pc_manager.py
"""
import os, math, ctypes, tempfile, subprocess, threading, time, multiprocessing as mp
import tkinter as tk
from tkinter import ttk, messagebox
import psutil
import customtkinter as ctk

ctk.set_appearance_mode("dark")
BG, CARD, ACC, TXT, MUT = "#0f1117", "#1a1d27", "#3b82f6", "#e5e7eb", "#8b93a7"
GREEN, ORANGE, RED, CYAN = "#22c55e", "#f59e0b", "#ef4444", "#22d3ee"
HIST = 60
PROTECTED = {"system", "system idle process", "registry", "smss.exe", "csrss.exe", "wininit.exe",
             "winlogon.exe", "services.exe", "lsass.exe", "svchost.exe", "dwm.exe", "explorer.exe",
             "fontdrvhost.exe", "sihost.exe", "taskhostw.exe", "ctfmon.exe", "searchhost.exe",
             "startmenuexperiencehost.exe", "shellexperiencehost.exe", "runtimebroker.exe",
             "textinputhost.exe", "securityhealthservice.exe", "msmpeng.exe", "cmd.exe",
             "conhost.exe", "python.exe", "pythonw.exe", "pcmanager.exe", "systemd", "init", "kthreadd"}


def fmt(b):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024: return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} PB"


def trim_ram():
    """Pide a Windows que libere memoria no usada de cada proceso (no cierra nada)."""
    if os.name != "nt": return 0
    n = 0
    for p in psutil.process_iter():
        try:
            h = ctypes.windll.kernel32.OpenProcess(0x0500, False, p.pid)
            if h:
                ctypes.windll.psapi.EmptyWorkingSet(h); ctypes.windll.kernel32.CloseHandle(h); n += 1
        except Exception: pass
    return n


class Graph(tk.Canvas):
    def __init__(self, master, title, color, **kw):
        super().__init__(master, height=120, bg=CARD, highlightthickness=0, **kw)
        self.title, self.color, self.data = title, color, [0] * HIST

    def push(self, v, label=""):
        self.data = self.data[1:] + [v]
        self.delete("all")
        w, h = max(self.winfo_width(), 50), self.winfo_height()
        for k in (25, 50, 75):
            y = h - (k / 100) * (h - 30)
            self.create_line(0, y, w, y, fill="#262a36")
        step = w / (HIST - 1)
        pts = [(i * step, h - (d / 100) * (h - 30)) for i, d in enumerate(self.data)]
        self.create_polygon([0, h] + [c for p in pts for c in p] + [w, h], fill=self.color, stipple="gray25", outline="")
        self.create_line([c for p in pts for c in p], fill=self.color, width=2, smooth=True)
        self.create_text(12, 8, anchor="nw", fill=TXT, font=("Segoe UI", 11, "bold"), text=f"{self.title}  {label}")


def cpu_worker(stop, counter):
    while not stop.is_set():
        x = 0.0
        for i in range(1, 200000):
            x += (i ** 0.5) * (i % 7) / (i + 1)
        with counter.get_lock():
            counter.value += 1


class App(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=BG)
        self.title("PC Manager")
        self.geometry("1000x700")
        self.minsize(900, 620)
        ttk.Style(self).theme_use("clam")
        st = ttk.Style()
        st.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=TXT, rowheight=28,
                     borderwidth=0, font=("Segoe UI", 10))
        st.configure("Treeview.Heading", background="#232736", foreground=MUT, borderwidth=0, font=("Segoe UI", 9, "bold"))
        st.map("Treeview", background=[("selected", ACC)])
        ctk.CTkLabel(self, text="⚡ PC Manager", font=("Segoe UI", 22, "bold"), text_color=TXT).pack(anchor="w", padx=20, pady=(14, 0))
        self.tabs = ctk.CTkTabview(self, fg_color=BG, segmented_button_selected_color=ACC,
                                   segmented_button_unselected_color=CARD, corner_radius=12)
        self.tabs.pack(fill="both", expand=True, padx=14, pady=8)
        self.t_perf, self.t_proc = self.tabs.add("Rendimiento"), self.tabs.add("Procesos")
        self.t_clean, self.t_stress = self.tabs.add("Limpieza"), self.tabs.add("Prueba de render")
        self.stress_procs, self.stress_stop, self.mem_blocks, self.running = [], None, [], False
        self.counter = mp.Value("l", 0)
        self.build_perf(); self.build_proc(); self.build_clean(); self.build_stress()
        self.last_net, self.n = psutil.net_io_counters(), 0
        self.tick()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------- helpers UI ----------
    def card(self, parent, title, color):
        f = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=14)
        ctk.CTkLabel(f, text=title, text_color=MUT, font=("Segoe UI", 11)).pack(anchor="w", padx=14, pady=(10, 0))
        v = ctk.CTkLabel(f, text="--", text_color=TXT, font=("Segoe UI", 24, "bold")); v.pack(anchor="w", padx=14)
        b = ctk.CTkProgressBar(f, progress_color=color, fg_color="#262a36", height=8); b.set(0)
        b.pack(fill="x", padx=14, pady=(2, 6))
        s = ctk.CTkLabel(f, text="", text_color=MUT, font=("Segoe UI", 10)); s.pack(anchor="w", padx=14, pady=(0, 10))
        return f, v, b, s

    def btn(self, parent, text, cmd, color=ACC, **kw):
        return ctk.CTkButton(parent, text=text, command=cmd, fg_color=color, hover_color=color,
                             corner_radius=10, height=34, font=("Segoe UI", 12, "bold"), **kw)

    # ---------- Rendimiento ----------
    def build_perf(self):
        f = self.t_perf
        top = ctk.CTkFrame(f, fg_color="transparent"); top.pack(fill="x", pady=4)
        self.cards = {}
        for i, (k, t, c) in enumerate((("cpu", "CPU", CYAN), ("ram", "MEMORIA RAM", GREEN),
                                       ("disk", "DISCO", ORANGE), ("net", "RED", ACC))):
            fr, v, b, s = self.card(top, t, c)
            fr.grid(row=0, column=i, sticky="nsew", padx=5); top.columnconfigure(i, weight=1)
            self.cards[k] = (v, b, s)
        gr = ctk.CTkFrame(f, fg_color="transparent"); gr.pack(fill="x", pady=6)
        gr.columnconfigure((0, 1), weight=1)
        self.g_cpu = Graph(gr, "CPU", CYAN); self.g_cpu.grid(row=0, column=0, sticky="ew", padx=5)
        self.g_ram = Graph(gr, "RAM", GREEN); self.g_ram.grid(row=0, column=1, sticky="ew", padx=5)
        self.cores = ctk.CTkFrame(f, fg_color=CARD, corner_radius=14); self.cores.pack(fill="both", expand=True, padx=5, pady=6)
        self.core_bars = []
        self.lbl_info = ctk.CTkLabel(f, text="", text_color=MUT, font=("Consolas", 11), justify="left")
        self.lbl_info.pack(anchor="w", padx=8, pady=4)

    def update_perf(self):
        cpu, vm = psutil.cpu_percent(), psutil.virtual_memory()
        du, n = psutil.disk_usage(os.path.abspath(os.sep)), psutil.net_io_counters()
        down, up = n.bytes_recv - self.last_net.bytes_recv, n.bytes_sent - self.last_net.bytes_sent
        self.last_net = n
        fq = psutil.cpu_freq()
        c = self.cards
        c["cpu"][0].configure(text=f"{cpu:.0f}%"); c["cpu"][1].set(cpu / 100)
        c["cpu"][2].configure(text=f"{fq.current:.0f} MHz" if fq else "")
        c["ram"][0].configure(text=f"{vm.percent:.0f}%"); c["ram"][1].set(vm.percent / 100)
        c["ram"][2].configure(text=f"{fmt(vm.used)} / {fmt(vm.total)}")
        c["disk"][0].configure(text=f"{du.percent:.0f}%"); c["disk"][1].set(du.percent / 100)
        c["disk"][2].configure(text=f"{fmt(du.used)} / {fmt(du.total)}")
        c["net"][0].configure(text=f"↓ {fmt(down)}/s"); c["net"][1].set(min(1, down / 12.5e6))
        c["net"][2].configure(text=f"↑ {fmt(up)}/s")
        self.g_cpu.push(cpu, f"{cpu:.0f}%"); self.g_ram.push(vm.percent, f"{vm.percent:.0f}%")
        per = psutil.cpu_percent(percpu=True)
        if not self.core_bars:
            for i in range(len(per)):
                l = ctk.CTkLabel(self.cores, text=f"Núcleo {i}", text_color=MUT, font=("Segoe UI", 10))
                b = ctk.CTkProgressBar(self.cores, progress_color=CYAN, fg_color="#262a36", height=8, width=90)
                l.grid(row=i // 4 * 2, column=i % 4, padx=14, pady=(8, 0), sticky="w")
                b.grid(row=i // 4 * 2 + 1, column=i % 4, padx=14, pady=(0, 4), sticky="ew")
                self.core_bars.append(b)
            for i in range(4): self.cores.columnconfigure(i, weight=1)
        for b, p in zip(self.core_bars, per): b.set(p / 100)
        up_s, temps = time.time() - psutil.boot_time(), ""
        try:
            t = psutil.sensors_temperatures()
            if t: temps = " | " + ", ".join(f"{k}: {v[0].current:.0f}°C" for k, v in t.items())
        except Exception: pass
        self.lbl_info.configure(text=f"Procesos: {len(psutil.pids())} | Encendido: {int(up_s//3600)}h {int(up_s%3600//60)}m{temps}")

    # ---------- Procesos ----------
    def build_proc(self):
        f = self.t_proc
        bar = ctk.CTkFrame(f, fg_color="transparent"); bar.pack(fill="x", pady=(2, 8))
        self.btn(bar, "🧹 Limpiar procesos", self.open_cleaner, GREEN).pack(side="left", padx=4)
        self.btn(bar, "🚀 Liberar RAM", self.free_ram, ACC).pack(side="left", padx=4)
        self.btn(bar, "✖ Finalizar seleccionado", self.kill_proc, RED).pack(side="left", padx=4)
        self.lbl_proc = ctk.CTkLabel(bar, text="", text_color=MUT); self.lbl_proc.pack(side="left", padx=10)
        cols = ("pid", "nombre", "cpu", "ram")
        self.tree = ttk.Treeview(f, columns=cols, show="headings")
        for c, w in zip(cols, (80, 420, 100, 130)):
            self.tree.heading(c, text=c.upper()); self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=4)
        for p in psutil.process_iter():
            try: p.cpu_percent(None)
            except Exception: pass

    def update_proc(self):
        rows = []
        for p in psutil.process_iter(["pid", "name", "memory_info"]):
            try: rows.append((p.info["pid"], p.info["name"], p.cpu_percent(None) / psutil.cpu_count(), p.info["memory_info"].rss))
            except Exception: pass
        rows.sort(key=lambda r: (r[2], r[3]), reverse=True)
        sel = self.tree.selection(); keep = self.tree.item(sel[0])["values"][0] if sel else None
        self.tree.delete(*self.tree.get_children())
        for r in rows[:150]:
            iid = self.tree.insert("", "end", values=(r[0], r[1], f"{r[2]:.1f}%", fmt(r[3])))
            if keep == r[0]: self.tree.selection_set(iid)

    def kill_proc(self):
        sel = self.tree.selection()
        if not sel: return
        pid, name = self.tree.item(sel[0])["values"][:2]
        if messagebox.askyesno("Confirmar", f"¿Finalizar {name} (PID {pid})?"):
            try: psutil.Process(int(pid)).terminate()
            except Exception as e: messagebox.showerror("Error", str(e))

    def free_ram(self):
        before = psutil.virtual_memory().available
        trim_ram(); time.sleep(0.5)
        gained = psutil.virtual_memory().available - before
        self.lbl_proc.configure(text=f"RAM liberada: {fmt(max(gained, 0))}")

    def open_cleaner(self):
        me = psutil.Process()
        try: user = me.username()
        except Exception: user = None
        cands = []
        for p in psutil.process_iter(["pid", "name", "memory_info", "username"]):
            try:
                i = p.info
                if i["pid"] in (me.pid, me.ppid()) or (i["name"] or "").lower() in PROTECTED: continue
                if user and i["username"] != user: continue
                if i["memory_info"].rss < 40 * 2**20: continue
                cands.append((i["memory_info"].rss, i["pid"], i["name"]))
            except Exception: pass
        cands.sort(reverse=True)
        win = ctk.CTkToplevel(self, fg_color=BG); win.title("Limpiar procesos"); win.geometry("520x560")
        win.after(150, lambda: (win.lift(), win.focus()))
        ctk.CTkLabel(win, text="Apps en segundo plano que puedes cerrar", font=("Segoe UI", 15, "bold")).pack(pady=(14, 2))
        ctk.CTkLabel(win, text="Se excluyen procesos del sistema. Guarda tu trabajo antes de cerrar.",
                     text_color=MUT).pack()
        lst = ctk.CTkScrollableFrame(win, fg_color=CARD); lst.pack(fill="both", expand=True, padx=14, pady=10)
        rows = []
        for rss, pid, name in cands[:40]:
            v = tk.BooleanVar(value=rss > 200 * 2**20)
            ctk.CTkCheckBox(lst, text=f"{name}  —  {fmt(rss)}", variable=v, fg_color=ACC).pack(anchor="w", pady=3, padx=6)
            rows.append((v, pid, rss))
        if not cands: ctk.CTkLabel(lst, text="No hay nada que limpiar 🎉", text_color=MUT).pack(pady=20)
        def go():
            freed = n = 0
            for v, pid, rss in rows:
                if v.get():
                    try: psutil.Process(pid).terminate(); freed += rss; n += 1
                    except Exception: pass
            self.lbl_proc.configure(text=f"Cerrados {n} procesos (~{fmt(freed)})")
            win.destroy()
        self.btn(win, "Cerrar seleccionados", go, RED).pack(pady=(0, 14))

    # ---------- Limpieza ----------
    def build_clean(self):
        f = self.t_clean
        c = ctk.CTkFrame(f, fg_color=CARD, corner_radius=14); c.pack(fill="x", pady=4, padx=4)
        ctk.CTkLabel(c, text="🗑 Archivos temporales", font=("Segoe UI", 14, "bold")).pack(side="left", padx=14, pady=14)
        self.btn(c, "Escanear", self.scan_temp).pack(side="left", padx=4)
        self.btn(c, "Limpiar", self.clean_temp, GREEN).pack(side="left", padx=4)
        self.lbl_temp = ctk.CTkLabel(c, text="Sin escanear", text_color=MUT); self.lbl_temp.pack(side="left", padx=12)
        ctk.CTkLabel(f, text="📦 Aplicaciones instaladas", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=8, pady=(12, 4))
        self.apps = ttk.Treeview(f, columns=("n", "s"), show="headings")
        self.apps.heading("n", text="NOMBRE"); self.apps.heading("s", text="TAMAÑO")
        self.apps.column("n", width=600); self.apps.column("s", width=120)
        self.apps.pack(fill="both", expand=True, padx=4)
        bar = ctk.CTkFrame(f, fg_color="transparent"); bar.pack(fill="x", pady=8)
        self.btn(bar, "Recargar", self.load_apps).pack(side="left", padx=4)
        self.btn(bar, "Desinstalar seleccionada", self.uninstall, RED).pack(side="left", padx=4)
        self.uninst = {}; self.load_apps()

    def temp_dirs(self):
        d = {tempfile.gettempdir()}
        d.add(os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Temp") if os.name == "nt" else os.path.expanduser("~/.cache"))
        return [x for x in d if os.path.isdir(x)]

    def scan_temp(self):
        def work():
            total = n = 0
            for d in self.temp_dirs():
                for root, _, files in os.walk(d):
                    for fn in files:
                        try: total += os.path.getsize(os.path.join(root, fn)); n += 1
                        except Exception: pass
            self.after(0, lambda: self.lbl_temp.configure(text=f"{n} archivos · {fmt(total)} recuperables"))
        threading.Thread(target=work, daemon=True).start()

    def clean_temp(self):
        if not messagebox.askyesno("Confirmar", "Se borrarán los temporales (los que estén en uso se omiten). ¿Continuar?"): return
        def work():
            freed = 0
            for d in self.temp_dirs():
                for root, dirs, files in os.walk(d, topdown=False):
                    for fn in files:
                        p = os.path.join(root, fn)
                        try: s = os.path.getsize(p); os.remove(p); freed += s
                        except Exception: pass
                    for dn in dirs:
                        try: os.rmdir(os.path.join(root, dn))
                        except Exception: pass
            self.after(0, lambda: self.lbl_temp.configure(text=f"Liberados {fmt(freed)} ✔"))
        threading.Thread(target=work, daemon=True).start()

    def load_apps(self):
        self.apps.delete(*self.apps.get_children()); self.uninst.clear()
        if os.name != "nt":
            self.apps.insert("", "end", values=("Solo disponible en Windows", "")); return
        import winreg
        base = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
        keys = [(winreg.HKEY_LOCAL_MACHINE, base), (winreg.HKEY_LOCAL_MACHINE, base.replace("SOFTWARE\\", "SOFTWARE\\WOW6432Node\\")),
                (winreg.HKEY_CURRENT_USER, base)]
        found = {}
        for hive, path in keys:
            try: k = winreg.OpenKey(hive, path)
            except OSError: continue
            for i in range(winreg.QueryInfoKey(k)[0]):
                try:
                    sk = winreg.OpenKey(k, winreg.EnumKey(k, i))
                    name, cmd = winreg.QueryValueEx(sk, "DisplayName")[0], winreg.QueryValueEx(sk, "UninstallString")[0]
                    try: size = winreg.QueryValueEx(sk, "EstimatedSize")[0] * 1024
                    except OSError: size = 0
                    found[name] = (cmd, size)
                except OSError: pass
        for name, (cmd, size) in sorted(found.items(), key=lambda x: -x[1][1]):
            self.uninst[self.apps.insert("", "end", values=(name, fmt(size) if size else "-"))] = cmd

    def uninstall(self):
        sel = self.apps.selection()
        if sel and sel[0] in self.uninst and messagebox.askyesno("Confirmar", "¿Abrir el desinstalador de esta app?"):
            subprocess.Popen(self.uninst[sel[0]], shell=True)

    # ---------- Prueba de render ----------
    def build_stress(self):
        f = self.t_stress
        c = ctk.CTkFrame(f, fg_color=CARD, corner_radius=14); c.pack(fill="x", padx=4, pady=4)
        ctk.CTkLabel(c, text="🔥 Prueba a máximo rendimiento", font=("Segoe UI", 15, "bold")).grid(row=0, column=0, columnspan=4, sticky="w", padx=14, pady=(12, 4))
        self.v_cpu, self.v_ram, self.v_gfx = tk.BooleanVar(value=True), tk.BooleanVar(), tk.BooleanVar(value=True)
        for i, (t, v) in enumerate((("CPU (todos los núcleos)", self.v_cpu), ("RAM (50% de la libre)", self.v_ram), ("Render gráfico", self.v_gfx))):
            ctk.CTkCheckBox(c, text=t, variable=v, fg_color=ACC).grid(row=1, column=i, padx=14, pady=4, sticky="w")
        self.v_dur = tk.IntVar(value=30)
        self.lbl_dur = ctk.CTkLabel(c, text="Duración: 30 s", text_color=MUT)
        self.lbl_dur.grid(row=2, column=0, padx=14, sticky="w")
        ctk.CTkSlider(c, from_=10, to=300, number_of_steps=29, variable=self.v_dur, progress_color=ACC,
                      command=lambda v: self.lbl_dur.configure(text=f"Duración: {int(v)} s")).grid(row=2, column=1, columnspan=2, sticky="ew", padx=10)
        self.btn_stress = self.btn(c, "▶ Iniciar", self.toggle_stress, GREEN)
        self.btn_stress.grid(row=2, column=3, padx=14, pady=10)
        c.columnconfigure((0, 1, 2), weight=1)
        self.lbl_stress = ctk.CTkLabel(f, text="Inactivo", text_color=MUT, font=("Consolas", 11)); self.lbl_stress.pack(anchor="w", padx=8)
        self.g_stress = Graph(f, "CPU durante la prueba", RED); self.g_stress.pack(fill="x", padx=4, pady=6)
        self.canvas = tk.Canvas(f, bg="#000", height=200, highlightthickness=0); self.canvas.pack(fill="both", expand=True, padx=4, pady=4)

    def toggle_stress(self):
        if self.running: self.stop_stress(); return
        if not messagebox.askyesno("Aviso", "La prueba lleva el PC al límite y puede calentarlo. Vigila las temperaturas. ¿Continuar?"): return
        self.running, self.t0, self.angle = True, time.time(), 0
        self.btn_stress.configure(text="■ Detener", fg_color=RED, hover_color=RED)
        self.counter = mp.Value("l", 0); self.stress_stop = mp.Event()
        if self.v_cpu.get():
            self.stress_procs = [mp.Process(target=cpu_worker, args=(self.stress_stop, self.counter), daemon=True) for _ in range(psutil.cpu_count())]
            for p in self.stress_procs: p.start()
        if self.v_ram.get():
            try:
                for _ in range(int(psutil.virtual_memory().available * 0.5) // (64 * 2**20)):
                    self.mem_blocks.append(bytearray(b"\x01" * (64 * 2**20)))
            except MemoryError: pass
        self.render_loop()

    def render_loop(self):
        if not self.running: return
        el = time.time() - self.t0
        if el >= self.v_dur.get(): self.stop_stress(); return
        if self.v_gfx.get():
            c = self.canvas; c.delete("all")
            w, h = c.winfo_width(), c.winfo_height(); self.angle += 0.08
            for i in range(120):
                a = self.angle + i * 0.15
                x, y = w / 2 + math.cos(a * 1.3) * (i * w / 260), h / 2 + math.sin(a) * (i * h / 260)
                col = f"#{int(127+127*math.sin(a)):02x}{int(127+127*math.sin(a+2)):02x}{int(127+127*math.sin(a+4)):02x}"
                c.create_oval(x - 8, y - 8, x + 8, y + 8, fill=col, outline="")
        cpu = psutil.cpu_percent(); self.g_stress.push(cpu, f"{cpu:.0f}%")
        self.lbl_stress.configure(text=f"Tiempo {el:.0f}/{self.v_dur.get()} s | Puntuación CPU: {self.counter.value} | RAM reservada: {fmt(sum(len(b) for b in self.mem_blocks))}")
        self.after(33, self.render_loop)

    def stop_stress(self):
        self.running = False
        if self.stress_stop: self.stress_stop.set()
        for p in self.stress_procs:
            p.join(timeout=1)
            if p.is_alive(): p.terminate()
        self.stress_procs, self.mem_blocks = [], []
        self.btn_stress.configure(text="▶ Iniciar", fg_color=GREEN, hover_color=GREEN)
        self.lbl_stress.configure(text=f"Finalizado. Puntuación final CPU: {self.counter.value}")

    # ---------- Bucle ----------
    def tick(self):
        self.update_perf()
        self.n += 1
        if self.n % 3 == 0: self.update_proc()
        self.after(1000, self.tick)

    def on_close(self):
        self.stop_stress(); self.destroy()


if __name__ == "__main__":
    mp.freeze_support()
    App().mainloop()
