# PyInstaller-Spec für die Pseudokrat-GUI (Windows + macOS)
#
# Bauen:
#   pip install pyinstaller
#   pyinstaller packaging/pseudokrat.spec --noconfirm
#
# Output: dist/Pseudokrat/Pseudokrat.exe  (Windows)
#         dist/Pseudokrat.app             (macOS, via py2app-Workflow getrennt)
#
# Wir bauen onedir statt onefile:
#   - schnellerer Cold-Start (kein Extract beim Launch)
#   - Antivirus-Heuristiken stolpern seltener
#   - Inno-Setup kann das Verzeichnis 1:1 in ProgramFiles installieren

# ruff: noqa
# type: ignore
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent  # packaging/ → ../
SRC = ROOT / "src"

block_cipher = None

# Hidden imports — alles, was per dynamischem Import geladen wird
hidden = (
    collect_submodules("pseudokrat")
    + collect_submodules("PySide6")
    + [
        "pseudokrat.recognizers.iban",
        "pseudokrat.recognizers.at_uid",
        "pseudokrat.recognizers.at_svnr",
        "pseudokrat.recognizers.de_steuer_id",
        "pseudokrat.recognizers.de_ust_id",
        "pseudokrat.recognizers.ch_ahv",
        "pseudokrat.recognizers.company",
        "pseudokrat.recognizers.email",
        "pseudokrat.recognizers.phone",
        "pseudokrat.recognizers.url",
        "pseudokrat.recognizers.secret",
        "pseudokrat.recognizers.mandanten_nr",
        "pseudokrat.formats.txt_handler",
        "pseudokrat.formats.csv_handler",
        "pseudokrat.formats.docx_handler",
        "pseudokrat.formats.xlsx_handler",
        "pseudokrat.formats.pdf_handler",
    ]
)

datas = []
datas += collect_data_files("docx", include_py_files=False)
datas += collect_data_files("openpyxl", include_py_files=False)
datas += collect_data_files("reportlab", include_py_files=False)

# Optionale ML-Imports werden NICHT gebundelt — das 3-GB-Modell wird
# aus dem Wizard heraus on-demand heruntergeladen.
excludes = [
    "torch",
    "transformers",
    "huggingface_hub",
    "tensorflow",
    "numpy.tests",
    "pandas",
    "scipy",
    "matplotlib",
    "tkinter",
    "pytest",
    "mypy",
]


a = Analysis(
    [str(SRC / "pseudokrat" / "gui" / "__main__.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

is_windows = sys.platform.startswith("win")

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Pseudokrat",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI-App
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "packaging" / "icon.ico") if is_windows else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Pseudokrat",
)

# macOS-App-Bundle: nur erzeugen, wenn wir auf macOS bauen.
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Pseudokrat.app",
        icon=str(ROOT / "packaging" / "icon.icns"),
        bundle_identifier="com.pseudokrat.app",
        info_plist={
            "CFBundleName": "Pseudokrat",
            "CFBundleDisplayName": "Pseudokrat",
            "CFBundleShortVersionString": "0.1.0",
            "CFBundleVersion": "0.1.0",
            "NSHighResolutionCapable": True,
            "NSHumanReadableCopyright": "Copyright (c) 2026 Pseudokrat.",
            "LSMinimumSystemVersion": "11.0",
        },
    )
