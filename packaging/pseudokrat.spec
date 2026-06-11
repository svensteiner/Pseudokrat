# PyInstaller-Spec fuer Pseudokrat (Windows + macOS)
#
# Baut ZWEI Programme in EIN onedir-Bundle (dist/Pseudokrat/):
#   * Pseudokrat.exe      — Konsolen-CLI: 'setup' (Weg-Auswahl), 'watch'
#                           (Ordner-Loesung), 'install', 'anonymize', ...
#                           -> der Einstiegspunkt fuer Kunden ohne Python.
#   * Pseudokrat-GUI.exe  — das PySide6-Hauptfenster.
#
# Bauen:
#   pip install -e ".[gui,simple-mode,clipboard,watcher,ocr]" pyinstaller
#   pyinstaller packaging/pseudokrat.spec --noconfirm --clean
#
# onedir (kein onefile): schnellerer Start, AV-freundlicher, Inno-Setup-tauglich.

# ruff: noqa
# type: ignore
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent  # packaging/ -> ..
SRC = ROOT / "src"

block_cipher = None


def _optional_collect(pkg):
    """collect_all fuer optionale Pakete; leeres Ergebnis, wenn nicht installiert."""
    try:
        return collect_all(pkg)
    except Exception as exc:  # pragma: no cover - Build-Zeit-Diagnose
        print(f"[spec] WARN: '{pkg}' nicht gebundelt ({exc}).")
        return ([], [], [])


# ---- Hidden imports (dynamisch geladene Module) ----------------------------
hidden = collect_submodules("pseudokrat") + [
    "pseudokrat.recognizers.iban",
    "pseudokrat.recognizers.at_uid",
    "pseudokrat.recognizers.at_svnr",
    "pseudokrat.recognizers.de_steuer_id",
    "pseudokrat.recognizers.de_ust_id",
    "pseudokrat.recognizers.ch_ahv",
    "pseudokrat.recognizers.company",
    "pseudokrat.recognizers.person",
    "pseudokrat.recognizers.person_name",
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
    "pseudokrat.watcher",
]

datas = []
datas += collect_data_files("docx", include_py_files=False)
datas += collect_data_files("openpyxl", include_py_files=False)
datas += collect_data_files("reportlab", include_py_files=False)

binaries = []

# ---- Optionale Ordner-/OCR-Abhaengigkeiten --------------------------------
# PyMuPDF (PDF-Layout-Redaction) und RapidOCR (Text in Bildern). RapidOCR
# bringt ONNX-Modelle + YAML-Configs als Daten mit -> collect_all noetig.
for _pkg in ("pymupdf", "fitz", "rapidocr_onnxruntime", "onnxruntime", "cv2"):
    _d, _b, _h = _optional_collect(_pkg)
    datas += _d
    binaries += _b
    hidden += _h

# ML wird NICHT gebundelt (3-GB-Modell wird bei Bedarf nachgeladen).
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
    # Qt-Module, die die GUI nicht nutzt (nur QtCore/QtGui/QtWidgets noetig).
    # Spart >100 MB ungepackt (QML/Quick/Designer/OpenGL/Netzwerk).
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQuickControls2",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtNetwork",
    "PySide6.QtDesigner",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets",
    "PySide6.QtDBus",
    "PySide6.QtConcurrent",
    "PySide6.QtHelp",
    "PySide6.QtPrintSupport",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtUiTools",
    "PySide6.QtXml",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
]


def _prune_toc(toc):
    """Entfernt Ballast, den die Qt-/OpenCV-Hooks trotz excludes mitschleppen.

    * opengl32sw.dll      — Software-GL-Fallback (~20 MB); QtWidgets rendert
                            per Raster-Engine, OpenGL wird nicht genutzt.
    * opencv ffmpeg-DLL   — Video-Codec (~28 MB); OCR verarbeitet nur Bilder.
    * PySide6/qml/        — QML-Plugins; die GUI ist reines QtWidgets.
    * Qt-Uebersetzungen   — bis auf Deutsch (App-Sprache).
    """
    pruned = []
    for entry in toc:
        dest = entry[0].replace("\\", "/").lower()
        name = dest.rsplit("/", 1)[-1]
        if "opengl32sw" in name:
            continue
        if name.startswith("opencv_videoio_ffmpeg"):
            continue
        if "/qml/" in dest or dest.startswith("pyside6/qml"):
            continue
        if "/translations/" in dest and not name.startswith(("qt_de", "qtbase_de")):
            continue
        pruned.append(entry)
    return pruned

is_windows = sys.platform.startswith("win")
_icon_path = ROOT / "packaging" / "icon.ico"
# Icon nur setzen, wenn die Datei existiert — sonst bricht PyInstaller ab.
icon = str(_icon_path) if (is_windows and _icon_path.exists()) else None

# ---- Analyse 1: Konsolen-CLI ----------------------------------------------
a_cli = Analysis(
    [str(SRC / "pseudokrat" / "__main__.py")],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    excludes=excludes,
    noarchive=False,
    cipher=block_cipher,
)

# ---- Analyse 2: GUI --------------------------------------------------------
a_gui = Analysis(
    [str(SRC / "pseudokrat" / "gui" / "__main__.py")],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    # Nur die tatsaechlich genutzten Qt-Module (kein collect_submodules:
    # das zieht QML/Quick/Designer & Co. mit — >100 MB Ballast).
    hiddenimports=hidden
    + ["PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"],
    excludes=excludes,
    noarchive=False,
    cipher=block_cipher,
)

# Gemeinsame Abhaengigkeiten deduplizieren.
MERGE((a_cli, "Pseudokrat", "Pseudokrat"), (a_gui, "Pseudokrat-GUI", "Pseudokrat-GUI"))

pyz_cli = PYZ(a_cli.pure, a_cli.zipped_data, cipher=block_cipher)
exe_cli = EXE(
    pyz_cli,
    a_cli.scripts,
    [],
    exclude_binaries=True,
    name="Pseudokrat",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # Ordner-Watcher/Setup brauchen die Konsole
    icon=icon,
)

pyz_gui = PYZ(a_gui.pure, a_gui.zipped_data, cipher=block_cipher)
exe_gui = EXE(
    pyz_gui,
    a_gui.scripts,
    [],
    exclude_binaries=True,
    name="Pseudokrat-GUI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI
    icon=icon,
)

coll = COLLECT(
    exe_cli,
    _prune_toc(a_cli.binaries),
    a_cli.zipfiles,
    _prune_toc(a_cli.datas),
    exe_gui,
    _prune_toc(a_gui.binaries),
    a_gui.zipfiles,
    _prune_toc(a_gui.datas),
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Pseudokrat",
)

# macOS-App-Bundle (nur auf macOS).
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
