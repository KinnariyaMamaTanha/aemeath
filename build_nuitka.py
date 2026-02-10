#!/usr/bin/env python3
"""Nuitka build script for Aemeath desktop pet.

Cross-platform compilation script that produces optimized standalone executables.
Much faster and smaller than PyInstaller, with native performance.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
PROJECT_ROOT = Path(__file__).parent


def main():
    """Build Aemeath using Nuitka with optimal settings."""
    
    # Clean previous builds
    dist_dir = PROJECT_ROOT / "dist"
    build_dir = PROJECT_ROOT / "build"
    
    if dist_dir.exists():
        print(f"🧹 Cleaning {dist_dir}")
        shutil.rmtree(dist_dir)
    if build_dir.exists():
        print(f"🧹 Cleaning {build_dir}")
        shutil.rmtree(build_dir)
    
    # Base Nuitka command
    nuitka_cmd = [
        sys.executable, "-m", "nuitka",
        
        # Input - use package directory for __main__.py
        "--main=src/aemeath",
        
        # Output settings
        "--standalone",                    # Bundle everything
        "--onefile",                       # Single executable (optional, can remove for faster build)
        "--output-dir=dist",
        "--output-filename=aemeath",
        
        # Optimization
        "--lto=yes",                       # Link-Time Optimization for better performance
        "--assume-yes-for-downloads",      # Auto-download dependencies
        
        # UI settings - only for GUI applications
        "--enable-plugin=pyside6",         # PySide6 support
        
        # Include data files - use include-data-dir for directories
        "--include-data-dir=assets/gifs=assets/gifs",
        "--include-data-files=assets/icons/aemeath.ico=assets/icons/aemeath.ico",
        
        # Module inclusion
        "--include-package=aemeath",
        "--include-module=aemeath.app",
        "--include-module=aemeath.config",
        "--include-module=aemeath.cursor",
        "--include-module=aemeath.pet",
        "--include-module=aemeath.sprite",
        
        # PySide6 module optimization - only include what we need
        "--nofollow-import-to=PySide6.Qt3DAnimation",
        "--nofollow-import-to=PySide6.Qt3DCore",
        "--nofollow-import-to=PySide6.Qt3DExtras",
        "--nofollow-import-to=PySide6.Qt3DInput",
        "--nofollow-import-to=PySide6.Qt3DLogic",
        "--nofollow-import-to=PySide6.Qt3DRender",
        "--nofollow-import-to=PySide6.QtBluetooth",
        "--nofollow-import-to=PySide6.QtCharts",
        "--nofollow-import-to=PySide6.QtDataVisualization",
        "--nofollow-import-to=PySide6.QtMultimedia",
        "--nofollow-import-to=PySide6.QtMultimediaWidgets",
        "--nofollow-import-to=PySide6.QtNetwork",
        "--nofollow-import-to=PySide6.QtOpenGL",
        "--nofollow-import-to=PySide6.QtOpenGLWidgets",
        "--nofollow-import-to=PySide6.QtPositioning",
        "--nofollow-import-to=PySide6.QtPrintSupport",
        "--nofollow-import-to=PySide6.QtQml",
        "--nofollow-import-to=PySide6.QtQuick",
        "--nofollow-import-to=PySide6.QtQuickWidgets",
        "--nofollow-import-to=PySide6.QtSql",
        "--nofollow-import-to=PySide6.QtSvg",
        "--nofollow-import-to=PySide6.QtSvgWidgets",
        "--nofollow-import-to=PySide6.QtTest",
        "--nofollow-import-to=PySide6.QtWebEngine",
        "--nofollow-import-to=PySide6.QtWebEngineCore",
        "--nofollow-import-to=PySide6.QtWebEngineWidgets",
        "--nofollow-import-to=PySide6.QtXml",
        
        # Exclude unnecessary stdlib modules
        "--nofollow-import-to=tkinter",
        "--nofollow-import-to=unittest",
        "--nofollow-import-to=email",
        "--nofollow-import-to=http",
        "--nofollow-import-to=xmlrpc",
        "--nofollow-import-to=multiprocessing",
        "--nofollow-import-to=asyncio",
    ]
    
    # Platform-specific settings
    if IS_WINDOWS:
        nuitka_cmd.extend([
            "--nofollow-import-to=PySide6.QtDBus",  # Not available on Windows
            "--windows-console-mode=disable",       # No console window for GUI
            "--windows-icon-from-ico=assets/icons/aemeath.ico",
        ])
    else:
        # Linux icon support
        nuitka_cmd.append("--linux-icon=assets/icons/aemeath.ico")
    
    print("🚀 Building Aemeath with Nuitka...")
    print(f"📍 Platform: {'Windows' if IS_WINDOWS else 'Linux'}")
    print(f"📦 Output: dist/aemeath{'..exe' if IS_WINDOWS else ''}")
    print()
    
    try:
        subprocess.run(nuitka_cmd, check=True, cwd=PROJECT_ROOT)
        print()
        print("✅ Build completed successfully!")
        print(f"📦 Executable: dist/aemeath{'..exe' if IS_WINDOWS else ''}")
    except subprocess.CalledProcessError as e:
        print(f"❌ Build failed with exit code {e.returncode}")
        sys.exit(1)
    except FileNotFoundError:
        print("❌ Nuitka not found. Please install it first:")
        print(f"   uv pip install nuitka")
        sys.exit(1)


if __name__ == "__main__":
    main()
