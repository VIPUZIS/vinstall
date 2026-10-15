#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vInstaller Creator — графический «создатель» установщиков EXE.

Приложение позволяет визуально настроить проект установщика (страницы мастера,
компоненты, файлы, ярлыки, реестр, внешний вид) и собрать из него .exe на базе
NSIS (Nullsoft Scriptable Install System).  Проект сохраняется в файл
``*.vicproj`` (JSON), который можно переиспользовать и передавать в CLI
(``vic-cli.py`` / ``vInstallerCreator --cli …``).

Модули:
    src.core   — модель проекта, валидация, генерация NSI и ресурсов;
    этот файл  — Tkinter GUI + встроенный NSIS-компилятор + CLI-режимы.

Самотест: ``vInstallerCreator.exe --selftest`` возвращает 0, если ядро
работоспособно (GUI не требуется).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback

# --- импорты core (работают и из исходников, и из PyInstaller-bundle) -----
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_HERE, "src") if os.path.isdir(os.path.join(_HERE, "src")) else _HERE
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

try:
    from src import core  # запуск из vinstaller/
except ImportError:
    import core  # PyInstaller flat layout / запуск из src/

APP_TITLE = f"{core.APP_NAME} {core.APP_VERSION}"


def resource_path(rel):
    """Путь к файлу внутри bundle (PyInstaller) или рядом со скриптом."""
    base = getattr(sys, "_MEIPASS", _HERE)
    p = os.path.join(base, rel)
    if os.path.exists(p):
        return p
    return os.path.join(_HERE, rel)


# ---------------------------------------------------------------------------
# Поиск компилятора NSIS (makensis)
# ---------------------------------------------------------------------------

NSIS_CANDIDATES = [
    r"C:\Program Files\NSIS\makensis.exe",
    r"C:\Program Files (x86)\NSIS\makensis.exe",
    r"C:\NSIS\makensis.exe",
]


def find_makensis(extra_path=""):
    for c in ([extra_path] if extra_path else []) + NSIS_CANDIDATES:
        if c and os.path.isfile(c):
            return c
    w = shutil.which("makensis")
    if w:
        return w
    return ""


def compile_installer(nsi_path, makensis="", log_cb=None, workdir=None):
    """Запускает makensis для nsi_path. Возвращает (rc, текст_лога)."""
    mk = makensis or find_makensis()
    if not mk:
        msg = ("NSIS (makensis) не найден. Установите NSIS 3.x с https://nsis.sourceforge.io "
               "или укажите путь к makensis.exe в настройках.")
        if log_cb:
            log_cb(msg)
        return 127, msg
    workdir = workdir or os.path.dirname(os.path.abspath(nsi_path))
    # /V4 — уровень детализации лога; на Unix-сборках makensis понимает только -V4
    verbose = "/V4" if mk.lower().endswith(".exe") else "-V4"
    cmd = [mk, verbose, nsi_path]
    proc = subprocess.Popen(cmd, cwd=workdir, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace")
    lines = []
    assert proc.stdout is not None
    for ln in proc.stdout:
        lines.append(ln.rstrip())
        if log_cb:
            log_cb(ln.rstrip())
    rc = proc.wait()
    return rc, "\n".join(lines)


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

def run_gui():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, colorchooser

    proj = core.default_project()
    proj_path = None

    root = tk.Tk()
    root.title(APP_TITLE)
    root.geometry("1024x720")
    try:
        ic = resource_path(os.path.join("assets", "app.ico"))
        if os.path.isfile(ic):
            root.iconbitmap(ic)
    except Exception:
        pass

    state = {"makensis": find_makensis(), "proj": proj}

    # ---------------- helpers --------------------------------------------
    def set_project(new_proj, path=None):
        nonlocal proj, proj_path
        state["proj"] = new_proj
        proj = new_proj
        proj_path = path
        rebuild_all()

    def get_meta():
        return state["proj"]["meta"]

    # ---------------- Notebook structure ---------------------------------
    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True, padx=6, pady=(6, 0))

    def make_tab(title):
        f = ttk.Frame(nb, padding=10)
        nb.add(f, text=title)
        return f

    tab_general = make_tab("Основное")
    tab_setup = make_tab("Установка")
    tab_files = make_tab("Файлы и компоненты")
    tab_short = make_tab("Ярлыки и реестр")
    tab_ui = make_tab("Интерфейс")
    tab_pages = make_tab("Страницы мастера")
    tab_scripts = make_tab("Скрипты")
    tab_build = make_tab("Сборка")

    # ================= Основное ==========================================
    g = ttk.LabelFrame(tab_general, text="Сведения о программе", padding=10)
    g.pack(fill="x")
    meta_vars = {}

    def add_field(frame, row, label, key, width=52):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=3)
        v = tk.StringVar()
        e = ttk.Entry(frame, textvariable=v, width=width)
        e.grid(row=row, column=1, sticky="we", pady=3)
        meta_vars[key] = v
        return v

    add_field(g, 0, "Название программы:", "name")
    add_field(g, 1, "Короткое имя (латиница):", "short_name")
    add_field(g, 2, "Версия (1.0.0):", "version")
    add_field(g, 3, "Издатель:", "publisher")
    add_field(g, 4, "Копирайт:", "copyright")
    add_field(g, 5, "Комментарий (FileDescription):", "comments")
    add_field(g, 6, "Домашняя страница (URL):", "url_info")
    add_field(g, 7, "Сайт обновлений:", "url_update")
    add_field(g, 8, "README / ссылка после установки:", "url_readme")
    add_field(g, 9, "Сборка (build):", "build")
    g.columnconfigure(1, weight=1)

    rowi = 10
    icon_var = tk.StringVar(); meta_vars["icon"] = icon_var
    ttk.Label(g, text="Иконка установщика (.ico):").grid(row=rowi, column=0, sticky="w", pady=3)
    fe = ttk.Frame(g); fe.grid(row=rowi, column=1, sticky="we")
    ttk.Entry(fe, textvariable=icon_var, width=44).pack(side="left", fill="x", expand=True)
    ttk.Button(fe, text="Обзор…", command=lambda: pick_file(icon_var, [("ICO", "*.ico")])).pack(side="left", padx=4)

    lic_var = tk.StringVar(); meta_vars["license_file"] = lic_var
    rowi += 1
    ttk.Label(g, text="Файл лицензии (.txt/.rtf):").grid(row=rowi, column=0, sticky="w", pady=3)
    fe = ttk.Frame(g); fe.grid(row=rowi, column=1, sticky="we")
    ttk.Entry(fe, textvariable=lic_var, width=44).pack(side="left", fill="x", expand=True)
    ttk.Button(fe, text="Обзор…", command=lambda: pick_file(lic_var, [("Текст", "*.txt *.rtf")])).pack(side="left", padx=4)

    rowi += 1
    lang_frame = ttk.Frame(g); lang_frame.grid(row=rowi, column=1, sticky="w", pady=6)
    lang_var = tk.StringVar(); meta_vars["language"] = lang_var
    fb_var = tk.StringVar(); meta_vars["fallback_language"] = fb_var
    ttk.Label(lang_frame, text="Язык мастера:").pack(side="left")
    langs = [(code, loc["label"]) for code, loc in core.LOCALES.items()]
    ttk.OptionMenu(lang_frame, lang_var, "ru", *[l for _, l in langs]).pack(side="left", padx=4)
    ttk.Label(lang_frame, text="Резервный:").pack(side="left", padx=(12, 0))
    ttk.OptionMenu(lang_frame, fb_var, "en", *[l for _, l in langs]).pack(side="left", padx=4)

    multiuser_var = tk.BooleanVar(); meta_vars["multiuser"] = multiuser_var
    ttk.Checkbutton(g, text="MultiUser.nsh (установка per-user/per-machine)",
                    variable=multiuser_var).grid(row=rowi, column=0, sticky="w")

    def pick_file(var, types):
        p = filedialog.askopenfilename(filetypes=types + [("Все", "*.*")])
        if p:
            var.set(p)

    # ================= Установка =========================================
    s = state["proj"]["setup"]
    sf = ttk.LabelFrame(tab_setup, text="Параметры установки", padding=10)
    sf.pack(fill="x")
    setup_vars = {}

    def add_setup_field(row, label, key, width=48):
        ttk.Label(sf, text=label).grid(row=row, column=0, sticky="w", pady=3)
        v = tk.StringVar()
        ttk.Entry(sf, textvariable=v, width=width).grid(row=row, column=1, sticky="we", pady=3)
        setup_vars[key] = v

    add_setup_field(0, "Папка по умолчанию:", "default_dir")
    ttk.Label(sf, text="Разрядность:").grid(row=1, column=0, sticky="w")
    arch_var = tk.StringVar(); setup_vars["arch"] = arch_var
    ar = ttk.Frame(sf); ar.grid(row=1, column=1, sticky="w")
    for val, lbl in (("x86", "32-bit (x86)"), ("x64", "64-bit (x64)")):
        ttk.Radiobutton(ar, text=lbl, value=val, variable=arch_var).pack(side="left", padx=6)

    ttk.Label(sf, text="Права (RequestExecutionLevel):").grid(row=2, column=0, sticky="w")
    lvl_var = tk.StringVar(); setup_vars["exec_level"] = lvl_var
    lv = ttk.Frame(sf); lv.grid(row=2, column=1, sticky="w")
    for val, lbl in (("auto", "auto"), ("admin", "администратор"), ("highest", "highest"),
                     ("user", "обычный пользователь"), ("lock", "lock")):
        ttk.Radiobutton(lv, text=lbl, value=val, variable=lvl_var).pack(side="left", padx=3)

    chk_mutex = tk.BooleanVar(); setup_vars["check_mutex"] = chk_mutex
    chk_root = tk.BooleanVar(); setup_vars["allow_root"] = chk_root
    chk_detect = tk.BooleanVar(); setup_vars["detect_old_version"] = chk_detect
    ttk.Checkbutton(sf, text="Блокировать второй экземпляр (mutex)", variable=chk_mutex)\
        .grid(row=3, column=1, sticky="w")
    ttk.Checkbutton(sf, text="Разрешить установку в корень диска", variable=chk_root)\
        .grid(row=4, column=1, sticky="w")
    ttk.Checkbutton(sf, text="Определять старую версию", variable=chk_detect)\
        .grid(row=5, column=1, sticky="w")

    ttk.Label(sf, text="Режим обновления:").grid(row=6, column=0, sticky="w")
    upg_var = tk.StringVar(); setup_vars["upgrade_mode"] = upg_var
    ttk.OptionMenu(sf, upg_var, "ask", "ask", "uninstall_first", "keep").grid(row=6, column=1, sticky="w")

    ttk.Label(sf, text="Закрывать приложения (имена окон через запятую):").grid(row=7, column=0, sticky="w")
    closeapps_var = tk.StringVar(); setup_vars["close_apps_txt"] = closeapps_var
    ttk.Entry(sf, textvariable=closeapps_var, width=48).grid(row=7, column=1, sticky="we")

    reqf = ttk.LabelFrame(tab_setup, text="Требования", padding=10)
    reqf.pack(fill="x", pady=8)
    vc_var = tk.BooleanVar(); setup_vars["vc_redist"] = vc_var
    ttk.Checkbutton(reqf, text="Visual C++ Redistributable (проверять/ставить после)", variable=vc_var).grid(row=0, column=0, sticky="w")
    ttk.Label(reqf, text=".NET Framework (мин.):").grid(row=1, column=0, sticky="w", pady=3)
    dotnet_var = tk.StringVar(); setup_vars["dotnet"] = dotnet_var
    ttk.OptionMenu(reqf, dotnet_var, "", "", "4.5.2", "4.6", "4.7.2", "4.8").grid(row=1, column=1, sticky="w")
    ttk.Label(reqf, text="Windows не ниже:").grid(row=2, column=0, sticky="w")
    osmin_var = tk.StringVar(); setup_vars["os_min"] = osmin_var
    ttk.OptionMenu(reqf, osmin_var, "", "", "win7", "win8", "win8.1", "win10").grid(row=2, column=1, sticky="w")

    compf = ttk.LabelFrame(tab_setup, text="Сжатие", padding=10)
    compf.pack(fill="x", pady=8)
    cmeth_var = tk.StringVar(); setup_vars["comp_method"] = cmeth_var
    solid_var = tk.BooleanVar(); setup_vars["comp_solid"] = solid_var
    dict_var = tk.StringVar(); setup_vars["comp_dict"] = dict_var
    ttk.Label(compf, text="Метод:").grid(row=0, column=0, sticky="w")
    ttk.OptionMenu(compf, cmeth_var, "lzma", "zlib", "bzip2", "lzma").grid(row=0, column=1, sticky="w")
    ttk.Checkbutton(compf, text="Solid-архив", variable=solid_var).grid(row=0, column=2, sticky="w", padx=8)
    ttk.Label(compf, text="Словарь, МБ:").grid(row=0, column=3, sticky="e")
    ttk.Entry(compf, textvariable=dict_var, width=6).grid(row=0, column=4, sticky="w")
    sf.columnconfigure(1, weight=1)

    # ================= Файлы и компоненты =================================
    ff = ttk.Frame(tab_files)
    ff.pack(fill="both", expand=True)
    seclist_frame = ttk.LabelFrame(ff, text="Секции (компоненты)", padding=6)
    seclist_frame.pack(side="left", fill="y", padx=(0, 8))
    sec_list = tk.Listbox(seclist_frame, width=34, height=18)
    sec_list.pack(fill="both", expand=True)
    secbtns = ttk.Frame(seclist_frame); secbtns.pack(fill="x", pady=4)
    ttk.Button(secbtns, text="Добавить", command=lambda: add_section()).pack(side="left", padx=2)
    ttk.Button(secbtns, text="Удалить", command=lambda: del_section()).pack(side="left", padx=2)

    detail_frame = ttk.LabelFrame(ff, text="Содержимое секции", padding=6)
    detail_frame.pack(side="left", fill="both", expand=True)
    sec_vars = {"name": tk.StringVar(), "flags": tk.StringVar(), "size": tk.StringVar()}
    ttk.Label(detail_frame, text="Отображаемое имя:").grid(row=0, column=0, sticky="w")
    ttk.Entry(detail_frame, textvariable=sec_vars["name"], width=40).grid(row=0, column=1, columnspan=2, sticky="we")
    ttk.Label(detail_frame, text="Флаги (RO/RD/RE/-):").grid(row=1, column=0, sticky="w")
    ttk.Entry(detail_frame, textvariable=sec_vars["flags"], width=12).grid(row=1, column=1, sticky="w")
    ttk.Label(detail_frame, text="Размер, КБ:").grid(row=1, column=2, sticky="e")
    ttk.Entry(detail_frame, textvariable=sec_vars["size"], width=10).grid(row=2, column=2, sticky="w")
    types_frame = ttk.LabelFrame(detail_frame, text="Входит в типы установки")
    types_frame.grid(row=2, column=0, columnspan=2, sticky="w", pady=4)
    sectype_vars = []

    file_tree = ttk.Treeview(detail_frame, columns=("src", "dest", "kind"), height=9)
    file_tree.heading("src", text="Исходный файл/папка")
    file_tree.heading("dest", text="Подпапка назначения")
    file_tree.heading("kind", text="Тип")
    file_tree.column("#0", width=1, stretch=False)
    file_tree.column("src", width=380)
    file_tree.column("dest", width=160)
    file_tree.column("kind", width=70)
    file_tree.grid(row=3, column=0, columnspan=3, sticky="nsew", pady=6)
    detail_frame.rowconfigure(3, weight=1)
    detail_frame.columnconfigure(1, weight=1)
    fbrow = ttk.Frame(detail_frame); fbrow.grid(row=4, column=0, columnspan=3, sticky="we")
    ttk.Button(fbrow, text="Добавить файл…", command=lambda: add_sec_file(False)).pack(side="left", padx=2)
    ttk.Button(fbrow, text="Добавить папку…", command=lambda: add_sec_file(True)).pack(side="left", padx=2)
    ttk.Button(fbrow, text="Удалить выбранное", command=lambda: del_sec_file()).pack(side="left", padx=2)

    def current_sec():
        sel = sec_list.curselection()
        if not sel:
            return None
        return state["proj"]["sections"][sel[0]]

    def refresh_sec_list():
        sec_list.delete(0, "end")
        for sc in state["proj"]["sections"]:
            sec_list.insert("end", f'{sc["id"]} — {sc["name"]}')

    def load_sec_detail(*_):
        sc = current_sec()
        for w in types_frame.winfo_children():
            w.destroy()
        sectype_vars.clear()
        if not sc:
            return
        sec_vars["name"].set(sc["name"])
        sec_vars["flags"].set(sc.get("flags", ""))
        sec_vars["size"].set(str(sc.get("size_kb", 0)))
        for i, it in enumerate(state["proj"]["install_types"]):
            v = tk.BooleanVar(value=i in sc.get("types", []))
            sectype_vars.append(v)
            ttk.Checkbutton(types_frame, text=it["name"], variable=v).pack(side="left", padx=4)
        file_tree.delete(*file_tree.get_children())
        for fe in sc.get("files", []):
            file_tree.insert("", "end", values=(fe.get("src", ""), fe.get("dest", ""), fe.get("kind", "file")))
        for rf in sc.get("folders", []):
            file_tree.insert("", "end", values=(rf.get("src", ""), rf.get("dest", ""), "folder"))

    def apply_sec_detail():
        sc = current_sec()
        if not sc:
            return
        sc["name"] = sec_vars["name"].get() or sc["id"]
        sc["flags"] = sec_vars["flags"].get().strip().upper()
        try:
            sc["size_kb"] = int(sec_vars["size"].get() or 0)
        except ValueError:
            sc["size_kb"] = 0
        sc["types"] = [i for i, v in enumerate(sectype_vars) if v.get()]
        files, folders = [], []
        for iid in file_tree.get_children():
            src, dest, kind = file_tree.item(iid, "values")
            if kind == "folder":
                folders.append({"src": src, "dest": dest})
            else:
                files.append({"src": src, "dest": dest,
                              "kind": "exe" if src.lower().endswith(".exe") else "file"})
        sc["files"], sc["folders"] = files, folders
        refresh_sec_list()

    def add_section():
        name = simple_input("Новая секция", "ID (латиница):", "component")
        if not name:
            return
        if any(s["id"] == name for s in state["proj"]["sections"]):
            messagebox.showerror(APP_TITLE, "Такой ID уже есть.")
            return
        state["proj"]["sections"].append({"id": name, "name": name, "size_kb": 0,
                                          "flags": "", "types": [0], "files": [], "folders": []})
        refresh_sec_list()
        sec_list.selection_clear(0, "end"); sec_list.selection_set(len(state["proj"]["sections"]) - 1)

    def del_section():
        sc = current_sec()
        if not sc:
            return
        if not messagebox.askyesno(APP_TITLE, f"Удалить секцию «{sc['id']}»?"):
            return
        state["proj"]["sections"].remove(sc)
        refresh_sec_list()

    def add_sec_file(isdir):
        sc = current_sec()
        if not sc:
            messagebox.showinfo(APP_TITLE, "Сначала выберите секцию.")
            return
        if isdir:
            p = filedialog.askdirectory()
            if p:
                sc.setdefault("folders", []).append({"src": p, "dest": ""})
        else:
            ps = filedialog.askopenfilenames()
            for p in ps:
                sc.setdefault("files", []).append({"src": p, "dest": "",
                                                   "kind": "exe" if p.lower().endswith(".exe") else "file"})
        load_sec_detail()

    def del_sec_file():
        sc = current_sec()
        if not sc:
            return
        for iid in file_tree.selection():
            file_tree.delete(iid)
        apply_sec_detail()

    sec_list.bind("<<ListboxSelect>>", load_sec_detail)
    for k in ("default_dir",):
        pass

    itf = ttk.LabelFrame(tab_files, text="Типы установки", padding=6)
    itf.pack(fill="x", pady=8)
    it_tree = ttk.Treeview(itf, columns=("name", "sections"), height=4)
    it_tree.heading("name", text="Тип"); it_tree.heading("sections", text="Секции (через запятую)")
    it_tree.column("#0", width=1, stretch=False)
    it_tree.column("name", width=180); it_tree.column("sections", width=380)
    it_tree.pack(fill="x")

    def refresh_types():
        it_tree.delete(*it_tree.get_children())
        for t in state["proj"]["install_types"]:
            it_tree.insert("", "end", values=(t["name"], t["sections"]))

    def edit_type(event):
        sel = it_tree.selection()
        if not sel:
            return
        idx = it_tree.index(sel[0])
        t = state["proj"]["install_types"][idx]
        nm = simple_input("Тип установки", "Название:", t["name"])
        if nm is None:
            return
        secs = simple_input("Тип установки", "Секции (* или id,id):", t["sections"])
        if secs is None:
            return
        t["name"], t["sections"] = nm, secs
        refresh_types()

    it_tree.bind("<Double-1>", edit_type)

    # ================= Ярлыки и реестр ====================================
    shf = ttk.LabelFrame(tab_short, text="Ярлыки", padding=6)
    shf.pack(fill="both", expand=True)
    sh_tree = ttk.Treeview(shf, columns=("where", "name", "target", "section"), height=7)
    for col, txt, w in (("#0", "", 1), ("where", "Где", 120), ("name", "Имя", 200),
                        ("target", "Цель", 260), ("section", "Секция", 100)):
        sh_tree.heading(col, text=txt); sh_tree.column(col, width=w)
    sh_tree.pack(fill="both", expand=True)
    shbtns = ttk.Frame(shf); shbtns.pack(fill="x", pady=3)

    def refresh_shortcuts():
        sh_tree.delete(*sh_tree.get_children())
        for sc in state["proj"]["shortcuts"]:
            sh_tree.insert("", "end", values=(sc.get("where"), sc.get("name"),
                                               sc.get("target"), sc.get("section")))

    def add_shortcut():
        d = simple_dialog("Новый ярлык",
                          [("Имя", "{APPNAME}"), ("Где", "startmenu"),
                           ("Цель ({EXE} = главный exe)", "{EXE}"),
                           ("Аргументы", ""), ("Секция", "shortcuts"),
                           ("Описание", "")])
        if not d:
            return
        state["proj"]["shortcuts"].append({
            "section": d["Секция"] or "shortcuts", "where": d["Где"] or "startmenu",
            "name": d["Имя"], "target": d["Цель ({EXE} = главный exe)"] or "{EXE}",
            "args": d["Аргументы"], "icon": "", "icon_index": 0, "description": d["Описание"]})
        refresh_shortcuts()

    def del_shortcut():
        for iid in list(sh_tree.selection()):
            state["proj"]["shortcuts"].pop(sh_tree.index(iid))
        refresh_shortcuts()

    ttk.Button(shbtns, text="Добавить ярлык", command=add_shortcut).pack(side="left", padx=2)
    ttk.Button(shbtns, text="Удалить", command=del_shortcut).pack(side="left", padx=2)

    rgf = ttk.LabelFrame(tab_short, text="Записи реестра", padding=6)
    rgf.pack(fill="both", expand=True, pady=8)
    rg_tree = ttk.Treeview(rgf, columns=("root", "key", "value", "type", "data", "section"), height=7)
    for col, txt, w in (("#0", "", 1), ("root", "Корень", 70), ("key", "Ключ", 260),
                        ("value", "Значение", 110), ("type", "Тип", 70),
                        ("data", "Данные", 160), ("section", "Секция", 80)):
        rg_tree.heading(col, text=txt); rg_tree.column(col, width=w)
    rg_tree.pack(fill="both", expand=True)
    rgbtns = ttk.Frame(rgf); rgbtns.pack(fill="x", pady=3)

    def refresh_reg():
        rg_tree.delete(*rg_tree.get_children())
        for e in state["proj"]["registry"]["entries"]:
            rg_tree.insert("", "end", values=(e.get("root"), e.get("key"), e.get("value"),
                                              e.get("type"), e.get("data"), e.get("section", "")))

    def add_reg():
        d = simple_dialog("Запись реестра",
                          [("Корень (HKLM/HKCU/HKCR)", "HKLM"),
                           ("Ключ", r"Software\{PUBLISHER}\{APPNAME}"),
                           ("Имя значения", ""), ("Тип (str/expand/dword/none)", "str"),
                           ("Данные", ""), ("Секция (необязательно)", "")])
        if not d:
            return
        state["proj"]["registry"]["entries"].append({
            "root": d["Корень (HKLM/HKCU/HKCR)"], "key": d["Ключ"],
            "value": d["Имя значения"], "type": d["Тип (str/expand/dword/none)"],
            "data": d["Данные"], "section": d["Секция (необязательно)"]})
        refresh_reg()

    def del_reg():
        for iid in list(rg_tree.selection()):
            state["proj"]["registry"]["entries"].pop(rg_tree.index(iid))
        refresh_reg()

    ttk.Button(rgbtns, text="Добавить запись", command=add_reg).pack(side="left", padx=2)
    ttk.Button(rgbtns, text="Удалить", command=del_reg).pack(side="left", padx=2)

    exef = ttk.LabelFrame(tab_short, text="Команды запуска", padding=6)
    exef.pack(fill="x", pady=8)
    run_install_var = tk.StringVar()
    run_uninst_var = tk.StringVar()
    startup_var = tk.StringVar()
    ttk.Label(exef, text="Выполнить при установке (cmd; ; разделитель):").grid(row=0, column=0, sticky="w")
    ttk.Entry(exef, textvariable=run_install_var, width=60).grid(row=0, column=1, sticky="we")
    ttk.Label(exef, text="Выполнить при удалении:").grid(row=1, column=0, sticky="w")
    ttk.Entry(exef, textvariable=run_uninst_var, width=60).grid(row=1, column=1, sticky="we")
    ttk.Label(exef, text="Автозапуск (Run key, cmd):").grid(row=2, column=0, sticky="w")
    ttk.Entry(exef, textvariable=startup_var, width=60).grid(row=2, column=1, sticky="we")
    exef.columnconfigure(1, weight=1)

    dirs_var = tk.StringVar()
    delf_var = tk.StringVar()
    doff = ttk.LabelFrame(tab_short, text="Доп. папки / удаление файлов", padding=6)
    doff.pack(fill="x", pady=4)
    ttk.Label(doff, text="Создать папки ($INSTDIR\\…):").grid(row=0, column=0, sticky="w")
    ttk.Entry(doff, textvariable=dirs_var, width=40).grid(row=0, column=1, sticky="we")
    ttk.Label(doff, text="Удалить при деинсталляции:").grid(row=1, column=0, sticky="w")
    ttk.Entry(doff, textvariable=delf_var, width=40).grid(row=1, column=1, sticky="we")
    doff.columnconfigure(1, weight=1)

    # ================= Интерфейс ==========================================
    uif = ttk.LabelFrame(tab_ui, text="Страницы мастера", padding=10)
    uif.pack(fill="x")
    page_vars = {}
    page_labels = {
        "welcome": "Приветственная страница", "license": "Страница лицензии",
        "components": "Выбор компонентов", "directory": "Выбор папки",
        "verify": "Подтверждение перед установкой", "instfiles": "Процесс установки",
        "finish": "Завершение установки", "uninstall_confirm": "Подтверждение удаления",
        "uninstall_finish": "Завершение удаления",
    }
    for i, (k, lbl) in enumerate(page_labels.items()):
        v = tk.BooleanVar()
        page_vars[k] = v
        ttk.Checkbutton(uif, text=lbl, variable=v).grid(row=i // 3, column=i % 3, sticky="w", padx=8, pady=3)

    stf = ttk.LabelFrame(tab_ui, text="Стиль и изображения", padding=10)
    stf.pack(fill="x", pady=8)
    style_var = tk.StringVar(); wizard_var = tk.StringVar()
    license_mode_var = tk.StringVar(); branding_var = tk.StringVar()
    details_var = tk.StringVar(); rtl_var = tk.BooleanVar(); winicon_var = tk.BooleanVar()
    header_img_var = tk.StringVar(); sidebar_img_var = tk.StringVar()
    completed_var = tk.StringVar()

    ttk.Label(stf, text="Раскладка мастера:").grid(row=0, column=0, sticky="w")
    ttk.OptionMenu(stf, wizard_var, "modern", "modern", "classic").grid(row=0, column=1, sticky="w")
    ttk.Label(stf, text="Лицензия:").grid(row=0, column=2, sticky="w")
    ttk.OptionMenu(stf, license_mode_var, "checkbox", "checkbox", "radiobuttons", "off").grid(row=0, column=3, sticky="w")
    ttk.Label(stf, text="Детали установки:").grid(row=1, column=0, sticky="w", pady=4)
    ttk.OptionMenu(stf, details_var, "hide", "hide", "show", "nevershow").grid(row=1, column=1, sticky="w")
    ttk.Label(stf, text="BrandingText:").grid(row=1, column=2, sticky="w")
    ttk.Entry(stf, textvariable=branding_var, width=30).grid(row=1, column=3, sticky="we")
    ttk.Checkbutton(stf, text="RTL-интерфейс", variable=rtl_var).grid(row=2, column=0, sticky="w")
    ttk.Checkbutton(stf, text="Иконка в окне", variable=winicon_var).grid(row=2, column=1, sticky="w")
    ttk.Label(stf, text="Header BMP (пусто = авто):").grid(row=3, column=0, sticky="w", pady=4)
    he = ttk.Frame(stf); he.grid(row=3, column=1, columnspan=3, sticky="we")
    ttk.Entry(he, textvariable=header_img_var, width=48).pack(side="left", fill="x", expand=True)
    ttk.Button(he, text="Обзор…", command=lambda: pick_file(header_img_var, [("BMP", "*.bmp")])).pack(side="left", padx=4)
    ttk.Label(stf, text="Sidebar BMP (пусто = авто):").grid(row=4, column=0, sticky="w")
    se2 = ttk.Frame(stf); se2.grid(row=4, column=1, columnspan=3, sticky="we")
    ttk.Entry(se2, textvariable=sidebar_img_var, width=48).pack(side="left", fill="x", expand=True)
    ttk.Button(se2, text="Обзор…", command=lambda: pick_file(sidebar_img_var, [("BMP", "*.bmp")])).pack(side="left", padx=4)
    ttk.Label(stf, text="CompletedText:").grid(row=5, column=0, sticky="w")
    ttk.Entry(stf, textvariable=completed_var, width=60).grid(row=5, column=1, columnspan=3, sticky="we")
    stf.columnconfigure(3, weight=1)

    colf = ttk.LabelFrame(tab_ui, text="Цвета интерфейса", padding=10)
    colf.pack(fill="x", pady=8)
    color_vars = {}

    def color_btn(frame, key, label, colr):
        v = tk.StringVar(value=colr)
        color_vars[key] = v

        def choose():
            c = colorchooser.askcolor(color=v.get(), title=label)
            if c and c[1]:
                v.set(c[1].upper())
                sw.configure(bg=v.get())

        b = ttk.Frame(frame)
        b.pack(side="left", padx=6, pady=4)
        sw = tk.Canvas(b, width=18, height=18, highlightthickness=1, bg=colr)
        sw.pack(side="left")
        ttk.Label(b, text=label).pack(side="left", padx=4)
        ttk.Button(b, text="…", width=3, command=choose).pack(side="left")

    for key, label in (("header_bg", "Шапка"), ("sidebar_bg", "Сайдбар 1"),
                       ("sidebar_bg2", "Сайдбар 2"), ("sidebar_fg", "Текст сайдбара"),
                       ("wnd_bg", "Фон окна"), ("button_color", "Акцент")):
        color_btn(colf, key, label, core.DEFAULT_UI_COLORS[key])

    # ================= Скрипты ============================================
    scf = ttk.LabelFrame(tab_scripts, text="Нижеследующий код вставляется в NSI-скрипт", padding=6)
    scf.pack(fill="both", expand=True)
    script_texts = {}
    for key, label in (("pre_init", ".onInit (pre_init)"),
                       ("leave_directory", "DirectoryLeave"),
                       ("custom_function", "Custom Function"),
                       ("uninstall_custom", "Uninstall custom")):
        fr = ttk.Frame(scf); fr.pack(fill="x", pady=3)
        ttk.Label(fr, text=label, width=22).pack(side="top", anchor="w")
        tx = tk.Text(fr, height=5, width=100)
        tx.pack(fill="x")
        script_texts[key] = tx

    # ================= Сборка =============================================
    bf = ttk.Frame(tab_build, padding=10)
    bf.pack(fill="both", expand=True)
    out_var = tk.StringVar()
    mk_var = tk.StringVar(value=state["makensis"])
    ttk.Label(bf, text="Имя итогового установщика:").pack(anchor="w")
    ttk.Entry(bf, textvariable=out_var, width=60).pack(anchor="w", pady=2)
    ttk.Label(bf, text="Путь к makensis(.exe):").pack(anchor="w", pady=(8, 0))
    mfr = ttk.Frame(bf); mfr.pack(anchor="w", fill="x")
    ttk.Entry(mfr, textvariable=mk_var, width=52).pack(side="left", fill="x")
    ttk.Button(mfr, text="Обзор…", command=lambda: pick_file(mk_var, [("makensis", "makensis*"), ("Все", "*.*")])).pack(side="left", padx=4)

    bbtns = ttk.Frame(bf); bbtns.pack(fill="x", pady=10)
    btn_gen = ttk.Button(bbtns, text="1. Сгенерировать NSI")
    btn_compile = ttk.Button(bbtns, text="2. Собрать EXE (NSIS)")
    btn_full = ttk.Button(bbtns, text="▶ Полный цикл: проверить → NSI → EXE")
    btn_gen.pack(side="left", padx=3); btn_compile.pack(side="left", padx=3); btn_full.pack(side="left", padx=3)

    build_log = tk.Text(bf, height=16, state="disabled", font=("Consolas", 9))
    build_log.pack(fill="both", expand=True)

    last_nsi = {"path": ""}

    def log(msg):
        build_log.configure(state="normal")
        build_log.insert("end", msg + "\n")
        build_log.see("end")
        build_log.configure(state="disabled")

    # ---------------- collect / apply project -----------------------------
    def apply_ui_to_project():
        p = state["proj"]
        m = p["meta"]
        for k, v in meta_vars.items():
            m[k] = v.get() if isinstance(v, tk.StringVar) else bool(v.get())
        svars = setup_vars
        p["setup"]["default_dir"] = svars["default_dir"].get() or p["setup"]["default_dir"]
        p["setup"]["arch"] = svars["arch"].get()
        p["setup"]["exec_level"] = svars["exec_level"].get()
        p["setup"]["check_mutex"] = bool(svars["check_mutex"].get())
        p["setup"]["allow_root"] = bool(svars["allow_root"].get())
        p["setup"]["detect_old_version"] = bool(svars["detect_old_version"].get())
        p["setup"]["upgrade_mode"] = svars["upgrade_mode"].get()
        p["setup"]["close_apps"] = [x.strip() for x in svars["close_apps_txt"].get().split(",") if x.strip()]
        p["setup"]["requires"] = {"vc_redist": bool(svars["vc_redist"].get()),
                                  "dotnet": svars["dotnet"].get(),
                                  "os_min": svars["os_min"].get()}
        p["compression"] = {"method": svars["comp_method"].get(),
                           "solid": bool(svars["comp_solid"].get()),
                           "dict_mb": int(svars["comp_dict"].get() or 8)}
        p["ui"]["wizard"] = wizard_var.get()
        p["ui"]["license_mode"] = license_mode_var.get()
        p["ui"]["details_show"] = details_var.get()
        p["ui"]["branding"] = branding_var.get()
        p["ui"]["rtl"] = bool(rtl_var.get())
        p["ui"]["window_icon"] = bool(winicon_var.get())
        p["ui"]["header_image"] = [header_img_var.get(), ""]
        p["ui"]["sidebar_image"] = [sidebar_img_var.get(), ""]
        p["ui"]["completed_text"] = completed_var.get()
        for k, v in color_vars.items():
            p["ui"]["colors"][k] = v.get()
        for k, v in page_vars.items():
            p["pages"][k] = bool(v.get())
        for k, tx in script_texts.items():
            p["scripts"][k] = tx.get("1.0", "end").rstrip("\n")
        p["output"]["filename"] = out_var.get() or p["output"]["filename"]
        ri = [c.strip() for c in run_install_var.get().split(";") if c.strip()]
        p["run"]["install_exec"] = [{"cmd": c, "section": "", "silent": True, "wait": False} for c in ri]
        ru = [c.strip() for c in run_uninst_var.get().split(";") if c.strip()]
        p["run"]["uninstall_exec"] = [{"cmd": c, "silent": True} for c in ru]
        p["run"]["startup_run"] = startup_var.get().strip()
        p["file_ops"]["dirs"] = [d.strip() for d in dirs_var.get().split(",") if d.strip()]
        p["file_ops"]["delete_files"] = [d.strip() for d in delf_var.get().split(",") if d.strip()]
        apply_sec_detail()
        state["makensis"] = mk_var.get()

    LANG_REV = {lbl: code for code, loc in core.LOCALES.items() for lbl in (loc["label"],)}

    def load_project_into_ui():
        p = state["proj"]
        for k, v in meta_vars.items():
            if isinstance(v, tk.StringVar):
                v.set(str(p["meta"].get(k, "")))
            else:
                v.set(bool(p["meta"].get(k, False)))
        lang_lbl = core.LOCALES.get(p["meta"].get("language", "ru"), {}).get("label", "English")
        meta_vars["language"].set(lang_lbl)
        fb_lbl = core.LOCALES.get(p["meta"].get("fallback_language", "en"), {}).get("label", "English")
        meta_vars["fallback_language"].set(fb_lbl)
        su = p["setup"]
        setup_vars["default_dir"].set(su["default_dir"])
        setup_vars["arch"].set(su["arch"])
        setup_vars["exec_level"].set(su["exec_level"])
        setup_vars["check_mutex"].set(su["check_mutex"])
        setup_vars["allow_root"].set(su["allow_root"])
        setup_vars["detect_old_version"].set(su["detect_old_version"])
        setup_vars["upgrade_mode"].set(su["upgrade_mode"])
        setup_vars["close_apps_txt"].set(", ".join(su.get("close_apps", [])))
        req = su.get("requires", {})
        setup_vars["vc_redist"].set(bool(req.get("vc_redist")))
        setup_vars["dotnet"].set(req.get("dotnet", ""))
        setup_vars["os_min"].set(req.get("os_min", ""))
        cp = p["compression"]
        setup_vars["comp_method"].set(cp["method"])
        setup_vars["comp_solid"].set(cp["solid"])
        setup_vars["comp_dict"].set(str(cp["dict_mb"]))
        ui = p["ui"]
        wizard_var.set(ui["wizard"]); license_mode_var.set(ui["license_mode"])
        details_var.set(ui["details_show"]); branding_var.set(ui["branding"])
        rtl_var.set(ui["rtl"]); winicon_var.set(ui["window_icon"])
        header_img_var.set((ui.get("header_image") or ["", ""])[0])
        sidebar_img_var.set((ui.get("sidebar_image") or ["", ""])[0])
        completed_var.set(ui.get("completed_text", ""))
        for k, v in color_vars.items():
            v.set(ui["colors"].get(k, "#000000"))
        for k, v in page_vars.items():
            v.set(bool(p["pages"].get(k)))
        for k, tx in script_texts.items():
            tx.delete("1.0", "end")
            tx.insert("1.0", p["scripts"].get(k, ""))
        out_var.set(p["output"]["filename"])
        run_install_var.set("; ".join(c["cmd"] for c in p["run"]["install_exec"]))
        run_uninst_var.set("; ".join(c["cmd"] for c in p["run"]["uninstall_exec"]))
        startup_var.set(p["run"].get("startup_run", ""))
        dirs_var.set(", ".join(p["file_ops"]["dirs"]))
        delf_var.set(", ".join(p["file_ops"]["delete_files"]))
        refresh_sec_list(); refresh_types(); refresh_shortcuts(); refresh_reg()
        if p["sections"]:
            sec_list.selection_set(0); load_sec_detail()
        root.title(f"{APP_TITLE} — {p['meta']['name']}" + (f" [{os.path.basename(proj_path)}]" if proj_path else ""))

    def rebuild_all():
        load_project_into_ui()

    # ---------------- actions ----------------------------------------------
    def new_project():
        if messagebox.askyesno(APP_TITLE, "Создать новый проект? Несохранённые изменения будут потеряны."):
            set_project(core.default_project(), None)

    def open_project():
        p = filedialog.askopenfilename(filetypes=[("vInstaller Project", "*.vicproj"), ("Все", "*.*")])
        if not p:
            return
        try:
            set_project(core.load_project(p), p)
            log(f"Проект открыт: {p}")
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Не удалось открыть проект:\n{e}")

    def save_project(as_new=False):
        apply_ui_to_project()
        global proj_path
        p = proj_path if (proj_path and not as_new) else \
            filedialog.asksaveasfilename(defaultextension=".vicproj",
                                        filetypes=[("vInstaller Project", "*.vicproj")],
                                        initialfile=re.sub(r"\W+", "_", state["proj"]["meta"]["name"]) + ".vicproj")
        if not p:
            return
        core.save_project(state["proj"], p)
        proj_path = p
        root.title(f"{APP_TITLE} — {state['proj']['meta']['name']} [{os.path.basename(p)}]")
        log(f"Проект сохранён: {p}")

    def validate(show_dialog=True):
        apply_ui_to_project()
        issues = core.validate_project(state["proj"])
        errs = [m for sev, m in issues if sev == "error"]
        warns = [m for sev, m in issues if sev == "warning"]
        for m in errs:
            log("✖ ОШИБКА: " + m)
        for m in warns:
            log("⚠ предупреждение: " + m)
        if not issues:
            log("✔ Проверка проекта: ошибок нет.")
        if show_dialog:
            if errs:
                messagebox.showerror(APP_TITLE, "Найдены ошибки:\n\n" + "\n".join(errs[:12]))
            elif warns:
                messagebox.showwarning(APP_TITLE, "Есть предупреждения:\n\n" + "\n".join(warns[:12]))
            else:
                messagebox.showinfo(APP_TITLE, "Проект корректен ✔")
        return not errs

    def gen_nsi():
        apply_ui_to_project()
        if not validate(show_dialog=False):
            messagebox.showerror(APP_TITLE, "Исправьте ошибки проекта (см. журнал сборки).")
            return ""
        wd = os.path.dirname(proj_path) if proj_path else os.getcwd()
        out = os.path.join(wd, re.sub(r"\W+", "_", state["proj"]["meta"]["name"]) + ".nsi")
        try:
            path, _ = core.generate_nsi(state["proj"], out, workdir=wd)
            last_nsi["path"] = path
            log("NSI сгенерирован: " + path)
            return path
        except Exception as e:
            log("Ошибка генерации NSI: " + str(e))
            messagebox.showerror(APP_TITLE, f"Ошибка генерации NSI:\n{e}")
            return ""

    def do_compile():
        nsi = last_nsi["path"] or gen_nsi()
        if not nsi:
            messagebox.showerror(APP_TITLE, "Сначала сгенерируйте NSI-скрипт.")
            return
        mk = mk_var.get() or find_makensis()
        if not mk:
            messagebox.showerror(APP_TITLE,
                                 "makensis не найден. Установите NSIS 3.x и укажите путь к makensis.exe.")
            log("NSIS не найден — сборка невозможна.")
            return
        log(f"Запуск: {mk} {nsi}")
        nb.index(tab_build)

        def worker():
            rc, text = compile_installer(nsi, mk, log_cb=lambda l: root.after(0, log, l))
            def done():
                if rc == 0:
                    outfile = os.path.join(os.path.dirname(nsi),
                                           core.expand_placeholders(state["proj"]["output"]["filename"], state["proj"]))
                    log(f"✔ УСТАНОВЩИХ ГОТОВ: {outfile}")
                    messagebox.showinfo(APP_TITLE, f"Установщик собран:\n{outfile}")
                else:
                    log(f"✖ NSIS завершился с кодом {rc}")
                    messagebox.showerror(APP_TITLE, f"Ошибка компиляции NSIS (код {rc}). См. журнал.")
            root.after(0, done)
        threading.Thread(target=worker, daemon=True).start()

    def full_cycle():
        nb.index(tab_build)
        if validate(show_dialog=False):
            if gen_nsi():
                do_compile()

    btn_gen.configure(command=gen_nsi)
    btn_compile.configure(command=do_compile)
    btn_full.configure(command=full_cycle)

    # ---------------- small dialogs ----------------------------------------
    def simple_input(title, label, initial=""):
        d = tk.Toplevel(root); d.title(title); d.transient(root); d.grab_set()
        v = tk.StringVar(value=initial)
        ttk.Label(d, text=label).pack(padx=10, pady=(10, 2))
        e = ttk.Entry(d, textvariable=v, width=44); e.pack(padx=10, pady=2)
        res = {}

        def yes(event=None):
            res["v"] = v.get(); d.destroy()
        e.bind("<Return>", yes)
        bf2 = ttk.Frame(d); bf2.pack(pady=8)
        ttk.Button(bf2, text="OK", command=yes).pack(side="left", padx=4)
        ttk.Button(bf2, text="Отмена", command=lambda: (res.pop('v', None), d.destroy())).pack(side="left")
        e.focus_force()
        d.wait_window()
        return res.get("v")

    def simple_dialog(title, fields):
        d = tk.Toplevel(root); d.title(title); d.transient(root); d.grab_set()
        vs = {}
        grid = ttk.Frame(d, padding=10); grid.pack()
        for i, (lbl, init) in enumerate(fields):
            ttk.Label(grid, text=lbl).grid(row=i, column=0, sticky="w", pady=2)
            v = tk.StringVar(value=init); vs[lbl] = v
            ttk.Entry(grid, textvariable=v, width=48).grid(row=i, column=1, sticky="we", pady=2)
        res = {}

        def yes():
            res.update({k: v.get() for k, v in vs.items()}); d.destroy()
        bf2 = ttk.Frame(d); bf2.pack(pady=6)
        ttk.Button(bf2, text="OK", command=yes).pack(side="left", padx=4)
        ttk.Button(bf2, text="Отмена", command=d.destroy).pack(side="left")
        d.wait_window()
        return res or None

    # ---------------- menu --------------------------------------------------
    menubar = tk.Menu(root)
    fm = tk.Menu(menubar, tearoff=0)
    fm.add_command(label="Новый проект", accelerator="Ctrl+N", command=new_project)
    fm.add_command(label="Открыть…", accelerator="Ctrl+O", command=open_project)
    fm.add_command(label="Сохранить", accelerator="Ctrl+S", command=lambda: save_project(False))
    fm.add_command(label="Сохранить как…", accelerator="Ctrl+Shift+S", command=lambda: save_project(True))
    fm.add_separator()
    fm.add_command(label="Проверить проект", command=lambda: validate())
    fm.add_command(label="Сгенерировать NSI", command=gen_nsi)
    fm.add_command(label="Собрать EXE", command=do_compile)
    fm.add_separator()
    fm.add_command(label="Выход", command=root.destroy)
    menubar.add_cascade(label="Файл", menu=fm)
    hb = tk.Menu(menubar, tearoff=0)
    hb.add_command(label="О программе", command=lambda: messagebox.showinfo(
        APP_TITLE, f"{APP_TITLE}\n\nГенератор графических установщиков Windows на базе NSIS.\n"
                   f"Проекты: *.vicproj • Сборка: makensis.exe (NSIS 3)\n\n"
                   f"Собрано CREATE.py • {core.APP_VERSION}"))
    menubar.add_cascade(label="Справка", menu=hb)
    root.configure(menu=menubar)
    root.bind("<Control-n>", lambda e: new_project())
    root.bind("<Control-o>", lambda e: open_project())
    root.bind("<Control-s>", lambda e: save_project(False))

    status = ttk.Label(root, text="Готов. NSIS: " + (state["makensis"] or "НЕ НАЙДЕН — установите NSIS 3.x"),
                       relief="sunken", anchor="w")
    status.pack(fill="x", side="bottom")

    rebuild_all()
    root.mainloop()


# ---------------------------------------------------------------------------
# CLI-режимы (чтобы EXE умел и headless-сборку)
# ---------------------------------------------------------------------------

def cli_main(argv):
    ap = argparse.ArgumentParser(prog="vInstallerCreator", description=APP_TITLE)
    sub = ap.add_subparsers(dest="cmd")
    p_new = sub.add_parser("new", help="создать шаблон проекта")
    p_new.add_argument("out")
    p_val = sub.add_parser("validate", help="проверить проект")
    p_val.add_argument("project")
    p_gen = sub.add_parser("generate", help="сгенерировать NSI из проекта")
    p_gen.add_argument("project")
    p_gen.add_argument("--out", default="")
    p_gen.add_argument("--out-dir", dest="out_dir", default="")
    p_bld = sub.add_parser("build", help="полная сборка установщика")
    p_bld.add_argument("project")
    p_bld.add_argument("--makensis", default="")
    p_bld.add_argument("--out-dir", default="")
    sub.add_parser("selftest", help="проверка работоспособности ядра")
    ns = ap.parse_args(argv)

    if ns.cmd == "new":
        core.save_project(core.default_project(), ns.out)
        print("Создан проект:", ns.out)
        return 0
    if ns.cmd == "validate":
        proj = core.load_project(ns.project)
        issues = core.validate_project(proj)
        for sev, msg in issues:
            print(("ERROR" if sev == "error" else "WARN ") + ": " + msg)
        return 1 if any(s == "error" for s, _ in issues) else 0
    if ns.cmd in ("generate", "build"):
        proj = core.load_project(ns.project)
        wd = ns.out_dir or os.path.dirname(os.path.abspath(ns.project)) or os.getcwd()
        os.makedirs(wd, exist_ok=True)
        nsi = ns.out if ns.cmd == "generate" and ns.out else \
            os.path.join(wd, re.sub(r"\W+", "_", proj["meta"]["name"]) + ".nsi")
        core.generate_nsi(proj, nsi, workdir=wd)
        print("NSI:", nsi)
        if ns.cmd == "generate":
            return 0
        rc, text = compile_installer(nsi, ns.makensis, log_cb=print, workdir=wd)
        return rc
    if ns.cmd == "selftest":
        print(f"{APP_TITLE} selftest")
        p = core.default_project()
        p["meta"]["name"] = "SelfTest App"
        issues = core.validate_project(p)
        print("validate:", "OK" if not [i for i in issues if i[0] == "error"] else "FAIL")
        tmp = os.path.join(os.environ.get("TEMP", "/tmp"), "vic_selftest.nsi")
        path, text = core.generate_nsi(p, tmp, workdir=os.path.dirname(tmp))
        print("generate_nsi:", "OK" if os.path.isfile(path) and len(text) > 1000 else "FAIL")
        mk = find_makensis()
        print("makensis:", mk or "not found (нужен NSIS для сборки установщиков)")
        print("SELFTEST OK")
        return 0
    ap.print_help()
    return 0


# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    if args and args[0] in ("new", "validate", "generate", "build", "selftest"):
        return cli_main(args)
    if args and args[0] == "--cli":
        return cli_main(args[1:] or ["--help"])
    if "--selftest" in args:
        return cli_main(["selftest"])
    try:
        run_gui()
        return 0
    except ImportError as e:
        # headless-окружение без DISPLAY: tkinter недоступен
        print("GUI недоступен (%s). Используйте CLI-режим:" % e, file=sys.stderr)
        print("  vInstallerCreator selftest | validate <proj.vicproj> | build <proj.vicproj>")
        return cli_main(args or ["selftest"])


if __name__ == "__main__":
    sys.exit(main())
