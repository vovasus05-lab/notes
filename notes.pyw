"""Нотатки та завдання - невеликий застосунок для робочого столу Windows.

Запуск: двічі клацніть notes.pyw (потрібен Python з python.org, галочка "Add to PATH").
Дані зберігаються в %APPDATA%\\DesktopNotes\\data.json
"""
import json
import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox

APP_NAME = "DesktopNotes"
DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
DATA_FILE = os.path.join(DATA_DIR, "data.json")


# ---------- збереження ----------
def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("notes", [])
        data.setdefault("tasks", [])
        return data
    except (OSError, ValueError):
        return {"notes": [], "tasks": []}


def save_data(data):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DATA_FILE)
    except OSError as e:
        messagebox.showerror("Помилка збереження", str(e))


# ---------- автозапуск (реєстр Windows) ----------
def _run_command():
    if getattr(sys, "frozen", False):  # зібраний через PyInstaller
        return f'"{sys.executable}"'
    pyw = sys.executable.replace("python.exe", "pythonw.exe")
    return f'"{pyw}" "{os.path.abspath(__file__)}"'


def autostart_enabled():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run")
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def set_autostart(enable):
    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                         r"Software\Microsoft\Windows\CurrentVersion\Run",
                         0, winreg.KEY_SET_VALUE)
    if enable:
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _run_command())
    else:
        try:
            winreg.DeleteValue(key, APP_NAME)
        except FileNotFoundError:
            pass
    winreg.CloseKey(key)


# ---------- інтерфейс ----------
class App:
    def __init__(self, root):
        self.root = root
        self.data = load_data()
        self.cur_note = None

        root.title("Нотатки та завдання")
        root.geometry("680x480")
        root.minsize(520, 360)

        self.summary = ttk.Label(root, font=("Segoe UI", 11, "bold"))
        self.summary.pack(anchor="w", padx=12, pady=(10, 4))

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, padx=10, pady=4)
        self.tasks_tab = ttk.Frame(nb)
        self.notes_tab = ttk.Frame(nb)
        nb.add(self.tasks_tab, text="Завдання")
        nb.add(self.notes_tab, text="Нотатки")

        self.build_tasks()
        self.build_notes()

        bottom = ttk.Frame(root)
        bottom.pack(fill="x", padx=12, pady=(0, 8))
        self.auto_var = tk.BooleanVar(value=autostart_enabled())
        if os.name == "nt":
            ttk.Checkbutton(bottom, text="Запускати разом із Windows",
                            variable=self.auto_var,
                            command=self.toggle_autostart).pack(side="left")

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh_tasks()
        self.refresh_notes()
        self.update_summary()

    # --- завдання ---
    def build_tasks(self):
        f = self.tasks_tab
        top = ttk.Frame(f)
        top.pack(fill="x", padx=8, pady=8)
        self.task_entry = ttk.Entry(top, font=("Segoe UI", 11))
        self.task_entry.pack(side="left", fill="x", expand=True)
        self.task_entry.bind("<Return>", lambda e: self.add_task())
        ttk.Button(top, text="Додати", command=self.add_task).pack(side="left", padx=(6, 0))

        mid = ttk.Frame(f)
        mid.pack(fill="both", expand=True, padx=8)
        self.task_list = tk.Listbox(mid, font=("Segoe UI", 12), activestyle="none",
                                    selectmode="browse", exportselection=False)
        sb = ttk.Scrollbar(mid, command=self.task_list.yview)
        self.task_list.config(yscrollcommand=sb.set)
        self.task_list.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.task_list.bind("<Double-Button-1>", lambda e: self.toggle_task())

        btns = ttk.Frame(f)
        btns.pack(fill="x", padx=8, pady=8)
        ttk.Button(btns, text="Виконано / не виконано", command=self.toggle_task).pack(side="left")
        ttk.Button(btns, text="Видалити", command=self.delete_task).pack(side="left", padx=6)
        ttk.Button(btns, text="Прибрати виконані", command=self.clear_done).pack(side="left")

    def refresh_tasks(self):
        self.task_list.delete(0, "end")
        for i, t in enumerate(self.data["tasks"]):
            self.task_list.insert("end", ("☑  " if t["done"] else "☐  ") + t["text"])
            if t["done"]:
                self.task_list.itemconfig(i, fg="#888888")

    def selected_task(self):
        sel = self.task_list.curselection()
        return sel[0] if sel else None

    def add_task(self):
        text = self.task_entry.get().strip()
        if not text:
            return
        self.data["tasks"].append({"text": text, "done": False})
        self.task_entry.delete(0, "end")
        self.commit_tasks()

    def toggle_task(self):
        i = self.selected_task()
        if i is None:
            return
        self.data["tasks"][i]["done"] = not self.data["tasks"][i]["done"]
        self.commit_tasks(select=i)

    def delete_task(self):
        i = self.selected_task()
        if i is None:
            return
        del self.data["tasks"][i]
        self.commit_tasks()

    def clear_done(self):
        self.data["tasks"] = [t for t in self.data["tasks"] if not t["done"]]
        self.commit_tasks()

    def commit_tasks(self, select=None):
        save_data(self.data)
        self.refresh_tasks()
        if select is not None:
            self.task_list.selection_set(select)
        self.update_summary()

    # --- нотатки ---
    def build_notes(self):
        f = self.notes_tab
        left = ttk.Frame(f)
        left.pack(side="left", fill="y", padx=(8, 4), pady=8)
        self.note_list = tk.Listbox(left, width=24, font=("Segoe UI", 11),
                                    activestyle="none", exportselection=False)
        self.note_list.pack(fill="y", expand=True)
        self.note_list.bind("<<ListboxSelect>>", self.on_note_select)
        row = ttk.Frame(left)
        row.pack(fill="x", pady=(6, 0))
        ttk.Button(row, text="Нова", command=self.new_note).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Видалити", command=self.delete_note).pack(side="left", fill="x", expand=True, padx=(4, 0))

        right = ttk.Frame(f)
        right.pack(side="left", fill="both", expand=True, padx=(4, 8), pady=8)
        self.note_text = tk.Text(right, wrap="word", font=("Segoe UI", 12),
                                 undo=True, state="disabled")
        self.note_text.pack(fill="both", expand=True)
        self.note_text.bind("<KeyRelease>", self.on_note_edit)

    @staticmethod
    def note_title(text):
        first = text.strip().split("\n")[0] if text.strip() else ""
        return first[:30] or "(порожня нотатка)"

    def refresh_notes(self, select=None):
        self.note_list.delete(0, "end")
        for n in self.data["notes"]:
            self.note_list.insert("end", self.note_title(n))
        if select is not None and 0 <= select < len(self.data["notes"]):
            self.note_list.selection_set(select)
            self.load_note(select)
        else:
            self.cur_note = None
            self.note_text.config(state="normal")
            self.note_text.delete("1.0", "end")
            self.note_text.config(state="disabled")

    def load_note(self, i):
        self.cur_note = i
        self.note_text.config(state="normal")
        self.note_text.delete("1.0", "end")
        self.note_text.insert("1.0", self.data["notes"][i])
        self.note_text.edit_reset()

    def on_note_select(self, _event=None):
        sel = self.note_list.curselection()
        if sel:
            self.load_note(sel[0])

    def on_note_edit(self, _event=None):
        if self.cur_note is None:
            return
        text = self.note_text.get("1.0", "end-1c")
        self.data["notes"][self.cur_note] = text
        i = self.cur_note
        self.note_list.delete(i)
        self.note_list.insert(i, self.note_title(text))
        self.note_list.selection_set(i)
        save_data(self.data)

    def new_note(self):
        self.data["notes"].append("")
        save_data(self.data)
        self.refresh_notes(select=len(self.data["notes"]) - 1)
        self.note_text.focus_set()

    def delete_note(self):
        if self.cur_note is None:
            return
        if messagebox.askyesno("Видалити", "Видалити цю нотатку?"):
            del self.data["notes"][self.cur_note]
            save_data(self.data)
            self.refresh_notes()

    # --- інше ---
    def update_summary(self):
        open_n = sum(1 for t in self.data["tasks"] if not t["done"])
        self.summary.config(text=f"Невиконаних завдань: {open_n}    Нотаток: {len(self.data['notes'])}")

    def toggle_autostart(self):
        try:
            set_autostart(self.auto_var.get())
        except Exception as e:
            self.auto_var.set(not self.auto_var.get())
            messagebox.showerror("Автозапуск", str(e))

    def on_close(self):
        save_data(self.data)
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
