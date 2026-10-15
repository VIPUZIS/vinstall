#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CREATE.py — компилятор vInstallerCreator.exe.

Официальный сборочный скрипт проекта **vInstaller Creator**.  Собирает
полноценный standalone-EXE (или onedir-дистрибутив) из исходников через
PyInstaller, генерирует иконку приложения, version-info ресурс, spec-файл
и контрольные суммы собранного бинарника.

Использование:
    python CREATE.py                     # one-file EXE (для Windows-хоста)
    python CREATE.py --onedir            # папка-дистрибутив (быстрый старт)
    python CREATE.py --clean             # удалить build/ dist/ и .spec
    python CREATE.py --check             # только проверка окружения сборки
    python CREATE.py --name MyApp --version 2.1.0.7
    python CREATE.py --noconsole         # GUI-режим (без окна консоли)
    python CREATE.py --icon path.ico     # своя иконка
    python CREATE.py --upx               # сжать исполняемый файл UPX (если доступен)
    python CREATE.py --target windows    # форсировать флаги под Windows-сборку
    python CREATE.py --dry-run           # показать команду без запуска

Выход:
    dist/vInstallerCreator(.exe)  +  dist/checksums.sha256.txt  +  build/build_report.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import time

# ---------------------------------------------------------------------------
# Константы сборки
# ---------------------------------------------------------------------------

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(ROOT, "vinstaller", "src")
BUILD_DIR = os.path.join(ROOT, "build")
DIST_DIR = os.path.join(ROOT, "dist")
ASSETS_DIR = os.path.join(ROOT, "vinstaller", "assets")

APP_NAME_DEFAULT = "vInstallerCreator"
APP_VERSION_DEFAULT = "1.0.0.0"
PUBLISHER = "My Company"
DESCRIPTION = "vInstaller Creator — графический создатель установщиков EXE (NSIS)"
COPYRIGHT_TMPL = "(C) {YEAR} {PUBLISHER}. Все права защищены."

ENTRY_GUI = os.path.join(SRC_DIR, "vinstaller.py")      # main() GUI-приложения
ENTRY_CLI = os.path.join(SRC_DIR, "vic-cli.py")          # main() CLI-утилиты
CORE_MODULE = "src.core"

HIDDEN_IMPORTS = [
    "tkinter",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "tkinter.ttk",
    "tkinter.colorchooser",
    "json",
    "struct",
    "copy",
    "re",
]


# ---------------------------------------------------------------------------
# Утилиты вывода
# ---------------------------------------------------------------------------

USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text


def info(msg):   print(_c("[INFO ] ", "36") + msg)
def ok(msg):     print(_c("[OK   ] ", "32") + msg)
def warn(msg):   print(_c("[WARN ] ", "33") + msg)
def fail(msg):   print(_c("[ERROR] ", "31") + msg)
def step(msg):   print("\n" + _c("=" * 64, "1") + "\n" + _c(f"  {msg}", "1") + "\n" + _c("=" * 64, "1"))


# ---------------------------------------------------------------------------
# Версия / version-info
# ---------------------------------------------------------------------------

def normalize_version(v: str) -> str:
    parts = [p for p in (v or "").strip().split(".") if p.isdigit()]
    while len(parts) < 4:
        parts.append("0")
    return ".".join(parts[:4])


def render_version_info(dest_path: str, exe_name: str, version: str) -> str:
    """Подставляет значения в шаблон version_info.txt и пишет готовый ресурс."""
    tpl_file = os.path.join(SRC_DIR, "version_info.txt")
    vp = normalize_version(version)
    a, b, c_, d = (int(x) for x in vp.split("."))
    mapping = {
        "<FILE_MS>": str(a),
        "<FILE_LS>": str((b << 16) | c_),
        "<PROD_MS>": str(a),
        "<PROD_LS>": str((b << 16) | c_),
        "<COMPANY>": PUBLISHER,
        "<DESCRIPTION>": DESCRIPTION,
        "<FILE_VERSION>": vp,
        "<PRODUCT_VERSION>": vp,
        "<PRODUCT_NAME>": exe_name.replace(".exe", ""),
        "<COPYRIGHT>": COPYRIGHT_TMPL.format(YEAR=time.localtime().tm_year, PUBLISHER=PUBLISHER),
    }
    if os.path.isfile(tpl_file):
        with open(tpl_file, "r", encoding="utf-8") as f:
            text = f.read()
    else:  # fallback — если шаблон потерян, собираем ресурс на лету
        text = (
            "VSVersionInfo(\n"
            "  ffi=FixedFileInfo(filevers=(%(FILE_MS)s, %(FILE_LS)s, 0, 0),\n"
            "    prodvers=(%(PROD_MS)s, %(PROD_LS)s, 0, 0), mask=0x3f, flags=0x0,\n"
            "    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),\n"
            "  kids=[StringFileInfo([StringTable('040904b0', ["
            "StringStruct('CompanyName', '%(COMPANY)s'),\n"
            "StringStruct('FileDescription', '%(DESCRIPTION)s'),\n"
            "StringStruct('FileVersion', '%(FILE_VERSION)s'),\n"
            "StringStruct('InternalName', 'vInstallerCreator'),\n"
            "StringStruct('LegalCopyright', '%(COPYRIGHT)s'),\n"
            "StringStruct('OriginalFilename', 'vInstallerCreator.exe'),\n"
            "StringStruct('ProductName', '%(PRODUCT_NAME)s'),\n"
            "StringStruct('ProductVersion', '%(PRODUCT_VERSION)s')])]),\n"
            "  VarFileInfo([VarStruct('Translation', [1033, 1200])])]\n)\n"
        ) % mapping
    for k, v in mapping.items():
        text = text.replace(k, v)
    out = dest_path
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    return out


# ---------------------------------------------------------------------------
# Иконка (генерируется без внешних зависимостей)
# ---------------------------------------------------------------------------

def _ico_header_and_png_or_bmp(entries):
    """Собирает ICO-контейнер из списка (width, height, bmp_bytes)."""
    hdr = struct.pack("<HHH", 0, 1, len(entries))
    dir_ = b""
    body = b""
    offset = 6 + 16 * len(entries)
    for w, h, data in entries:
        dw = 0 if w >= 256 else w
        dh = 0 if h >= 256 else h
        dir_ += struct.pack("<BBBBHHII", dw, dh, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
        body += data
    return hdr + dir_ + body


def _bmp_dib(w, h, argb_rows):
    """DIB (BITMAPINFOHEADER + пиксели BGRA снизу вверх + AND-маска) для ICO."""
    rowsize = w * 4
    pixels = bytearray()
    for y in range(h - 1, -1, -1):
        for x in range(w):
            r, g, b, a = argb_rows[y][x]
            pixels += bytes((b, g, r, a))
    andmask_row = ((w + 31) // 32) * 4
    andmask = b"\x00" * (andmask_row * h)
    dib = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, len(pixels) + len(andmask), 0, 0, 0, 0)
    return dib + bytes(pixels) + andmask


def generate_icon(path: str) -> str:
    """Рисунок: синий круг + белая «стрела установки вниз» + база. sizes 16..256."""
    sizes = [16, 24, 32, 48, 64, 128, 256]
    entries = []
    for s in sizes:
        img = [[(0, 0, 0, 0) for _ in range(s)] for _ in range(s)]
        cx = cy = (s - 1) / 2.0
        r_out = s * 0.47
        r_in = s * 0.40
        blue = (46, 109, 164, 255)
        lblue = (91, 155, 213, 255)
        white = (255, 255, 255, 255)
        for y in range(s):
            for x in range(s):
                dx, dy = x - cx, y - cy
                d = (dx * dx + dy * dy) ** 0.5
                if d <= r_out:
                    col = blue if d > r_in else lblue
                    # стрелка вниз: вертикальный стержень + треугольник
                    shaft_w = max(1, int(s * 0.09))
                    tri_h = s * 0.26
                    tri_y0 = cy + s * 0.02
                    if abs(dx) <= shaft_w and tri_y0 - s * 0.30 <= dy <= tri_y0:
                        col = white
                    elif dy > tri_y0 - s * 0.02 and dy <= tri_y0 - s * 0.02 + tri_h * 0.55:
                        half = (tri_h * 0.55 - (dy - (tri_y0 - s * 0.02))) / (tri_h * 0.55) * s * 0.22
                        if abs(dx) <= half:
                            col = white
                    # «подставка» — горизонтальная черта внизу круга
                    if s * 0.30 <= dy <= s * 0.30 + max(1, s * 0.06) and abs(dx) <= s * 0.22:
                        col = white
                    img[y][x] = col
        entries.append((s, s, _bmp_dib(s, s, img)))
    data = _ico_header_and_png_or_bmp(entries)
    with open(path, "wb") as f:
        f.write(data)
    return path


# ---------------------------------------------------------------------------
# Проверки окружения
# ---------------------------------------------------------------------------

def check_python(min_ver=(3, 8)):
    cur = sys.version_info[:2]
    if cur < min_ver:
        fail(f"Нужен Python {min_ver[0]}.{min_ver[1]}+, найден {cur[0]}.{cur[1]}")
        return False
    info(f"Python {platform.python_version()} ({sys.executable})")
    return True


def check_entrypoints():
    missing = [p for p in (ENTRY_GUI,) if not os.path.isfile(p)]
    for m in missing:
        fail(f"Не найден входной модуль: {m}")
    return not missing


def get_pyinstaller():
    try:
        import PyInstaller  # noqa: F401
        ver = PyInstaller.__version__
        info(f"PyInstaller установлен: {ver}")
        return True
    except ImportError:
        warn("PyInstaller не найден — пробую установить автоматически…")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "pyinstaller"])
            import PyInstaller  # noqa: F401
            ok(f"PyInstaller установлен: {PyInstaller.__version__}")
            return True
        except Exception as e:
            fail(f"Не удалось установить PyInstaller: {e}")
            return False


def host_is_windows():
    return platform.system() == "Windows"


# ---------------------------------------------------------------------------
# Spec-файл
# ---------------------------------------------------------------------------

def write_spec(args, icon_path, vi_path, spec_path):
    datas_entries = []
    for folder in (ASSETS_DIR, os.path.join(ROOT, "vinstaller", "templates"),
                   os.path.join(ROOT, "vinstaller", "examples")):
        if os.path.isdir(folder) and os.listdir(folder):
            datas_entries.append(f"    (r'{folder}', '{os.path.basename(folder)}'),")
    datas_block = "[\n%s\n]" % "\n".join(datas_entries) if datas_entries else "[]"

    console = "True" if args.console else "False"
    debug = "True" if args.debug else "False"
    icon_line = f"icon=r'{icon_path}'" if icon_path else "icon=None"
    upx_line = "True" if args.upx else "False"

    script = f"""# -*- mode: python ; coding: utf-8 -*-
# Сгенерировано CREATE.py {time.strftime('%Y-%m-%d %H:%M:%S')} — не редактируйте вручную.

a = Analysis(
    [r'{args.entry}'],
    pathex=[r'{ROOT}', r'{SRC_DIR}'],
    binaries=[],
    datas={datas_block},
    hiddenimports={json.dumps(HIDDEN_IMPORTS)},
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=['pytest', 'setuptools', 'pip', 'wheel'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    {'a.binaries,' if not args.onedir else ''}
    {'a.zipfiles,' if not args.onedir else ''}
    {'a.datas,' if not args.onedir else ''}
    name=r'{args.name}',
    debug={debug},
    bootloader_ignore_signals=False,
    strip=False,
    upx={upx_line},
    upx_exclude=[],
    runtime_tmpdir=None,
    console={console},
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    {icon_line},
    version=r'{vi_path}',
)
"""
    if args.onedir:
        script += f"""
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx={upx_line},
    upx_exclude=[],
    name=r'{args.name}',
)
"""
    with open(spec_path, "w", encoding="utf-8") as f:
        f.write(script)
    return spec_path


# ---------------------------------------------------------------------------
# Сборка
# ---------------------------------------------------------------------------

def run_pyinstaller(args, spec_path):
    cmd = [sys.executable, "-m", "PyInstaller",
           "--noconfirm",
           "--distpath", DIST_DIR,
           "--workpath", os.path.join(BUILD_DIR, "pyi-work"),
           spec_path]  # spec уже лежит в BUILD_DIR — --specpath не нужен
    if args.clean_build:
        cmd.append("--clean")
    info("Команда: " + " ".join(cmd))
    if args.dry_run:
        warn("--dry-run: сборка пропущена.")
        return -1  # -1 = «не собирали», чтобы main не искал выходной файл
    env = os.environ.copy()
    env.setdefault("PYINSTALLER_CONFIG_DIR", os.path.join(BUILD_DIR, "pyi-config"))
    proc = subprocess.run(cmd, cwd=ROOT, env=env)
    return proc.returncode


def find_output(args):
    ext = ".exe" if (host_is_windows() or args.target == "windows") else ""
    if args.onedir:
        p = os.path.join(DIST_DIR, args.name, args.name + ext)
    else:
        p = os.path.join(DIST_DIR, args.name + ext)
    return p if os.path.exists(p) else None


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def smoke_test(exe_path):
    """Запуск собранного бинарника с --selftest (если он это поддерживает)."""
    if not os.path.isfile(exe_path):
        return None
    try:
        r = subprocess.run([exe_path, "--selftest"], capture_output=True, text=True, timeout=120)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return None, str(e)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        prog="CREATE.py",
        description="Компилятор vInstallerCreator.exe (обёртка над PyInstaller)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--name", default=APP_NAME_DEFAULT, help="имя выходного файла")
    ap.add_argument("--version", default=APP_VERSION_DEFAULT, help="версия вида 1.0.0.0 для version-info")
    ap.add_argument("--onedir", action="store_true", help="собрать папку-дистрибутив вместо одного файла")
    ap.add_argument("--console", action="store_true", help="оставить консольное окно (по умолчанию GUI без консоли)")
    ap.add_argument("--noconsole", dest="console", action="store_false", help="GUI-режим, окно консоли скрыто")
    ap.set_defaults(console=False)
    ap.add_argument("--icon", default="", help="путь к своему .ico (иначе генерируется автоматически)")
    ap.add_argument("--upx", action="store_true", help="разрешить сжатие UPX (если upx в PATH)")
    ap.add_argument("--debug", action="store_true", help="debug-сборка PyInstaller")
    ap.add_argument("--clean", action="store_true", help="удалить build/, dist/ и .spec и выйти")
    ap.add_argument("--clean-build", action="store_true", help="--clean для PyInstaller перед сборкой")
    ap.add_argument("--check", action="store_true", help="только проверить окружение сборки")
    ap.add_argument("--dry-run", action="store_true", help="показать команду PyInstaller без запуска")
    ap.add_argument("--target", choices=["auto", "windows", "linux"], default="auto",
                    help="целевая ОС (влияет на расширение выхода и подсказки)")
    ap.add_argument("--entry", default=ENTRY_GUI, help="входной скрипт (GUI по умолчанию)")
    ap.add_argument("--with-cli-tool", action="store_true", help="дополнительно собрать вик CLI vic-cli как второй EXE")
    return ap.parse_args(argv)


def do_clean():
    removed = []
    for d in (BUILD_DIR, DIST_DIR):
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
            removed.append(d)
    for sp in (os.path.join(ROOT, f"{APP_NAME_DEFAULT}.spec"),
               os.path.join(BUILD_DIR, f"{APP_NAME_DEFAULT}.spec")):
        if os.path.isfile(sp):
            os.remove(sp)
            removed.append(sp)
    if removed:
        ok("Удалено: " + ", ".join(removed))
    else:
        info("Нечего удалять — build/dist отсутствуют.")


def main(argv=None):
    args = parse_args(argv)
    t0 = time.time()

    step("vInstaller Creator — компилятор EXE (CREATE.py)")
    info(f"Хост: {platform.system()} {platform.release()} ({platform.machine()})")
    info(f"Цель: {args.target if args.target != 'auto' else ('windows' if host_is_windows() else 'linux (кросс-компиляция EXE невозможна)')}")

    if args.clean:
        do_clean()
        return 0

    step("Проверка окружения")
    if not check_python():
        return 2
    if not check_entrypoints():
        return 2
    if not get_pyinstaller():
        return 2
    if args.check:
        ok("Окружение сборки готово.")
        return 0

    if not host_is_windows() and args.target == "auto":
        warn("Сборка идёт не на Windows: PyInstaller создаст бинарник для текущей ОС.")
        warn("Для настоящего vInstallerCreator.exe запустите CREATE.py на Windows")
        warn("(или используйте GitHub Actions/windows-latest — workflow прилагается).")

    os.makedirs(BUILD_DIR, exist_ok=True)
    os.makedirs(DIST_DIR, exist_ok=True)

    step("Ресурсы приложения")
    icon_path = args.icon or os.path.join(ASSETS_DIR, "app.ico")
    if args.icon:
        ok(f"Иконка пользователя: {icon_path}")
    else:
        os.makedirs(ASSETS_DIR, exist_ok=True)
        generate_icon(icon_path)
        ok(f"Сгенерирована иконка: {icon_path} (16–256 px)")
    vi_path = render_version_info(os.path.join(BUILD_DIR, "version_info_generated.txt"),
                                  args.name + (".exe" if host_is_windows() or args.target == "windows" else ""),
                                  args.version)
    ok(f"Version-info ресурс: {vi_path}")

    step("Генерация spec-файла")
    spec_path = write_spec(args, icon_path if os.path.isfile(icon_path) else "", vi_path,
                           os.path.join(BUILD_DIR, f"{args.name}.spec"))
    ok(f"Spec: {spec_path}")

    step("Сборка через PyInstaller")
    rc = run_pyinstaller(args, spec_path)
    if rc == -1:  # --dry-run
        ok("Spec-файл готов; dry-run завершён без ошибки.")
        return 0
    if rc != 0:
        fail(f"PyInstaller завершился с кодом {rc}")
        return 1

    exe_path = find_output(args)
    if not exe_path:
        fail("Собранный файл не найден в dist/ — проверьте вывод PyInstaller выше.")
        return 1
    size_mb = os.path.getsize(exe_path) / (1024 * 1024)
    digest = sha256_file(exe_path)
    ok(f"Готово: {exe_path} ({size_mb:.1f} MB)")
    ok(f"SHA-256: {digest}")

    step("Проверочный запуск (--selftest)")
    code, out = smoke_test(exe_path)
    if code is None:
        warn("Самотест пропущен (бинарник недоступен для запуска на этом хосте).")
    elif code == 0:
        ok("Самотест пройден.")
        for ln in out.strip().splitlines()[-8:]:
            info("  " + ln)
    else:
        warn(f"Самотест вернул код {code}:")
        for ln in out.strip().splitlines()[-12:]:
            warn("  " + ln)

    checksums_path = os.path.join(DIST_DIR, "checksums.sha256.txt")
    with open(checksums_path, "w", encoding="utf-8") as f:
        f.write(f"{digest}  {os.path.basename(exe_path)}\n")
    report = {
        "app": args.name,
        "version": normalize_version(args.version),
        "mode": "onedir" if args.onedir else "onefile",
        "console": bool(args.console),
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "host": f"{platform.system()} {platform.release()} {platform.machine()}",
        "python": platform.python_version(),
        "output": exe_path,
        "size_mb": round(size_mb, 2),
        "sha256": digest,
        "duration_sec": round(time.time() - t0, 1),
        "selftest_exit": code,
    }
    with open(os.path.join(BUILD_DIR, "build_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    ok(f"Отчёт: {os.path.join(BUILD_DIR, 'build_report.json')}")
    ok(f"Контрольные суммы: {checksums_path}")

    step("СБОРКА ЗАВЕРШЕНА")
    ok(f"{exe_path}")
    info("Теперь vInstallerCreator умеет создавать .exe установщики (через NSIS/makensis).")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        fail("Прервано пользователем.")
        sys.exit(130)
