# vInstaller Creator

**Графический «создатель» EXE-установщиков для Windows на Python.**

vInstaller Creator — это desktop-приложение (Tkinter GUI + CLI), которое позволяет
визуально настроить проект установщика (страницы мастера, компоненты, файлы, ярлыки,
реестр, внешний вид, лицензию и т. д.) и собрать из него полноценный **.exe-установщик**
на базе **NSIS** (Nullsoft Scriptable Install System).

Сам сервис распространяется как один standalone-файл **`vInstallerCreator.exe`**,
который компилируется из исходников этим репозиторием через скрипт **`CREATE.py`**
(обёртка над PyInstaller).

> ⚠️ Важно не путать два разных EXE:
>
> | Что это | Как получается | Где лежит |
> |---|---|---|
> | **vInstallerCreator.exe** — сам сервис/приложение | `python CREATE.py` (PyInstaller) | `dist/vInstallerCreator.exe` |
> | **Установщик вашего приложения** (`MyApp-setup.exe`) | внутри vInstallerCreator кнопка «Собрать» или CLI `build` (NSIS/makensis) | куда укажете в проекте |
>
> В этом README раздел **«Сборка vInstallerCreator.exe»** описывает компиляцию именно **сервиса**,
> а не установщика.

---

## Содержание

1. [Возможности](#возможности)
2. [Требования](#требования)
3. [Структура проекта](#структура-проекта)
4. [Быстрый старт (запуск из исходников)](#быстрый-старт-запуск-из-исходников)
5. [Сборка vInstallerCreator.exe (сам сервис, НЕ установщик!)](#сборка-vinstallercreatorexe-сам-сервис-не-установщик)
6. [CREATE.py — параметры командной строки](#createpy--параметры-командной-строки)
7. [CI-сборка exe на Windows (GitHub Actions)](#ci-сборка-exe-на-windows-github-actions)
8. [Работа в vInstallerCreator: создание .exe-установщика](#работа-в-vinstallercreator-создание-exe-установщика)
9. [CLI-режим (headless-сборка установщиков)](#cli-режим-headless-сборка-установщиков)
10. [Формат проекта `.vicproj`](#формат-проекта-vicproj)
11. [Проверка собранного exe (selftest)](#проверка-собранного-exe-selftest)
12. [Устранение неполадок](#устранение-неполадок)
13. [Лицензия](#лицензия)

---

## Возможности

**GUI (Tkinter, вкладки):**

- 📝 Метаданные: имя продукта, версия/сборка, издатель, URL (about/update/readme),
  авторские права, язык мастера (+ резервный), иконка `.ico`, файл лицензии `.txt/.rtf`;
- 🧭 Страницы мастера установки: приветствие, лицензия, выбор папки, выбор
  компонентов, подтверждение, прогресс, готово (+ собственные тексты);
- 📦 Компоненты (sections): обязательные/опциональные, размеры, вложенность;
- 🗂 Файлы и папки: добавление файлов/каталогов в компоненты, перезапись,
  исключение масок;
- 🔗 Ярлыки: Пуск / рабочий стол / QuickLaunch / common-версии, аргументы,
  иконка с индексом, описание;
- 🧩 Записи реестра: HKLM/HKCU/HKCC, ключ/значение/тип, ассоциации файлов;
- ⚙️ Параметры установки: папка по умолчанию с плейсхолдерами, уровень прав
  (`none/user/highest/admin/lock/auto`), x86/x64, блокировка второго экземпляра
  (mutex), определение старой версии и режим обновления (спросить / удалить
  сначала / сохранить), проверка требований (VC++ Redist, .NET, мин. Windows),
  сжатие zlib/bzip2/LZMA (solid, размер словаря), запись uninstall-реестра,
  произвольные NSIS-директивы (`custom_ini`);
- 🎨 Внешний вид: MUI2/classic, modern/classic wizard, цвета header/sidebar
  (битмапы 800×150 / 164×400 генерируются автоматически или свои картинки),
  брендирование, тексты кнопок, лицензионный режим (checkbox/radio);
- 🪟 Диалоги и сообщения, license/agreement, доп. страницы;
- ▶️ Post-install запуск файла/команды, customExec/customInstall;
- ✅ Живая валидация проекта (ошибки и предупреждения);
- 💾 Сохранение/загрузка проекта в JSON `*.vicproj`;
- 🔨 One-click сборка `.exe` установщика с логом компиляции NSIS.

**Ядро / CLI:**

- Генерация `.nsi` скрипта NSIS без GUI (`generate`);
- Полная headless-сборка установщика (`build`);
- Создание шаблона проекта (`new`);
- Проверка проекта (`validate`);
- Само-тест работоспособности ядра (`selftest`) — используется CREATE.py после сборки.

**CREATE.py (компилятор сервиса):**

- Сборка через PyInstaller: one-file или one-dir;
- Автогенерация ICO-иконки приложения (16–256 px, без внешних зависимостей);
- Автогенерация version-info ресурса (FileVersion/ProductName/© — из шаблона
  `vinstaller/src/version_info.txt`);
- Генерация `.spec`-файла, SHA-256 контрольных суммы, JSON отчёта о сборке;
- Автоматический smoke-test собранного бинарника (`--selftest`);
- Опции: UPX, debug-сборка, свой `.ico`, консоль/GUI, dry-run, чистка.

---

## Требования

### Для работы vInstallerCreator (создания установщиков)

| Компонент | Версия | Зачем |
|---|---|---|
| Windows | 7/8/10/11 | целевая платформа установщиков |
| **NSIS** | 3.x (рекомендуется 3.08+) | компиляция `.nsi` → `.exe` установщика |
| (опц.) Unicode-сборка NSIS | — | кириллица в текстах установщика |

NSIS: <https://nsis.sourceforge.io/Download>. После установки `makensis.exe`
обычно лежит в `C:\Program Files (x86)\NSIS\`. Приложение ищет его автоматически
в PATH и типовых каталогах; путь можно указать вручную (`--makensis` в CLI).

> На Linux/macOS можно запускать GUI и генерировать `.nsi`, но **финальная сборка
> .exe-установщика требует makensis** (Windows-нативный; под Linux существует
> переносимая сборка NSIS — см. [устранение неполадок](#устранение-неполадок)).

### Для сборки vInstallerCreator.exe из исходников

| Компонент | Версия |
|---|---|
| Python | 3.8+ (рекомендуется 3.11/3.12, 64-bit) |
| pyinstaller | 6.x (`pip install pyinstaller`) |
| tkinter | входит в официальный установщик python.org |
| ОС для сборки `.exe` | **Windows** (PyInstaller не кросс-компилирует) |
| (опц.) UPX | 4.x — для сжатия (`--upx`) |

---

## Структура проекта

```text
.
├── CREATE.py                     # компилятор vInstallerCreator.exe (обёртка PyInstaller)
├── README.md                     # этот файл
├── .gitignore
└── vinstaller/                   # исходники приложения
    ├── src/
    │   ├── vinstaller.py         # Tkinter GUI + встроенный NSIS-компилятор + CLI-режимы
    │   ├── core.py               # модель проекта, валидация, генерация NSI, ресурсы
    │   └── version_info.txt      # шаблон Win32 version-info для CREATE.py
    ├── assets/
    │   └── app.ico               # иконка приложения (создаётся CREATE.py автоматически)
    └── examples/
        ├── demo.vicproj          # пример проекта установщика
        └── demo_app/             # тестовые файлы для демо-установщика
```

После сборки появляются (в `.gitignore`):

```text
build/                          # временные артефакты PyInstaller, spec, version-info, build_report.json
dist/
├── vInstallerCreator.exe       # ← ГОТОВЫЙ СЕРВИС (one-file)
└── checksums.sha256.txt        # SHA-256 собранного exe
```

---

## Быстрый старт (запуск из исходников)

Без сборки exe — для разработки и проверки:

```bash
# Windows
cd vinstaller
python src\vinstaller.py            # открыть GUI

# проверка ядра без GUI
python src\vinstaller.py selftest

# генерация NSI из примера
python src\vinstaller.py generate examples\demo.vicproj --out out.nsi
```

```bash
# Linux/macOS (аналогично, слеши /)
python3 vinstaller/src/vinstaller.py
```

---

## Сборка vInstallerCreator.exe (сам сервис, НЕ установщик!)

Это **главный раздел**: как получить исполняемый файл самого приложения
`vInstallerCreator.exe`. Здесь компилируется **сервис-создатель установщиков**,
а не какой-либо установщик.

### Шаг 1. Подготовка окружения (на Windows)

1. Установите **Python 3.11+ (64-bit)** с [python.org](https://www.python.org/downloads/)
   (галочка *Add Python to PATH*; tkinter входит в комплект).
2. Откройте `cmd` / PowerShell в корне проекта и установите PyInstaller:

   ```powershell
   pip install pyinstaller
   ```

   (CREATE.py может установить PyInstaller сам, если его нет, но явная установка надёжнее.)

3. Проверьте окружение сборки:

   ```powershell
   python CREATE.py --check
   ```

   Ожидаемый вывод: версия Python, версия PyInstaller, `[OK] Окружение сборки готово.`

### Шаг 2. Сборка

Простейшая команда (one-file GUI-приложение):

```powershell
python CREATE.py
```

Что делает скрипт:

1. проверяет Python / входные модули / наличие PyInstaller;
2. генерирует иконку `vinstaller/assets/app.ico` (если не задана своя);
3. подставляет версию/издателя в `build/version_info_generated.txt`;
4. пишет `build/vInstallerCreator.spec`;
5. запускает PyInstaller (`--noconfirm`, dist → `dist/`, work → `build/pyi-work`);
6. находит выходной `dist/vInstallerCreator.exe`, считает SHA-256;
7. прогоняет smoke-test: `dist\vInstallerCreator.exe --selftest`;
8. сохраняет `dist/checksums.sha256.txt` и `build/build_report.json`.

Результат:

```text
dist\
├── vInstallerCreator.exe     # ← САМ СЕРВИС, одиночный файл ~15–30 MB
└── checksums.sha256.txt
```

Запуск: двойной клик по `vInstallerCreator.exe` → открывается GUI создателя
установщиков. Сервис **не требует** установленного Python. Для сборки
установщиков на машине всё равно нужен NSIS (см. требования).

### Варианты сборки

```powershell
:: быстрая сборка "папкой" (меньше антивирусных ложных срабатываний, старт быстрее)
python CREATE.py --onedir
:: результат: dist\vInstallerCreator\vInstallerCreator.exe + _internal\

:: задать имя и версию (попадёт в свойства файла Windows)
python CREATE.py --name MyInstallerCreator --version 2.1.0.7

:: консольная версия (удобно отлаживать CLI/ошибки)
python CREATE.py --console

:: своя иконка вместо автогенерируемой
python CREATE.py --icon C:\path\to\my.ico

:: сжать UPX (если upx.exe в PATH)
python CREATE.py --upx

:: debug-сборка PyInstaller
python CREATE.py --debug

:: только посмотреть команду PyInstaller, без сборки
python CREATE.py --dry-run

:: полная пересборка с нуля
python CREATE.py --clean-build

:: удалить build/, dist/ и spec
python CREATE.py --clean
```

### Сборка не на Windows (Linux/macOS)

PyInstaller собирает бинарник **только под текущую ОС**. На Linux CREATE.py создаст
`dist/vInstallerCreator` (ELF, без `.exe`) — это нормально для проверки ядра, но
для настоящего `.exe` нужны:

- либо запуск `python CREATE.py` на Windows,
- либо CI с runner `windows-latest` (см. следующий раздел).

CREATE.py честно предупредит об этом и соберёт артефакт для хостовой ОС
(`--target windows` форсирует подсказки/расширения, но не меняет реальную платформу выхода).

### Что проверяется после сборки

CREATE.py автоматически запускает собранный exe с флагом `--selftest`:

```text
[OK] Самотест пройден.
  vInstaller Creator selftest
  validate: OK
  generate_nsi: OK
  makensis: C:\Program Files (x86)\NSIS\makensis.exe   (или "not found")
  SELFTEST OK
```

Если NSIS на сборочной машине не установлен — строка `makensis: not found`
**не является ошибкой** сборки сервиса: exe собран корректно, NSIS понадобится
уже при создании установщиков.

---

## CREATE.py — параметры командной строки

| Флаг | По умолчанию | Описание |
|---|---|---|
| `--name NAME` | `vInstallerCreator` | имя выходного файла |
| `--version V` | `1.0.0.0` | версия `a.b.c.d` для version-info |
| `--onedir` | выкл. | папка-дистрибутив вместо одного файла |
| `--console` | выкл. | оставить окно консоли (по умолчанию GUI без консоли) |
| `--noconsole` | (значение по умолчанию) | GUI-режим, консоль скрыта — поведение по умолчанию |
| `--icon PATH` | авто-генерация | свой `.ico` для exe |
| `--upx` | выкл. | разрешить сжатие UPX (нужен `upx` в PATH) |
| `--debug` | выкл. | debug-сборка PyInstaller |
| `--clean` | — | удалить `build/`, `dist/`, `.spec` и выйти |
| `--clean-build` | выкл. | передать `--clean` PyInstaller перед сборкой |
| `--check` | — | только проверка окружения сборки |
| `--dry-run` | — | показать команду PyInstaller без запуска |
| `--target {auto,windows,linux}` | `auto` | целевая ОС (влияет на расширения/подсказки) |
| `--entry PATH` | GUI-точка входа | альтернативная точка входа |
| `--with-cli-tool` | выкл. | доп. CLI-exE вторым файлом (нужен отдельный entry; по умолчанию точка входа одна) |

Полезные комбинации:

```powershell
python CREATE.py --check                       # готова ли машина к сборке
python CREATE.py --dry-run                     # что будет выполнено
python CREATE.py --onedir --console            # отладочная быстрая сборка
python CREATE.py --name MyApp --version 1.2.0.0 --icon my.ico --upx
```

Артефакты сборки:

- `build/<Name>.spec` — сгенерированный spec (можно изучить/доработать);
- `build/version_info_generated.txt` — подставленный version-info ресурс;
- `build/build_report.json` — отчёт: версия, режим, размер, SHA-256, время, код selftest;
- `dist/checksums.sha256.txt` — контрольная сумма релизного exe.

---

## CI-сборка exe на Windows (GitHub Actions)

Так как `.exe` собирается только на Windows, самый воспроизводимый способ — CI.
Создайте `.github/workflows/build.yml`:

```yaml
name: Build vInstallerCreator.exe
on:
  push:
    tags: ["v*"]
  workflow_dispatch:

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install pyinstaller
      - name: Build exe
        shell: bash
        run: |
          VER="${GITHUB_REF_NAME#v}"
          python CREATE.py --version "${VER}.0" --target windows
      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: vInstallerCreator-win
          path: |
            dist/vInstallerCreator.exe
            dist/checksums.sha256.txt
```

---

## Работа в vInstallerCreator: создание .exe-установщика

Когда `vInstallerCreator.exe` собран и запущен, порядок действий такой:

Интерфейс состоит из 8 вкладок: **«Основное», «Установка», «Файлы и компоненты»,
«Ярлыки и реестр», «Интерфейс», «Страницы мастера», «Скрипты», «Сборка»**.

1. **Файл → Новый проект** (или откройте `vinstaller/examples/demo.vicproj`;
   Ctrl+N / Ctrl+O / Ctrl+S тоже работают).
2. **«Основное»** — имя продукта, версия, издатель, URL, язык, иконка и файл лицензии
   устанавливаемого приложения.
3. **«Установка»** — папка по умолчанию, уровень прав (`exec_level`), разрядность
   (`arch`), сжатие (zlib/bzip2/LZMA), режим обновления, требования (VC++/​.NET/версия ОС).
4. **«Файлы и компоненты»** — создайте секции-компоненты и добавьте в них файлы/папки.
5. **«Ярлыки и реестр»** — ярлыки (Пуск/рабочий стол), записи реестра, файловые ассоциации.
6. **«Интерфейс»** — стиль MUI2/classic, цвета header/sidebar (битмапы генерируются
   автоматически), брендирование, текст кнопки «Готово».
7. **«Страницы мастера»** — какие страницы показывать (приветствие, лицензия, папка,
   компоненты, подтверждение, прогресс, готово).
8. **«Скрипты»** — вставка произвольного NSIS-кода (`.onInit`, custom-функции и т. п.).
9. **Меню «Проект» → «Проверить проект»** — устраните сообщения уровня ERROR
   (WARN не блокируют сборку).
10. **Вкладка «Сборка»**: укажите имя итогового установщика (по умолчанию шаблон
    `{APPNAME}-{VERSION}-setup.exe`) и, если нужно, путь к `makensis.exe`; затем:
    - **«1. Сгенерировать NSI»** — получится готовый `.nsi` скрипт NSIS;
    - **«2. Собрать EXE (NSIS)»** — приложение вызовет `makensis` и покажет
      полный лог компиляции в окне журнала;
    - или **«▶ Полный цикл: проверить → NSI → EXE»** — всё одной кнопкой.
11. Готово: ваш `MyApp-1.0.0-setup.exe` создан. Проект сохранён в `*.vicproj` —
    его можно переиспользовать, передавать коллегам и вызывать в CI.

Если `makensis` не найден: установите NSIS 3.x или укажите путь к `makensis.exe`
(в GUI поле пути / в CLI `--makensis`).

---

## CLI-режим (headless-сборка установщиков)

Собранный `vInstallerCreator.exe` умеет работать без GUI — удобно для автоматизации:

```bat
:: создать шаблон проекта
vInstallerCreator.exe new myproject.vicproj

:: проверить проект
vInstallerCreator.exe validate myproject.vicproj

:: только cгенерировать NSI-скрипт
vInstallerCreator.exe generate myproject.vicproj --out installer.nsi

:: полная сборка установщика
vInstallerCreator.exe build myproject.vicproj --out-dir dist_setup
vInstallerCreator.exe build myproject.vicproj --makensis "C:\Program Files (x86)\NSIS\makensis.exe"

:: само-тест ядра
vInstallerCreator.exe selftest
```

Эквивалентно можно вызывать из исходников: `python vinstaller/src/vinstaller.py <команда> …`
и через универсальный флаг `vInstallerCreator.exe --cli <команда> …`.

Типовой CI-конвейер выпуска установщика:

```yaml
- run: choco install nsis -y
- run: vInstallerCreator.exe build installer.vicproj --makensis "C:\Program Files\NSIS\makensis.exe"
```

---

## Формат проекта `.vicproj`

Обычный JSON (UTF-8, человекочитаемый). Создаётся кнопкой «Новый проект» или CLI
`vInstallerCreator.exe new my.vicproj`. Ключевые секции (значения — из шаблона по умолчанию):

```jsonc
{
  "schema": 1,
  "meta": { "name": "Новая программа", "version": "1.0.0", "publisher": "My Company",
            "url_info": "", "icon": "", "license_file": "", "language": "ru",
            "fallback_language": "en", "build": "1", "comments": "" },
  "setup": { "default_dir": "C:\\Program Files\\{APPNAME}",
             "exec_level": "auto",          // none | user | highest | admin | lock | auto
             "arch": "x86",                 // x86 | x64
             "check_mutex": true, "detect_old_version": true,
             "upgrade_mode": "ask",         // ask | uninstall_first | keep
             "requires": { "vc_redist": false, "dotnet": "", "os_min": "" },
             "custom_ini": {} },            // сырые доп. директивы NSIS {директива: аргументы}
  "compression": { "method": "lzma",        // zlib | bzip2 | lzma
                   "solid": true, "dict_mb": 8 },
  "ui": { "style": "mui2", "wizard": "modern",
          "colors": { "header": "#FFFFFF", "sidebar": "#2E6DA4" /* и т. д. */ },
          "header_image": ["", ""],         // [путь, подпись]; пусто -> генерируется битмап
          "sidebar_image": ["", ""],
          "license_mode": "checkbox",       // checkbox | radiobuttons | off
          "branding": "{APPNAME} • {PUBLISHER}",
          "details_show": "hide" },
  "pages": { "welcome": true, "license": false, "components": true,
             "directory": true, "verify": false, "instfiles": true,
             "finish": true, "uninstall_confirm": true, "uninstall_finish": true },
  "install_types": [ { "id": 0, "name": "Полная", "sections": "*" },
                     { "id": 1, "name": "Типичная", "sections": "main,shortcuts" },
                     { "id": 2, "name": "Минимальная", "sections": "main" } ],
  "sections": [ { "id": "main", "name": "{APPNAME}", "size_kb": 0, "flags": "RO",
                  "types": [0, 1, 2], "files": [], "folders": [] },
                { "id": "shortcuts", "name": "Ярлыки", "flags": "",
                  "types": [0, 1], "files": [], "folders": [] } ],
  "shortcuts": [ { "section": "shortcuts", "where": "startmenu",   // startmenu | desktop | custom
                   "name": "{APPNAME}", "target": "{EXE}", "args": "",
                   "icon": "", "icon_index": 0, "description": "" } ],
  "file_ops": { "dirs": ["data", "logs"], "delete_files": [] },
  "registry": { "entries": [] },            // [{root,key,value,type,data}]
  "run": { "install_exec": [],               // [{cmd, section, silent, wait}]
           "uninstall_exec": [], "startup_run": "" },
  "scripts": { "pre_init": "", "leave_directory": "",
               "custom_function": "", "uninstall_custom": "" },
  "output": { "filename": "{APPNAME}-{VERSION}-setup.exe" }
}
```

Поддерживаемые подстановки в текстах: `{APPNAME}`, `{SHORTNAME}`, `{VERSION}`,
`{PUBLISHER}`, `{YEAR}`.

Полный рабочий пример: [`vinstaller/examples/demo.vicproj`](vinstaller/examples/demo.vicproj)
(файлы демо-приложения — в `vinstaller/examples/demo_app/`).

---

## Проверка собранного exe (selftest)

Любой собранный экземпляр сервиса проверяется одной командой:

```powershell
dist\vInstallerCreator.exe --selftest
echo %ERRORLEVEL%        :: 0 = ядро работоспособно
```

selftest выполняет: `default_project()` → `validate_project()` → `generate_nsi()`
в временный файл и поиск `makensis`. Именно этот тест CREATE.py запускает
автоматически после каждой сборки (результат — в `build/build_report.json`,
поле `selftest_exit`).

Контрольная сумма релиза:

```powershell
certutil -hashfile dist\vInstallerCreator.exe SHA256
:: сравните со значением в dist\checksums.sha256.txt
```

---

## Устранение неполадок

| Симптом | Причина / решение |
|---|---|
| CREATE.py: `Не найден входной модуль` | запуск не из корня репозитория; `cd` в папку с `CREATE.py` |
| `PyInstaller не найден` и авто-установка падает | офлайн-среда: `pip install pyinstaller` заранее из локального wheel |
| Сборка прошла, но exe не `.exe`, а без расширения | вы собираете на Linux/macOS — соберите на Windows или в CI |
| Антивирус удаляет one-file exe | ложное срабатывание PyInstaller-bootloader: используйте `--onedir`, либо подпишите exe |
| `SmartScreen: неизвестный издатель` | подпись кодом не выполнена — подпишите (`signtool`) или доверьте локально |
| selftest: `makensis: not found` | NSIS не установлен на этой машине — установите NSIS 3.x; сам сервис при этом исправен |
| GUI не открывается из exe | запустите `vInstallerCreator.exe --console` (пересоберите с `--console`) и посмотрите ошибку |
| Кириллица в установщике «кракозябрами» | нужна Unicode-сборка NSIS (современные 3.x — Unicode by default) |
| Ошибка валидации `error: ...` | GUI подсветит проблемное поле; CLI `validate` печатает список ошибок |
| want cross-build? | невозможно: PyInstaller всегда собирает под хостовую ОС — используйте windows-latest CI |

---

## Лицензия

Проект распространяется под лицензией MIT (см. `LICENSE`, если добавлен).
NSIS — отдельный продукт с собственной лицензией (zlib/libpng).

---

*Коротко: `pip install pyinstaller && python CREATE.py` → `dist\vInstallerCreator.exe` —
это **сам сервис**; уже он, в свою очередь, создаёт `.exe`-установщики ваших приложений.*
