"""Стікери на робочому столі (Windows).

Кожен стікер - окреме віконце: свій колір, текст, пункти-чекбокси та посилання на файли/папки.
Дані: %APPDATA%\\DesktopNotes\\stickers.json
"""
import json
import os
import socket
import subprocess
import sys
import tkinter as tk
import uuid
from tkinter import filedialog, messagebox

APP_NAME = "DesktopNotes"
DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
DATA_FILE = os.path.join(DATA_DIR, "stickers.json")
OLD_FILE = os.path.join(DATA_DIR, "data.json")  # дані попередньої версії

COLORS = {
    "Жовтий": "#FFF59D",
    "Рожевий": "#F8BBD0",
    "Зелений": "#C5E1A5",
    "Блакитний": "#B3E5FC",
    "Помаранчевий": "#FFCC80",
    "Фіолетовий": "#D1C4E9",
    "Сірий": "#E0E0E0",
}
UI_FONT = "Segoe UI"
BOX_OPEN, BOX_DONE = "☐", "☑"


# ---------- допоміжне ----------
def darken(hex_color, factor):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % (int(r * factor), int(g * factor), int(b * factor))


def open_path(path):
    try:
        os.startfile(path)  # Windows
    except AttributeError:
        subprocess.Popen(["xdg-open", path])
    except OSError as e:
        messagebox.showerror("Не вдалося відкрити", f"{path}\n\n{e}")


def reveal_path(path):
    try:
        subprocess.Popen(["explorer", f"/select,{os.path.normpath(path)}"])
    except OSError:
        pass


# ---------- збереження ----------
def new_sticker_dict(x, y, w, h, color="#FFF59D", text="", links=None):
    return {"id": uuid.uuid4().hex, "x": x, "y": y, "w": w, "h": h,
            "color": color, "text": text, "links": links or [], "topmost": True}


def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("stickers", [])
        data.setdefault("last_dir", "")
        return data
    except (OSError, ValueError):
        pass
    data = {"stickers": [], "last_dir": ""}
    # одноразовий імпорт зі старої версії
    try:
        with open(OLD_FILE, "r", encoding="utf-8") as f:
            old = json.load(f)
        items = []
        tasks = old.get("tasks", [])
        if tasks:
            lines = [(BOX_DONE if t.get("done") else BOX_OPEN) + " " + t.get("text", "") for t in tasks]
            items.append(("#FFF59D", "\n".join(lines)))
        for n in old.get("notes", []):
            items.append(("#B3E5FC", n))
        for i, (color, text) in enumerate(items):
            data["stickers"].append(new_sticker_dict(80 + 40 * i, 80 + 40 * i, 280, 280, color, text))
    except (OSError, ValueError):
        pass
    return data


def save_data(data):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DATA_FILE)
    except OSError as e:
        messagebox.showerror("Помилка збереження", str(e))


# ---------- автозапуск ----------
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _run_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pyw = sys.executable.replace("python.exe", "pythonw.exe")
    return f'"{pyw}" "{os.path.abspath(__file__)}"'


def autostart_enabled():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY)
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def set_autostart(enable):
    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE)
    if enable:
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _run_command())
    else:
        try:
            winreg.DeleteValue(key, APP_NAME)
        except FileNotFoundError:
            pass
    winreg.CloseKey(key)


# ---------- стікер ----------
class Sticker:
    def __init__(self, mgr, d):
        self.mgr, self.d = mgr, d
        self.menu_vars = []
        root = mgr.root

        d.setdefault("links", [])
        d.setdefault("topmost", True)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        d["x"] = max(0, min(int(d["x"]), sw - 80))
        d["y"] = max(0, min(int(d["y"]), sh - 80))

        w = self.win = tk.Toplevel(root)
        w.overrideredirect(True)
        w.attributes("-topmost", bool(d["topmost"]))
        w.geometry(f'{d["w"]}x{d["h"]}+{d["x"]}+{d["y"]}')

        self.outer = tk.Frame(w, highlightthickness=1)
        self.outer.pack(fill="both", expand=True)

        # шапка
        self.header = tk.Frame(self.outer)
        self.header.pack(side="top", fill="x")
        self.btn_new = self._hbtn("+", lambda e: mgr.new_sticker(), "left")
        self.btn_close = self._hbtn("✕", lambda e: self.delete(), "right")
        self.btn_menu = self._hbtn("⋯", lambda e: self.show_menu(e), "right")
        self.spacer = tk.Label(self.header)
        self.spacer.pack(side="left", fill="x", expand=True)

        # низ з ручкою зміни розміру
        self.footer = tk.Frame(self.outer)
        self.footer.pack(side="bottom", fill="x")
        self.grip = tk.Label(self.footer, text="◢", font=(UI_FONT, 8))
        for cur in ("size_nw_se", "bottom_right_corner", "sizing"):
            try:
                self.grip.configure(cursor=cur)
                break
            except tk.TclError:
                continue
        self.grip.pack(side="right")

        # посилання
        self.links_frame = tk.Frame(self.outer)
        self.lb = tk.Listbox(self.links_frame, font=(UI_FONT, 10), relief="flat",
                             highlightthickness=0, activestyle="none",
                             exportselection=False, borderwidth=0)
        self.lb.pack(fill="x")

        # текст
        self.text = tk.Text(self.outer, wrap="word", font=(UI_FONT, 11), relief="flat",
                            borderwidth=0, highlightthickness=0, undo=True, padx=8, pady=4)
        self.text.pack(side="top", fill="both", expand=True)
        self.text.tag_configure("done", overstrike=True, foreground="#777777")
        self.text.insert("1.0", d["text"])
        self.text.edit_reset()
        self.text.edit_modified(False)
        self.restyle()

        self.apply_color()
        self.refresh_links()

        # події
        for wdg in (self.header, self.spacer):
            wdg.bind("<ButtonPress-1>", self.drag_start)
            wdg.bind("<B1-Motion>", self.drag_move)
            wdg.bind("<ButtonRelease-1>", self.drag_end)
            wdg.bind("<Button-3>", self.show_menu)
        self.grip.bind("<ButtonPress-1>", self.rs_start)
        self.grip.bind("<B1-Motion>", self.rs_move)
        self.grip.bind("<ButtonRelease-1>", self.drag_end)
        self.text.bind("<<Modified>>", self.on_modified)
        self.text.bind("<Button-1>", self.on_text_click)
        self.text.bind("<Return>", self.on_return)
        self.lb.bind("<Double-Button-1>", lambda e: self.open_selected())
        self.lb.bind("<Return>", lambda e: self.open_selected())
        self.lb.bind("<Delete>", lambda e: self.remove_selected_link())
        self.lb.bind("<Button-3>", self.link_menu)

    # --- побудова ---
    def _hbtn(self, txt, cmd, side):
        b = tk.Label(self.header, text=txt, font=(UI_FONT, 11, "bold"), cursor="hand2", padx=7, pady=1)
        b.pack(side=side)
        b.bind("<Button-1>", cmd)
        return b

    def apply_color(self):
        c = self.d["color"]
        hd, ln = darken(c, 0.90), darken(c, 0.94)
        self.win.configure(bg=c)
        self.outer.configure(bg=c, highlightbackground=darken(c, 0.7), highlightcolor=darken(c, 0.7))
        self.header.configure(bg=hd)
        for lbl in (self.btn_new, self.btn_close, self.btn_menu, self.spacer):
            lbl.configure(bg=hd, fg="#333333")
        self.footer.configure(bg=c)
        self.grip.configure(bg=c, fg=darken(c, 0.6))
        self.text.configure(bg=c, fg="#222222", insertbackground="#222222",
                            selectbackground=darken(c, 0.75), selectforeground="#000000")
        self.links_frame.configure(bg=c)
        self.lb.configure(bg=ln, fg="#0b4f9c", selectbackground=darken(c, 0.8), selectforeground="#0b4f9c")

    # --- перетягування / розмір ---
    def drag_start(self, e):
        self.win.lift()
        self._dx = e.x_root - self.win.winfo_x()
        self._dy = e.y_root - self.win.winfo_y()

    def drag_move(self, e):
        self.win.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def drag_end(self, _e=None):
        self.d.update(x=self.win.winfo_x(), y=self.win.winfo_y(),
                      w=self.win.winfo_width(), h=self.win.winfo_height())
        self.mgr.schedule_save()

    def rs_start(self, e):
        self._rx, self._ry = e.x_root, e.y_root
        self._rw, self._rh = self.win.winfo_width(), self.win.winfo_height()

    def rs_move(self, e):
        w = max(190, self._rw + e.x_root - self._rx)
        h = max(150, self._rh + e.y_root - self._ry)
        self.win.geometry(f"{w}x{h}")

    # --- текст і чекбокси ---
    def on_modified(self, _e=None):
        if self.text.edit_modified():
            self.d["text"] = self.text.get("1.0", "end-1c")
            self.restyle()
            self.mgr.schedule_save()
            self.text.edit_modified(False)

    def restyle(self):
        self.text.tag_remove("done", "1.0", "end")
        last = int(self.text.index("end-1c").split(".")[0])
        for i in range(1, last + 1):
            if self.text.get(f"{i}.0") == BOX_DONE:
                self.text.tag_add("done", f"{i}.0", f"{i}.end")

    def on_text_click(self, e):
        self.win.focus_force()
        idx = self.text.index(f"@{e.x},{e.y}")
        line, col = (int(v) for v in idx.split("."))
        ch = self.text.get(f"{line}.0")
        if col == 0 and ch in (BOX_OPEN, BOX_DONE):
            self.text.delete(f"{line}.0")
            self.text.insert(f"{line}.0", BOX_DONE if ch == BOX_OPEN else BOX_OPEN)
            return "break"

    def on_return(self, _e):
        line = self.text.get("insert linestart", "insert lineend")
        col = int(self.text.index("insert").split(".")[1])
        if line[:1] in (BOX_OPEN, BOX_DONE) and col >= 2:
            if line[1:].strip() == "":
                self.text.delete("insert linestart", "insert lineend")
            else:
                self.text.insert("insert", "\n" + BOX_OPEN + " ")
                self.text.see("insert")
            return "break"

    def add_item(self):
        content = self.text.get("1.0", "end-1c")
        prefix = "\n" if content and not content.endswith("\n") else ""
        self.text.insert("end-1c", prefix + BOX_OPEN + " ")
        self.text.see("end")
        self.text.focus_set()
        self.win.focus_force()

    # --- посилання ---
    def refresh_links(self):
        self.lb.delete(0, "end")
        for p in self.d["links"]:
            name = os.path.basename(p.rstrip("\\/")) or p
            if not os.path.exists(p):
                self.lb.insert("end", f"⚠ {name} (не знайдено)")
            else:
                self.lb.insert("end", ("📁 " if os.path.isdir(p) else "📄 ") + name)
        if self.d["links"]:
            self.lb.configure(height=min(len(self.d["links"]), 4))
            self.links_frame.pack(side="bottom", fill="x", padx=6, pady=(0, 4), before=self.text)
        else:
            self.links_frame.pack_forget()

    def _add_links(self, paths):
        for p in paths:
            p = os.path.normpath(p)
            if p not in self.d["links"]:
                self.d["links"].append(p)
        if paths:
            self.mgr.data["last_dir"] = os.path.dirname(os.path.normpath(paths[0]))
        self.refresh_links()
        self.mgr.schedule_save()

    def _dialog(self, fn):
        """Діалоги показуємо, тимчасово прибравши 'поверх усіх', щоб вони не ховалися."""
        self.win.attributes("-topmost", False)
        try:
            return fn()
        finally:
            self.win.attributes("-topmost", bool(self.d["topmost"]))

    def add_files(self):
        start = self.mgr.data.get("last_dir") or os.path.expanduser("~")
        paths = self._dialog(lambda: filedialog.askopenfilenames(
            parent=self.win, title="Прикріпити файли", initialdir=start))
        self._add_links(list(paths))

    def add_folder(self):
        start = self.mgr.data.get("last_dir") or os.path.expanduser("~")
        p = self._dialog(lambda: filedialog.askdirectory(
            parent=self.win, title="Прикріпити папку", initialdir=start))
        if p:
            self._add_links([p])

    def _sel(self):
        s = self.lb.curselection()
        return s[0] if s else None

    def open_selected(self):
        i = self._sel()
        if i is not None:
            open_path(self.d["links"][i])

    def remove_selected_link(self):
        i = self._sel()
        if i is not None:
            del self.d["links"][i]
            self.refresh_links()
            self.mgr.schedule_save()

    def link_menu(self, e):
        i = self.lb.nearest(e.y)
        if i < 0 or i >= len(self.d["links"]):
            return
        self.lb.selection_clear(0, "end")
        self.lb.selection_set(i)
        m = tk.Menu(self.win, tearoff=0)
        m.add_command(label="Відкрити", command=self.open_selected)
        m.add_command(label="Показати в папці", command=lambda: reveal_path(self.d["links"][i]))
        m.add_command(label="Видалити посилання", command=self.remove_selected_link)
        m.tk_popup(e.x_root, e.y_root)

    # --- меню стікера ---
    def set_color(self, c):
        self.d["color"] = c
        self.apply_color()
        self.mgr.schedule_save()

    def toggle_topmost(self, var):
        self.d["topmost"] = bool(var.get())
        self.win.attributes("-topmost", self.d["topmost"])
        self.mgr.schedule_save()

    def toggle_autostart(self, var):
        try:
            set_autostart(var.get())
        except Exception as ex:
            messagebox.showerror("Автозапуск", str(ex))

    def show_menu(self, e):
        m = tk.Menu(self.win, tearoff=0)
        self.menu_vars = []
        m.add_command(label="Новий стікер", command=self.mgr.new_sticker)
        m.add_separator()
        m.add_command(label=f"Додати пункт {BOX_OPEN}", command=self.add_item)
        m.add_command(label="Прикріпити файли…", command=self.add_files)
        m.add_command(label="Прикріпити папку…", command=self.add_folder)
        m.add_separator()
        cm = tk.Menu(m, tearoff=0)
        cvar = tk.StringVar(value=self.d["color"])
        self.menu_vars.append(cvar)
        for name, hx in COLORS.items():
            cm.add_radiobutton(label=name, variable=cvar, value=hx,
                               command=lambda h=hx: self.set_color(h))
        m.add_cascade(label="Колір", menu=cm)
        tvar = tk.BooleanVar(value=bool(self.d["topmost"]))
        self.menu_vars.append(tvar)
        m.add_checkbutton(label="Поверх усіх вікон", variable=tvar,
                          command=lambda: self.toggle_topmost(tvar))
        if os.name == "nt":
            avar = tk.BooleanVar(value=autostart_enabled())
            self.menu_vars.append(avar)
            m.add_checkbutton(label="Запускати разом із Windows", variable=avar,
                              command=lambda: self.toggle_autostart(avar))
        m.add_separator()
        m.add_command(label="Видалити стікер", command=self.delete)
        m.add_command(label="Вийти з програми", command=self.mgr.quit)
        m.tk_popup(e.x_root, e.y_root)

    def delete(self):
        if self.d["text"].strip() or self.d["links"]:
            ok = self._dialog(lambda: messagebox.askyesno(
                "Видалити стікер", "Видалити цей стікер разом із вмістом?", parent=self.win))
            if not ok:
                return
        self.mgr.remove_sticker(self)


# ---------- менеджер ----------
class Manager:
    def __init__(self, root):
        self.root = root
        self.data = load_data()
        self.stickers = []
        self._save_job = None
        self.scale = max(1.0, root.winfo_fpixels("1i") / 96)
        for d in self.data["stickers"]:
            self.stickers.append(Sticker(self, d))
        if not self.stickers:
            self.new_sticker()

    def new_sticker(self):
        n = len(self.stickers)
        if self.stickers:
            last = self.stickers[-1].d
            x, y = last["x"] + 36, last["y"] + 36
        else:
            x, y = 100, 100
        color = list(COLORS.values())[n % len(COLORS)]
        d = new_sticker_dict(x, y, int(270 * self.scale), int(260 * self.scale), color)
        self.data["stickers"].append(d)
        s = Sticker(self, d)
        self.stickers.append(s)
        s.text.focus_set()
        s.win.focus_force()
        self.schedule_save()

    def remove_sticker(self, s):
        self.stickers.remove(s)
        self.data["stickers"].remove(s.d)
        s.win.destroy()
        if not self.stickers:  # завжди лишається хоча б один
            self.new_sticker()
        self.schedule_save()

    def schedule_save(self):
        if self._save_job is not None:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(400, self.save_now)

    def save_now(self):
        self._save_job = None
        for s in self.stickers:
            s.d.update(x=s.win.winfo_x(), y=s.win.winfo_y(),
                       w=s.win.winfo_width(), h=s.win.winfo_height())
        save_data(self.data)

    def quit(self):
        self.save_now()
        self.root.destroy()


def acquire_single_instance():
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", 49731))
        return s
    except OSError:
        return None


if __name__ == "__main__":
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = tk.Tk()
    root.withdraw()
    lock = acquire_single_instance()
    if lock is None:
        messagebox.showinfo("Стікери", "Програма вже запущена - стікери лежать на робочому столі.")
        root.destroy()
        sys.exit(0)
    Manager(root)
    root.mainloop()
