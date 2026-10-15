"""vInstaller Creator — core project model, validation and NSIS script generation.

Used by the GUI (vinstaller.py) and the CLI (vic-cli.py). Contains all the
"business logic": project schema/defaults, migration, validation, resource
generation (BMP wizard images, ICO conversion) and the full Nullsoft
Scriptable Install System (NSIS) script generator that turns a project into
a graphical Windows installer EXE.
"""

import copy
import json
import os
import re
import struct
import time

APP_NAME = "vInstaller Creator"
APP_VERSION = "1.0.0"
PROJECT_EXT = ".vicproj"
SCHEMA_VERSION = 3

# ---------------------------------------------------------------------------
# Locales
# ---------------------------------------------------------------------------

LOCALES = {
    "ru": {"lang_id": 2047, "mui": "Russian", "label": "Русский"},
    "en": {"lang_id": 1033, "mui": "English", "label": "English"},
    "uk": {"lang_id": 1058, "mui": "Ukrainian", "label": "Українська"},
    "de": {"lang_id": 1031, "mui": "German", "label": "Deutsch"},
    "fr": {"lang_id": 1036, "mui": "French", "label": "Français"},
    "es": {"lang_id": 1034, "mui": "Spanish", "label": "Español"},
    "pl": {"lang_id": 1045, "mui": "Polish", "label": "Polski"},
    "tr": {"lang_id": 1055, "mui": "Turkish", "label": "Türkçe"},
    "zh_CN": {"lang_id": 2052, "mui": "SimpChinese", "label": "简体中文"},
}

# Wizard strings: key -> (russian, english)
STRINGS = {
    "WELCOME_TITLE": ("Добро пожаловать в мастер установки $(^Name)",
                      "Welcome to the $(^Name) Setup Wizard"),
    "WELCOME_TEXT": ("Мастер установит $(^Name) на ваш компьютер.\n\n"
                     "Рекомендуется закрыть все остальные приложения перед установкой, чтобы "
                     "не пришлось перезагружать компьютер.\n\nНажмите «Далее» для продолжения.",
                     "This wizard will install $(^Name) on your computer.\n\n"
                     "It is recommended that you close all other applications before continuing.\n\n"
                     "Click Next to continue."),
    "LICENSE_TITLE": ("Лицензионное соглашение", "License Agreement"),
    "LICENSE_TEXT": ("Пожалуйста, внимательно прочитайте лицензионное соглашение перед продолжением.",
                     "Please review the following important information before continuing."),
    "COMPANY_NAME": ("Издатель:", "Publisher:"),
    "COMPONENTS_INFO": ("Что вы хотите установить?", "What do you want to install?"),
    "DIRECTORY_TITLE": ("Выбор папки установки", "Select Install Folder"),
    "DIRECTORY_DESC": ("В какую папку установить $(^Name)?", "Where should $(^Name) be installed?"),
    "DIRECTORY_SUB": ("Нажмите «Обзор…» для выбора другой папки.", "Click Browse to select a different folder."),
    "INSTFILES_DESC": ("Мастер готов к установке программы. Нажмите «Установить» для продолжения.",
                       "Setup is ready to begin installing the program. Click Install to continue."),
    "READY_TITLE": ("Готово к установке", "Ready to Install"),
    "FINISH_TITLE": ("Мастер установки завершён", "Completing the $(^Name) Setup Wizard"),
    "FINISH_TEXT": ("Программа установлена на ваш компьютер.\n\nНажмите «Готово» для выхода из мастера.",
                    "$(^Name) has been installed on your computer.\n\nClick Finish to close this wizard."),
    "RUN_LABEL": ("Запустить $(^Name)", "Run $(^Name)"),
    "DESKTOP_SHORTCUT": ("Создать ярлык на рабочем столе", "Create a shortcut on the Desktop"),
    "UPGRADE_WARNING": ("На этом компьютере обнаружена старая версия $(^Name).\n\n"
                        "Рекомендуется сначала удалить старую версию. Всё равно продолжить установку?",
                        "An older version of $(^Name) was detected on this computer.\n\n"
                        "It is recommended that you uninstall the old version first. Continue anyway?"),
    "REBOOT_REQUIRED": ("Для завершения установки требуется перезагрузка компьютера.",
                        "A system restart is required to complete the installation."),
    "ADMIN_REQUIRED": ("Для установки требуются права администратора.\nЗапустите установщик от имени администратора.",
                       "Administrator rights are required to install this product.\nPlease run the setup as administrator."),
    "ALREADY_RUNNING": ("Другой экземпляр установщика уже запущен. Дождитесь его завершения.",
                        "Another instance of the installer is already running. Please wait for it to finish."),
    "CLOSE_APP_MSG": ("Программа \"$1\" должна быть закрыта перед установкой.\n\n"
                      "Закройте её и нажмите «Повторить», либо «Отмена» чтобы выйти.",
                      "The application \"$1\" must be closed before the installation.\n\n"
                      "Close it and click Retry, or Cancel to exit Setup."),
    "UNINSTALL_CAPTION": ("Мастер удаления $(^Name)", "$(^Name) Uninstall"),
    "UNINSTALL_TEXT": ("Мастер удалит $(^Name) с вашего компьютера.\n\nНажмите «Удалить» для продолжения.",
                       "$(^Name) will be uninstalled from your computer.\n\nClick Uninstall to continue."),
    "UNINSTALL_FINISH_TEXT": ("$(^Name) успешно удалён.\n\nНажмите «Готово» для выхода.",
                              "$(^Name) has been successfully removed.\n\nClick Finish to close this wizard."),
    "SPACE_REQ": ("Требуется места:", "Space Required:"),
    "SPACE_AVAIL": ("Доступно места:", "Space Available:"),
    "NEED_DOTNET": ("Для работы программы требуется .NET Framework версии не ниже $1.\nУстановите его и повторите попытку.",
                    "This program requires .NET Framework $1 or later.\nPlease install it and run Setup again."),
    "NEED_VCREDIST": ("Не найден Visual C++ Redistributable.\nОн будет установлен автоматически после установки программы.",
                      "Visual C++ Redistributable was not found.\nIt will be installed after Setup completes."),
    "OS_TOO_OLD": ("Эта программа требует Windows $1 или новее.", "This program requires Windows $1 or later."),
    "FILE_IN_USE": ("Файл используется другой программой. Установка продолжится после перезагрузки.",
                    "A file in use could not be updated. The change will take effect after reboot."),
}


def _t(loc_key, text_key):
    ru, en = STRINGS[text_key]
    return ru if loc_key == "ru" else en


DEFAULT_UI_COLORS = {
    "wnd_bg": "#FFFFFF",
    "header_bg": "#5B9BD5",
    "header_fg": "#FFFFFF",
    "sidebar_bg": "#5B9BD5",
    "sidebar_bg2": "#2E6DA4",
    "sidebar_fg": "#FFFFFF",
    "selection_color": "#5B9BD5",
    "button_color": "#5B9BD5",
    "progress_color": "#5B9BD5",
    "text_color": "#000000",
}

# ---------------------------------------------------------------------------
# Project defaults
# ---------------------------------------------------------------------------

def default_project():
    return copy.deepcopy({
        "schema": SCHEMA_VERSION,
        "meta": {
            "name": "Новая программа",
            "short_name": "",
            "version": "1.0.0",
            "publisher": "My Company",
            "url_info": "",
            "url_update": "",
            "url_readme": "",
            "copyright": "(C) {YEAR} {PUBLISHER}. Все права защищены.",
            "comments": "",
            "build": "1",
            "icon": "",
            "license_file": "",
            "language": "ru",
            "fallback_language": "en",
            "multiuser": False,
        },
        "setup": {
            "default_dir": r"C:\Program Files\{APPNAME}",
            "exec_level": "auto",              # none|user|highest|admin|lock|auto
            "arch": "x86",                     # x86|x64
            "allow_root": False,
            "check_mutex": True,
            "detect_old_version": True,
            "upgrade_mode": "ask",             # ask | uninstall_first | keep
            "close_apps": [],                  # window class/exe names to warn about
            "requires": {"vc_redist": False, "dotnet": "", "os_min": ""},
            "custom_ini": {},                  # raw extra NSIS directives {directive: args}
        },
        "compression": {
            "method": "lzma",                  # zlib|bzip2|lzma
            "solid": True,
            "dict_mb": 8,
        },
        "ui": {
            "style": "mui2",                   # mui2 | classic
            "wizard": "modern",                # modern | classic (ChangeUI)
            "colors": dict(DEFAULT_UI_COLORS),
            "header_image": ["", ""],          # [path, label]; empty => generated
            "sidebar_image": ["", ""],         # [path, label]; empty => generated
            "use_custom_images": True,
            "license_mode": "checkbox",        # checkbox|radiobuttons|off
            "misc_buttons": ["< Назад", "Далее >", "Отмена", "Готово"],
            "branding": "{APPNAME} • {PUBLISHER}",
            "completed_text": "",
            "window_icon": True,
            "details_show": "hide",            # hide|show|nevershow
            "rtl": False,
            "space_texts": True,
        },
        "pages": {
            "welcome": True,
            "license": False,
            "components": True,
            "directory": True,
            "verify": False,                   # ready-to-install page
            "instfiles": True,
            "finish": True,
            "uninstall_confirm": True,
            "uninstall_finish": True,
        },
        "install_types": [
            {"id": 0, "name": "Полная", "sections": "*"},
            {"id": 1, "name": "Типичная", "sections": "main,shortcuts"},
            {"id": 2, "name": "Минимальная", "sections": "main"},
        ],
        "sections": [
            {"id": "main", "name": "{APPNAME}", "size_kb": 0, "flags": "RO",
             "types": [0, 1, 2], "files": [], "folders": []},
            {"id": "shortcuts", "name": "Ярлыки", "size_kb": 0, "flags": "",
             "types": [0, 1], "files": [], "folders": []},
        ],
        "shortcuts": [
            {"section": "shortcuts", "where": "startmenu", "name": "{APPNAME}",
             "target": "{EXE}", "args": "", "icon": "", "icon_index": 0,
             "description": ""},
            {"section": "shortcuts", "where": "desktop", "name": "{APPNAME}",
             "target": "{EXE}", "args": "", "icon": "", "icon_index": 0,
             "description": ""},
        ],
        "file_ops": {
            "dirs": ["data", "logs"],
            "delete_files": [],
        },
        "registry": {"entries": []},
        "run": {
            "install_exec": [],     # [{cmd, section, silent, wait}]
            "uninstall_exec": [],   # [{cmd, silent}]
            "startup_run": "",      # value written to Run key
        },
        "scripts": {
            "pre_init": "",
            "leave_directory": "",
            "custom_function": "",
            "uninstall_custom": "",
        },
        "output": {
            "filename": "{APPNAME}-{VERSION}-setup.exe",
        },
    })


PLACEHOLDER_RE = re.compile(r"\{(APPNAME|SHORTNAME|VERSION|PUBLISHER|YEAR)\}")


def expand_placeholders(text, proj):
    meta = proj["meta"]
    mapping = {
        "APPNAME": meta.get("name", "App"),
        "SHORTNAME": meta.get("short_name") or meta.get("name", "App"),
        "VERSION": meta.get("version", "1.0.0"),
        "PUBLISHER": meta.get("publisher", ""),
        "YEAR": str(time.localtime().tm_year),
    }
    return PLACEHOLDER_RE.sub(lambda m: mapping.get(m.group(1), m.group(0)), text or "")


# ---------------------------------------------------------------------------
# Load / save / migrate
# ---------------------------------------------------------------------------

def load_project(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    return migrate(data)


def migrate(data):
    base = default_project()
    merged = deep_merge(base, data)
    merged["schema"] = SCHEMA_VERSION
    return merged


def deep_merge(base, override):
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def save_project(proj, path):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(proj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_VERSION_RE = re.compile(r"^\d+(\.\d+){0,3}$")
_SECID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_project(proj):
    """Return list of (severity, message); severity in {'error','warning'}."""
    issues = []
    meta = proj["meta"]
    if not (meta.get("name") or "").strip():
        issues.append(("error", "Не указано название программы."))
    ver = (meta.get("version") or "").strip()
    if not _VERSION_RE.match(ver):
        issues.append(("error", "Некорректная версия «%s». Формат: 1.0 … 1.0.0.0 (только цифры)." % ver))
    elif len(ver.split(".")) < 2:
        issues.append(("warning", "Версия «%s»: Windows отображает её как %s.0.0.0 — лучше указать 1.0.0." % (ver, ver)))
    exe_count = 0
    seen_ids = set()
    for sec in proj["sections"]:
        sid = sec.get("id", "")
        if not _SECID_RE.match(sid):
            issues.append(("error", "Некорректный ID секции «%s»: только латиница, цифры, подчёркивание." % sid))
        if sid in seen_ids:
            issues.append(("error", "Дублирующийся ID секции «%s»." % sid))
        seen_ids.add(sid)
        for fe in sec.get("files", []):
            src = fe.get("src", "")
            if src and not os.path.isfile(src):
                issues.append(("error", "Файл не найден: %s" % src))
            if src.lower().endswith(".exe") or fe.get("kind") == "exe":
                exe_count += 1
        for rf in sec.get("folders", []):
            src = rf.get("src", "")
            if src and not os.path.isdir(src):
                issues.append(("error", "Папка не найдена: %s" % src))
    if not proj["sections"]:
        issues.append(("error", "Нет ни одной секции установки."))
    if exe_count == 0:
        issues.append(("warning", "Среди файлов нет ни одного .exe — запуск программы и ярлыки могут быть нерабочими."))
    if proj["pages"]["license"]:
        lf = meta.get("license_file", "")
        if not lf or not os.path.isfile(lf):
            issues.append(("error", "Включена страница лицензии, но файл лицензии не выбран или не найден."))
    icon = meta.get("icon", "")
    if icon and not os.path.isfile(icon):
        issues.append(("error", "Иконка не найдена: %s" % icon))
    ui = proj["ui"]
    for key in ("header_image", "sidebar_image"):
        val = (ui.get(key) or ["", ""])[0]
        if val and not os.path.isfile(val):
            issues.append(("error", "Изображение (%s) не найдено: %s" % (key, val)))
    for st in proj["shortcuts"]:
        if st.get("target") == "{EXE}" and exe_count == 0:
            issues.append(("warning", "Ярлык «%s» ссылается на {EXE}, но основной .exe не выбран." %
                           expand_placeholders(st.get("name", ""), proj)))
        if st.get("section") not in seen_ids:
            issues.append(("error", "Ярлык «%s» привязан к несуществующей секции «%s»." %
                           (st.get("name"), st.get("section"))))
    for ent in proj["registry"]["entries"]:
        if not ent.get("root") or not ent.get("key"):
            issues.append(("error", "Неполная запись реестра: укажите корень (HKLM/HKCU…) и ключ."))
    for cmd in proj["run"]["install_exec"] + proj["run"]["uninstall_exec"]:
        if not cmd.get("cmd", "").strip():
            issues.append(("warning", "Пустая команда запуска — она будет пропущена."))
    if not any(sec.get("flags") != "RD" for sec in proj["sections"]):
        issues.append(("warning", "Все секции сняты по умолчанию (RD) — пользователь может ничего не установить."))
    return issues


# ---------------------------------------------------------------------------
# NSIS escaping helpers
# ---------------------------------------------------------------------------

def nq(s):
    """Escape a string for embedding inside double quotes in an NSIS script."""
    s = "" if s is None else str(s)
    s = s.replace('"', '$\\"').replace("$", "$$").replace("\r", "").replace("\n", "\\n")
    return s


def name_amp(s):
    return s.replace("&", "&&")


def _pad4(v):
    parts = [p for p in str(v).split(".") if p.isdigit()]
    while len(parts) < 4:
        parts.append("0")
    return ".".join(parts[:4])


def _safe_subdir(name):
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def main_exe(proj):
    """Locate primary executable among all section files."""
    for sec in proj["sections"]:
        for fe in sec.get("files", []):
            if fe.get("kind") == "exe":
                return fe.get("src", "")
    for sec in proj["sections"]:
        for fe in sec.get("files", []):
            if fe.get("src", "").lower().endswith(".exe"):
                return fe.get("src", "")
    return ""


# ---------------------------------------------------------------------------
# Resource generation (BMP wizard images without external deps)
# ---------------------------------------------------------------------------

def _hexcol(h, default):
    try:
        b = bytes.fromhex((h or "").lstrip("#"))
        return (b[0], b[1], b[2])
    except Exception:
        d = bytes.fromhex(default.lstrip("#"))
        return (d[0], d[1], d[2])


def write_bmp(path, w, h, pixel_fn):
    """Write a 24-bit BMP. pixel_fn(x,y)->(r,g,b), y counted top->bottom."""
    rowsize = (w * 3 + 3) & ~3
    pad = b"\x00" * (rowsize - w * 3)
    body = bytearray()
    for y in range(h - 1, -1, -1):           # bottom-up
        row = bytearray()
        for x in range(w):
            r, g, b = pixel_fn(x, y)
            row += bytes((b, g, r))
        row += pad
        body += row
    size = 54 + len(body)
    hdr = b"BM" + struct.pack("<IHHI", size, 0, 0, 54)
    info = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, len(body), 2835, 2835, 0, 0)
    with open(path, "wb") as f:
        f.write(hdr + info + bytes(body))
    return path


def gen_sidebar_bmp(path, colors, appname, publisher, version):
    c1 = _hexcol(colors.get("sidebar_bg"), "#5B9BD5")
    c2 = _hexcol(colors.get("sidebar_bg2"), "#2E6DA4")
    fg = _hexcol(colors.get("sidebar_fg"), "#FFFFFF")
    W, H = 164, 314

    def px(x, y):
        t = y / float(H - 1)
        r = int(c1[0] + (c2[0] - c1[0]) * t)
        g = int(c1[1] + (c2[1] - c1[1]) * t)
        b = int(c1[2] + (c2[2] - c1[2]) * t)
        # subtle brand block near bottom
        if H - 60 <= y < H - 20 and 12 <= x < W - 12:
            if y in (H - 60, H - 21) or x in (12, W - 13):
                return tuple(min(255, ch + 40) for ch in (r, g, b))
        return (r, g, b)
    return write_bmp(path, W, H, px)


def gen_header_bmp(path, colors):
    cbg = _hexcol(colors.get("header_bg"), "#5B9BD5")
    cfg = _hexcol(colors.get("header_fg"), "#FFFFFF")
    W, H = 494, 58

    def px(x, y):
        if y >= H - 3:
            return cfg
        return cbg
    return write_bmp(path, W, H, px)


# ---------------------------------------------------------------------------
# NSIS script generation
# ---------------------------------------------------------------------------

def generate_nsi(proj, out_nsi_path, workdir=None):
    """Generate a complete NSIS script; returns (path, script_text)."""
    global _CUR_PROJ
    _CUR_PROJ = proj
    if workdir is None:
        workdir = os.path.dirname(os.path.abspath(out_nsi_path)) or "."
    os.makedirs(workdir, exist_ok=True)

    meta, setup, ui, pages = proj["meta"], proj["setup"], proj["ui"], proj["pages"]
    comp = proj["compression"]
    lang = meta.get("language", "ru")
    if lang not in LOCALES:
        lang = "en"
    loc = LOCALES[lang]
    fallback = meta.get("fallback_language", "en")
    appname = expand_placeholders(meta["name"], proj)
    version = meta["version"]
    publisher = expand_placeholders(meta.get("publisher", ""), proj)
    icon = meta.get("icon", "")
    license_file = meta.get("license_file", "")
    arch = setup.get("arch", "x86")
    exec_level = setup.get("exec_level", "auto")
    outname = expand_placeholders(proj["output"]["filename"], proj)
    if not outname.lower().endswith(".exe"):
        outname += ".exe"
    instdir = expand_placeholders(setup["default_dir"], proj)
    colors = ui.get("colors", DEFAULT_UI_COLORS)
    style = ui.get("style", "mui2")

    L = []
    add = L.append

    # ================= header =============================================
    add("; ============================================================")
    add(";  Сгенерировано: %s %s" % (APP_NAME, APP_VERSION))
    add(";  Проект: %s   Дата: %s" % (appname, time.strftime("%Y-%m-%d %H:%M:%S")))
    add("; ============================================================")
    add('!include "MUI2.nsh"')
    add('!include "LogicLib.nsh"')
    add('!include "Sections.nsh"')
    add('!include "FileFunc.nsh"')
    add('!include "WinVer.nsh"')
    add('!include "x64.nsh"')
    add("")
    add('!define APP_NAME "%s"' % nq(appname))
    add('!define APP_VER "%s"' % nq(version))
    add('!define APP_PUB "%s"' % nq(publisher))
    add('!define DEFAULT_INSTALL_DIR "%s"' % nq(instdir))
    add("")
    add("Unicode true")
    if arch == "x64":
        add('!define /redef PROGRAMFILES "${PROGRAMFILES64}"')
    add('Name "%s"' % nq(name_amp(appname)))
    add('OutFile "%s"' % nq(outname))
    add('InstallDir "$PROGRAMFILES\\%s"' % nq(_safe_subdir(appname)))
    add('InstallDirRegKey HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APP_NAME}" "InstallLocation"')
    lvl = {"auto": "auto", "admin": "admin", "user": "user",
           "highest": "highest", "lock": "lock"}.get(exec_level, "auto")
    add("RequestExecutionLevel %s" % lvl)
    add("XPStyle on")
    add("ShowInstDetails %s" % ui.get("details_show", "hide"))
    add("ShowUninstDetails show")
    add("SetCompress force")
    if comp.get("solid"):
        add("SetCompressor /SOLID %s" % comp.get("method", "lzma"))
    else:
        add("SetCompressor %s" % comp.get("method", "lzma"))
    try:
        add("SetCompressorDictSize %d" % max(1, min(256, int(comp.get("dict_mb", 8)))))
    except Exception:
        pass
    add("CRCCheck on")
    add("WindowIcon %s" % ("on" if ui.get("window_icon", True) else "off"))
    add('Caption "${APP_NAME} ${APP_VER}"')
    add('BrandingText "%s"' % nq(expand_placeholders(ui.get("branding", ""), proj)))
    add("AllowRootDirInstall %s" % ("true" if setup.get("allow_root") else "false"))
    add("AutoCloseWindow false")
    add("SetDetailsPrint both")
    add('VIProductVersion "%s"' % _pad4(version))
    lid = loc["lang_id"]
    add('VIAddVersionKey /LANG=%d "ProductName" "${APP_NAME}"' % lid)
    add('VIAddVersionKey /LANG=%d "ProductVersion" "${APP_VER}"' % lid)
    add('VIAddVersionKey /LANG=%d "FileVersion" "${APP_VER} (build %s)"' % (lid, nq(meta.get("build", "1"))))
    add('VIAddVersionKey /LANG=%d "CompanyName" "${APP_PUB}"' % lid)
    add('VIAddVersionKey /LANG=%d "LegalCopyright" "%s"' % (lid, nq(expand_placeholders(meta.get("copyright", ""), proj))))
    add('VIAddVersionKey /LANG=%d "FileDescription" "%s"' % (lid, nq(meta.get("comments") or appname)))
    if icon:
        add('Icon "%s"' % nq(icon))
        add('UninstallIcon "%s"' % nq(icon))
    mb = ui.get("misc_buttons") or ["", "", "", ""]
    add('MiscButtonText "%s" "%s" "%s" "%s"' % tuple(nq(x) for x in (list(mb) + ["", "", "", ""])[:4]))
    if ui.get("completed_text"):
        add('CompletedText "%s"' % nq(expand_placeholders(ui["completed_text"], proj)))
    if ui.get("space_texts", True):
        add('SpaceTexts "${STR_SPACE_REQ}" "${STR_SPACE_AVAIL}"')
    if ui.get("rtl"):
        add("!define MUI_UI \"" + "${NSISDIR}\\Contrib\\UIs\\rtl.exe\"" + "\"")
    if ui.get("wizard", "modern") == "classic":
        add('ChangeUI all "${NSISDIR}\\Contrib\\UIs\\classic.exe"')
    add("")
    for k, v in (setup.get("custom_ini") or {}).items():
        add("%s %s" % (k, v))
    add("")

    # ================= localized LangStrings ==============================
    add("; ---------- Строки мастера ----------")
    ids = [loc["lang_id"]]
    if fallback in LOCALES and LOCALES[fallback]["lang_id"] not in ids:
        ids.append(LOCALES[fallback]["lang_id"])
    for key, (ru, en) in STRINGS.items():
        for i in ids:
            txt = ru if i == 2047 else en
            add('LangString %s %d "%s"' % ("STR_" + key, i, nq(txt)))
    add("")

    # ================= MUI defines & pages ================================
    add("; ---------- Страницы ----------")
    add("!define MUI_ABORTWARNING")
    add('!define MUI_WELCOMEPAGE_TITLE "${STR_WELCOME_TITLE}"')
    add('!define MUI_WELCOMEPAGE_TEXT "${STR_WELCOME_TEXT}"')
    add('!define MUI_LICENSEPAGE_TEXT_TOP "${STR_LICENSE_TEXT}"')
    if ui.get("license_mode") == "radiobuttons":
        add("!define MUI_LICENSEPAGE_RADIOBUTTONS")
    else:
        add("!define MUI_LICENSEPAGE_CHECKBOX")
    add('!define MUI_COMPONENTSPAGE_SMALLDESC')
    add('!define MUI_DIRECTORYPAGE_TEXT_TOP "${STR_DIRECTORY_DESC}"')
    add('!define MUI_DIRECTORYPAGE_TEXT_DESTINATION "${STR_DIRECTORY_SUB}"')
    add('!define MUI_DIRECTORYPAGE_VERIFYONLEAVE')
    if main_exe(proj):
        add('!define MUI_FINISHPAGE_RUN "$ExePath"')
        add('!define MUI_FINISHPAGE_RUN_TEXT "${STR_RUN_LABEL}"')
        add('!define MUI_FINISHPAGE_SHOWREADME "%s"' % nq(meta.get("url_readme", "")))
        add('!define MUI_FINISHPAGE_SHOWREADME_TEXT "${STR_DESKTOP_SHORTCUT}"')
    add('!define MUI_FINISHPAGE_TITLE "${STR_FINISH_TITLE}"')
    add('!define MUI_FINISHPAGE_TEXT "${STR_FINISH_TEXT}"')
    add("")
    # wizard bitmaps
    sidebar_user = (ui.get("sidebar_image") or ["", ""])[0]
    header_user = (ui.get("header_image") or ["", ""])[0]
    sidebar_path = sidebar_user if sidebar_user else os.path.join(workdir, "vic_sidebar.bmp")
    header_path = header_user if header_user else os.path.join(workdir, "vic_header.bmp")
    if not sidebar_user:
        gen_sidebar_bmp(sidebar_path, colors, appname, publisher, version)
    if not header_user:
        gen_header_bmp(header_path, colors)
    add('!define SIDEBAR_BMP "%s"' % nq(sidebar_path))
    add('!define HEADER_BMP "%s"' % nq(header_path))
    add('!define MUI_WELCOMEFINISHPAGE_BITMAP "${SIDEBAR_BMP}"')
    add('!define MUI_UNWELCOMEFINISHPAGE_BITMAP "${SIDEBAR_BMP}"')
    add("!define MUI_HEADERIMAGE")
    add('!define MUI_HEADERIMAGE_BITMAP "${HEADER_BMP}"')
    add('!define MUI_UNCAPTION "${STR_UNINSTALL_CAPTION}"')
    add("")
    if pages["welcome"]:
        add("!insertmacro MUI_PAGE_WELCOME")
    if pages["license"]:
        add('LicenseForceSelection %s' % ui.get("license_mode", "checkbox"))
        add('!insertmacro MUI_PAGE_LICENSE "%s"' % nq(license_file))
    if pages["components"]:
        add('!define MUI_PAGE_CUSTOMFUNCTION_LEAVE ComponentsLeave')
        add("!insertmacro MUI_PAGE_COMPONENTS")
    if pages["directory"]:
        add('!define MUI_PAGE_CUSTOMFUNCTION_LEAVE DirectoryLeave')
        add("!insertmacro MUI_PAGE_DIRECTORY")
    if pages["verify"]:
        add("!insertmacro MUI_PAGE_INSTFILES")   # verify page emulated below
    if pages["instfiles"]:
        add("!insertmacro MUI_PAGE_INSTFILES")
    if pages["finish"]:
        add("!insertmacro MUI_PAGE_FINISH")
    add("")
    add("; ---------- Страницы деинсталлятора ----------")
    if pages["uninstall_confirm"]:
        add("!insertmacro MUI_UNPAGE_CONFIRM")
    add("!insertmacro MUI_UNPAGE_INSTFILES")
    if pages["uninstall_finish"]:
        add("!insertmacro MUI_UNPAGE_FINISH")
    add("")
    add('!insertmacro MUI_LANGUAGE "%s"' % loc["mui"])
    if fallback in LOCALES and fallback != lang:
        add('!insertmacro MUI_LANGUAGE "%s"' % LOCALES[fallback]["mui"])
    add("")

    # ================= variables ==========================================
    add("; ---------- Переменные ----------")
    add("Var ExePath")
    add("Var InstalledVersion")
    add("Var OldUninstaller")
    for sec in proj["sections"]:
        add("Var SEC_%s" % sec["id"].upper())
    add("")

    # ================= page callbacks ======================================
    add("; ---------- Коллбэки страниц ----------")
    add("Function ComponentsLeave")
    if proj["scripts"].get("leave_components"):
        for ln in proj["scripts"]["leave_components"].splitlines():
            add("  " + ln)
    add("FunctionEnd")
    add("")
    add("Function DirectoryLeave")
    add('  ${If} $INSTDIR == ""')
    add('    StrCpy $INSTDIR "${DEFAULT_INSTALL_DIR}"')
    add('  ${EndIf}')
    if proj["scripts"].get("leave_directory"):
        for ln in proj["scripts"]["leave_directory"].splitlines():
            add("  " + ln)
    add("FunctionEnd")
    add("")

    # ================= .onInit ==============================================
    add("; ---------- Инициализация установщика ----------")
    add("Function .onInit")
    if fallback in LOCALES and fallback != lang:
        add("!insertmacro MUI_LANGDLL_DISPLAY")
    if setup.get("check_mutex", True):
        add('System::Call \'kernel32::CreateMutexA(i 0, i 0, t "${APP_NAME}_SetupMutex")i .r1\'')
        add('IntCmp $1 0 okmutex +3 +3')
        add('MessageBox MB_OK|MB_ICONSTOP "${STR_ALREADY_RUNNING}" /SD IDOK')
        add('Abort')
        add('okmutex:')
    if setup.get("detect_old_version", True):
        add('ReadRegStr $InstalledVersion HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APP_NAME}" "DisplayVersion"')
        add('ReadRegStr $OldUninstaller HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APP_NAME}" "UninstallString"')
        add('${If} $InstalledVersion != ""')
        mode = setup.get("upgrade_mode", "ask")
        if mode == "ask":
            add('  MessageBox MB_YESNO|MB_ICONEXCLAMATION "${STR_UPGRADE_WARNING}" /SD IDYES IDYES goOld')
            add('  Quit')
            add('goOld:')
        elif mode == "uninstall_first":
            add('  MessageBox MB_OKCANCEL|MB_ICONINFORMATION "${STR_UPGRADE_WARNING}" /SD IDOK IDCANCEL quitOld')
            add('  StrCpy $R1 "$OldUninstaller" -1 ; strip trailing quote handling done by NSIS itself')
            add('  nsExec::ExecToStack \'$OldUninstaller /S\'')
            add('  Sleep 1500')
            add('  Goto goOld2')
            add('quitOld:')
            add('  Quit')
            add('goOld2:')
        add('${EndIf}')
    req = setup.get("requires", {})
    if req.get("os_min"):
        winmap = {"win7": "7", "win8": "8", "win8.1": "8.1", "win10": "10"}
        wv = winmap.get(req["os_min"], "10")
        add('${IfNot} ${AtLeastWin%s}' % wv.replace(".", ""))
        add('  MessageBox MB_ICONSTOP|MB_OK "${STR_OS_TOO_OLD}" /SD IDOK')
        add('  Abort')
        add('${EndIf}')
    if req.get("dotnet"):
        add('ReadRegStr $0 HKLM "SOFTWARE\\Microsoft\\NET Framework Setup\\NDP\\v%s\\Install" "Version"' % req["dotnet"])
        add('${If} $0 == ""')
        add('  MessageBox MB_OK|MB_ICONEXCLAMATION "${STR_NEED_DOTNET}" /SD IDOK')
        add('  Abort')
        add('${EndIf}')
    if req.get("vc_redist"):
        add('ReadRegStr $0 HKLM "SOFTWARE\\Classes\\Installer\\Dependencies" "MSVCRT_x86"')
        add('${If} $0 == ""')
        add('  DetailPrint "${STR_NEED_VCREDIST}"')
        add('${EndIf}')
    for proc in setup.get("close_apps", []):
        pn = str(proc).strip()
        if not pn:
            continue
        add("; проверка запущенного приложения: %s" % nq(pn))
        lbl = re.sub(r"\W+", "_", pn)
        add('TryAgain_%s:' % lbl)
        add('  FindWindow $0 "" "%s"' % nq(pn))
        add('  ${If} $0 <> 0')
        add('    MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "${STR_CLOSE_APP_MSG}" /SD IDCANCEL IDRETRY +2')
        add('    Quit')
        add('    Goto TryAgain_%s' % lbl)
        add('  ${EndIf}')
    if proj["scripts"].get("pre_init"):
        add('  ; --- pre_init (пользовательский код) ---')
        for ln in proj["scripts"]["pre_init"].splitlines():
            add("  " + ln)
    add("FunctionEnd")
    add("")

    # ================= install types & sections =============================
    add("; ---------- Компоненты ----------")
    for stype in proj["install_types"]:
        add('InstType "%s"' % nq(stype["name"]))
    add("")
    for si, sec in enumerate(proj["sections"]):
        sid = sec["id"]
        flags = (sec.get("flags") or "").upper()
        prefix = ""
        if "RO" in flags:
            prefix = "/RO "
        elif "RD" in flags:
            prefix = "/RD "
        elif "RE" in flags:
            prefix = "/RE "
        add('Section %s"%s" %s $SEC_%s' % (prefix, nq(expand_placeholders(sec["name"], proj)), sid, sid.upper()))
        types = [t for t in sec.get("types", []) if isinstance(t, int)]
        if types:
            add("  SectionIn %s" % " ".join(str(t) for t in types))
        if sec.get("size_kb"):
            add("  SectionSetSize ${%s} %d" % (sid.upper(), int(sec["size_kb"])))
        add('  SetOutPath "$INSTDIR"')
        for fe in sec.get("files", []):
            src = fe.get("src", "")
            if not src or not os.path.isfile(src):
                continue
            dest = (fe.get("dest") or "").strip("\\/")
            fn = os.path.basename(src)
            if dest:
                add('  SetOutPath "$INSTDIR\\%s"' % nq(dest))
            add('  File "%s"' % nq(src))
            if fe.get("kind") == "exe" or (fn.lower().endswith(".exe") and not dest):
                add('  StrCpy $ExePath "$INSTDIR\\%s\\%s"' % (nq(dest + "\\" if dest else ""), nq(fn)))
            if dest:
                add('  SetOutPath "$INSTDIR"')
        for rf in sec.get("folders", []):
            src = rf.get("src", "")
            if not src or not os.path.isdir(src):
                continue
            dest = (rf.get("dest") or "").strip("\\/")
            if dest:
                add('  SetOutPath "$INSTDIR\\%s"' % nq(dest))
            add('  File /r "%s\\*.*"' % nq(src.rstrip("\\/")))
            add('  SetOutPath "$INSTDIR"')
        # shortcuts belonging to this section
        for sc in proj["shortcuts"]:
            if sc.get("section") != sid:
                continue
            where = sc.get("where", "startmenu")
            root = {"startmenu": "$SMPROGRAMS\\${APP_NAME}",
                    "desktop": "$DESKTOP",
                    "quicklaunch": "$QUICKLAUNCH",
                    "startup": "$SMSTARTUP",
                    "commonstartmenu": "$COMMONSTARTMENU\\${APP_NAME}",
                    "commondesktop": "$COMMONDESKTOP"}.get(where, "$SMPROGRAMS\\${APP_NAME}")
            nm = expand_placeholders(sc.get("name", "Shortcut"), proj)
            tgt = sc.get("target", "{EXE}")
            tgt_ns = '"$ExePath"' if tgt == "{EXE}" else '"%s"' % nq(tgt)
            args = nq(expand_placeholders(sc.get("args", ""), proj))
            ic = sc.get("icon", "")
            ici = int(sc.get("icon_index", 0) or 0)
            desc = nq(expand_placeholders(sc.get("description", ""), proj))
            if where in ("startmenu", "commonstartmenu"):
                add('  CreateDirectory "%s"' % root)
            add('  CreateShortCut "%s\\%s.lnk" %s "%s" "%s" %d SW_SHOWNORMAL "%s"' %
                (root, nq(nm), tgt_ns, args, ('"%s"' % nq(ic)) if ic else '""', ici, desc))
        # registry entries tagged to this section (or untagged)
        for ent in proj["registry"]["entries"]:
            if (ent.get("section") or "") not in ("", sid):
                continue
            _emit_reg(add, ent)
        # per-section post commands
        for cmd in proj["run"]["install_exec"]:
            if (cmd.get("section") or "") not in ("", sid):
                continue
            _emit_exec(add, cmd, proj)
        add("SectionEnd")
        add("")

    # ================= -Post section ========================================
    add("; ---------- Регистрация деинсталлятора ----------")
    add("Section -Post")
    un_inst = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}'
    add('  WriteRegStr HKLM "%s" "DisplayName" "${APP_NAME}"' % un_inst)
    add('  WriteRegStr HKLM "%s" "DisplayVersion" "${APP_VER}"' % un_inst)
    add('  WriteRegStr HKLM "%s" "Publisher" "${APP_PUB}"' % un_inst)
    add('  WriteRegStr HKLM "%s" "URLInfoAbout" "%s"' % (un_inst, nq(meta.get("url_info", ""))))
    add('  WriteRegStr HKLM "%s" "HelpLink" "%s"' % (un_inst, nq(meta.get("url_readme", ""))))
    add('  WriteRegStr HKLM "%s" "Readme" "%s"' % (un_inst, nq(meta.get("url_readme", ""))))
    add('  WriteRegStr HKLM "%s" "InstallLocation" "$INSTDIR"' % un_inst)
    add('  WriteRegStr HKLM "%s" "UninstallString" \'"$INSTDIR\\uninstall.exe"\'' % un_inst)
    add('  WriteRegStr HKLM "%s" "QuietUninstallString" \'"$INSTDIR\\uninstall.exe" /S\'' % un_inst)
    add('  WriteRegDWORD HKLM "%s" "NoModify" 1' % un_inst)
    add('  WriteRegDWORD HKLM "%s" "NoRepair" 1' % un_inst)
    add('  WriteRegDWORD HKLM "%s" "EstimatedSize" %d' % (un_inst, _estimate_size_kb(proj)))
    if icon:
        add('  WriteRegStr HKLM "%s" "DisplayIcon" "$ExePath,0"' % un_inst)
    if proj["run"].get("startup_run"):
        add('  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Run" "${APP_NAME}" \'%s\'' %
            nq(expand_placeholders(proj["run"]["startup_run"], proj)))
    add("SectionEnd")
    add("")

    # ================= uninstaller ===========================================
    add("; ---------- Деинсталлятор ----------")
    add("Function un.onInit")
    add("!insertmacro MUI_UNGETLANGUAGE")
    add("FunctionEnd")
    add("")
    add("Section Uninstall")
    add('  SetShellVarContext all')
    add('  ${If} ${FileExists} "$INSTDIR\\uninstall.exe"')
    add('    Delete "$INSTDIR\\uninstall.exe"')
    add('  ${EndIf}')
    for sec in reversed(proj["sections"]):
        for fe in sec.get("files", []):
            src = fe.get("src", "")
            if not src:
                continue
            dest = (fe.get("dest") or "").strip("\\/")
            fn = os.path.basename(src)
            add('  Delete "$INSTDIR\\%s%s"' % (nq(dest + "\\" if dest else ""), nq(fn)))
        for rf in sec.get("folders", []):
            dest = (rf.get("dest") or "").strip("\\/")
            if dest:
                add('  RMDir /r "$INSTDIR\\%s"' % nq(dest))
    for op in proj["file_ops"].get("delete_files", []):
        add('  Delete "$INSTDIR\\%s"' % nq(op.strip("\\/")))
    for d in proj["file_ops"].get("dirs", []):
        add('  RMDir "$INSTDIR\\%s"' % nq(d.strip("\\/")))
    for sc in proj["shortcuts"]:
        where = sc.get("where", "startmenu")
        root = {"startmenu": "$SMPROGRAMS\\${APP_NAME}",
                "desktop": "$DESKTOP",
                "quicklaunch": "$QUICKLAUNCH",
                "startup": "$SMSTARTUP",
                "commonstartmenu": "$COMMONSTARTMENU\\${APP_NAME}",
                "commondesktop": "$COMMONDESKTOP"}.get(where, "$SMPROGRAMS\\${APP_NAME}")
        nm = expand_placeholders(sc.get("name", "Shortcut"), proj)
        add('  Delete "%s\\%s.lnk"' % (root, nq(nm)))
        if where in ("startmenu", "commonstartmenu"):
            add('  RMDir "%s"' % root)
    for ent in proj["registry"]["entries"]:
        root = ent.get("root", "HKLM")
        key = nq(ent.get("key", ""))
        if key:
            add('  DeleteRegValue %s "%s" "%s"' % (root, key, nq(ent.get("value", ""))))
            add('  DeleteRegKey /ifempty %s "%s"' % (root, key))
    if proj["run"].get("startup_run"):
        add('  DeleteRegValue HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Run" "${APP_NAME}"')
    add('  DeleteRegKey HKLM "%s"' % un_inst)
    add('  RMDir /r "$INSTDIR"')
    if proj["scripts"].get("uninstall_custom"):
        add('  ; --- uninstall_custom (пользовательский код) ---')
        for ln in proj["scripts"]["uninstall_custom"].splitlines():
            add("  " + ln)
    for cmd in proj["run"]["uninstall_exec"]:
        c = expand_placeholders(cmd.get("cmd", ""), proj)
        if c.strip():
            add("  nsExec::ExecToLog '%s'" % c.replace("'", "$'"))
    add('  ${If} ${RebootFlag}')
    add('    MessageBox MB_OK|MB_ICONINFORMATION "${STR_REBOOT_REQUIRED}"')
    add('  ${EndIf}')
    add("SectionEnd")
    add("")
    add('WriteUninstaller "uninstall.exe"')
    add("")
    if proj["scripts"].get("custom_function"):
        add("; ---------- Пользовательская функция ----------")
        add("Function VicCustom")
        for ln in proj["scripts"]["custom_function"].splitlines():
            add("  " + ln)
        add("FunctionEnd")
        add("")

    text = "\n".join(L) + "\n"
    with open(out_nsi_path, "w", encoding="utf-8-sig") as f:
        f.write(text)
    return out_nsi_path, text


def _emit_reg(add, ent):
    root = ent.get("root", "HKLM")
    key = nq(ent.get("key", ""))
    val = nq(ent.get("value", ""))
    typ = ent.get("type", "str")
    data = nq(expand_placeholders(ent.get("data", ""), _CUR_PROJ))
    if typ == "dword":
        d = re.sub(r"[^0-9a-fA-Fx]", "", ent.get("data", "0")) or "0"
        add('  WriteRegDWORD %s "%s" "%s" %s' % (root, key, val, d))
    elif typ == "expand":
        add('  WriteRegExpandStr %s "%s" "%s" "%s"' % (root, key, val, data))
    elif typ == "none":
        add('  WriteRegStr %s "%s" "" "%s"' % (root, key, data))
    else:
        add('  WriteRegStr %s "%s" "%s" "%s"' % (root, key, val, data))


def _emit_exec(add, cmd, proj):
    c = expand_placeholders(cmd.get("cmd", ""), proj).strip()
    if not c:
        return
    c_ns = c.replace("'", "$'")
    if cmd.get("silent", True):
        add("  nsExec::ExecToLog '%s'" % c_ns)
    else:
        add("  Exec '%s'" % c_ns)
    if cmd.get("wait", True):
        add("  Pop $0")


def _estimate_size_kb(proj):
    total = 0
    for sec in proj["sections"]:
        for fe in sec.get("files", []):
            try:
                total += os.path.getsize(fe.get("src", ""))
            except OSError:
                pass
        for rf in sec.get("folders", []):
            src = rf.get("src", "")
            if os.path.isdir(src):
                for dp, _, fs in os.walk(src):
                    for f in fs:
                        try:
                            total += os.path.getsize(os.path.join(dp, f))
                        except OSError:
                            pass
    return max(1, total // 1024)


_CUR_PROJ = None
