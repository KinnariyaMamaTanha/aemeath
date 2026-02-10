# -*- mode: python ; coding: utf-8 -*-
"""Cross-platform PyInstaller spec for Aemeath desktop pet.

Aggressively excludes unused PySide6/Qt modules to minimise output size.
Only QtCore, QtGui, QtWidgets (and QtDBus on Linux) are needed.

Works on both Linux and Windows — library exclusion patterns adapt
automatically based on the build platform.
"""

import os
import sys

block_cipher = None
IS_WINDOWS = sys.platform == "win32"

# ---------------------------------------------------------------------------
# Modules to EXCLUDE — everything we don't use
# ---------------------------------------------------------------------------
_EXCLUDE_QT_MODULES = [
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DRender",
    "PySide6.QtBluetooth",
    "PySide6.QtCharts",
    "PySide6.QtConcurrent",
    "PySide6.QtDataVisualization",
    "PySide6.QtDesigner",
    "PySide6.QtGraphs",
    "PySide6.QtGraphsWidgets",
    "PySide6.QtHelp",
    "PySide6.QtHttpServer",
    "PySide6.QtLocation",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtNetworkAuth",
    "PySide6.QtNfc",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtPrintSupport",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickControls2",
    "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtSensors",
    "PySide6.QtSerialBus",
    "PySide6.QtSerialPort",
    "PySide6.QtSpatialAudio",
    "PySide6.QtSql",
    "PySide6.QtStateMachine",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtTest",
    "PySide6.QtTextToSpeech",
    "PySide6.QtUiTools",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets",
    "PySide6.QtXml",
    # Non-Qt modules we definitely don't need
    "tkinter",
    "unittest",
    "email",
    "html",
    "http",
    "xmlrpc",
    "pydoc",
    "doctest",
    "lib2to3",
    "multiprocessing",
    "asyncio",
]

# On Windows, QtDBus is not available — exclude it too.
if IS_WINDOWS:
    _EXCLUDE_QT_MODULES.append("PySide6.QtDBus")

a = Analysis(
    ["src/aemeath/__main__.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("assets/gifs/*.gif", "assets/gifs"),
        ("assets/icons/aemeath.ico", "assets/icons"),
    ],
    hiddenimports=["aemeath", "aemeath.app", "aemeath.config", "aemeath.cursor", "aemeath.pet", "aemeath.sprite"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_EXCLUDE_QT_MODULES,
    noarchive=False,
    optimize=2,       # -OO: strip docstrings + asserts
    cipher=block_cipher,
)

# ---------------------------------------------------------------------------
# Remove large Qt native libraries that were pulled in despite excludes.
# Patterns adapt to the platform's naming convention:
#   Linux  : libQt6WebEngineCore.so.6
#   Windows: Qt6WebEngineCore.dll
# ---------------------------------------------------------------------------
_UNWANTED_QT_STEMS = (
    "WebEngine", "Quick", "Qml", "Designer", "Pdf", "ShaderTools",
    "3D", "Graphs", "Multimedia", "Spatial", "Charts",
    "DataVisualization", "Bluetooth", "Location", "Sensors",
    "SerialBus", "SerialPort", "Nfc", "HttpServer", "TextToSpeech",
    "WebSockets", "WebChannel", "RemoteObjects", "Scxml",
    "StateMachine", "Svg", "Test", "Help", "Concurrent",
    "OpenGL", "PrintSupport", "Sql", "Xml",
)

# Media codec libraries (only present on Linux)
_UNWANTED_MEDIA_PREFIXES_LINUX = (
    "libavcodec", "libavformat", "libavutil", "libswresample", "libswscale",
)


def _is_unwanted_binary(path: str) -> bool:
    """Return True if *path* is a Qt/media library we don't need."""
    basename = os.path.basename(path)
    for stem in _UNWANTED_QT_STEMS:
        if IS_WINDOWS:
            if basename.startswith(f"Qt6{stem}"):
                return True
        else:
            if basename.startswith(f"libQt6{stem}"):
                return True
    if not IS_WINDOWS:
        if basename.startswith(_UNWANTED_MEDIA_PREFIXES_LINUX):
            return True
    return False


a.binaries = [
    (name, path, typ)
    for name, path, typ in a.binaries
    if not _is_unwanted_binary(path)
]

# Strip unwanted Qt plugins (same directory names on both platforms).
_UNWANTED_PLUGIN_DIRS = {
    "qml", "QtWebEngine", "multimedia", "sqldrivers", "designer",
    "sceneparsers", "renderers", "geometryloaders", "position",
    "sensorgestures", "sensors", "texttospeech", "canbus",
}

a.datas = [
    (name, path, typ)
    for name, path, typ in a.datas
    if not any(
        seg in _UNWANTED_PLUGIN_DIRS
        for seg in name.split(os.sep)
    )
]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="aemeath",
    debug=False,
    bootloader_ignore_signals=False,
    strip=not IS_WINDOWS,    # strip debug symbols (Linux only; breaks on Windows)
    upx=True,                # compress with UPX if available
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon="assets/icons/aemeath.ico",
)
