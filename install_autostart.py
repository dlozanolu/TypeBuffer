"""
Instala / desinstala TypeBuffer al iniciar sesión del usuario.

No es un servicio de Windows (Session 0): esos no ven el teclado del escritorio.
Equivalente correcto:
  - Windows: carpeta Inicio (Startup)
  - Linux:   ~/.config/autostart/*.desktop
  - macOS:   ~/Library/LaunchAgents/*.plist
"""

from __future__ import annotations

import argparse
import os
import platform
import sys
from pathlib import Path


APP_NAME = "TypeBuffer"
ROOT = Path(__file__).resolve().parent


def resolve_target() -> Path:
    """Prefiere el binario compilado; si no, el script .py."""
    system = platform.system()
    if system == "Windows":
        exe = ROOT / "dist" / f"{APP_NAME}.exe"
        if exe.exists():
            return exe
    else:
        bin_path = ROOT / "dist" / APP_NAME
        if bin_path.exists():
            return bin_path
    return ROOT / "TypeBuffer.py"


def run_command(target: Path) -> list[str]:
    if target.suffix.lower() == ".py":
        py = sys.executable
        return [py, str(target), "--quiet"]
    return [str(target), "--quiet"]


def windows_startup_dir() -> Path:
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def install_windows(target: Path) -> Path:
    startup = windows_startup_dir()
    startup.mkdir(parents=True, exist_ok=True)
    bat = startup / f"{APP_NAME}.bat"
    cmd = run_command(target)
    # start sin ventana de consola molesta si es .exe; el .bat queda mínimo
    if target.suffix.lower() == ".exe":
        bat.write_text(
            f'@echo off\r\nstart "" "{target}" --quiet\r\n',
            encoding="utf-8",
        )
    else:
        quoted = " ".join(f'"{c}"' if " " in c else c for c in cmd)
        bat.write_text(
            f'@echo off\r\nstart "" {quoted}\r\n',
            encoding="utf-8",
        )
    return bat


def uninstall_windows() -> Path | None:
    bat = windows_startup_dir() / f"{APP_NAME}.bat"
    if bat.exists():
        bat.unlink()
        return bat
    return None


def install_linux(target: Path) -> Path:
    autostart = Path.home() / ".config" / "autostart"
    autostart.mkdir(parents=True, exist_ok=True)
    desktop = autostart / f"{APP_NAME}.desktop"
    cmd = " ".join(run_command(target))
    desktop.write_text(
        "\n".join(
            [
                "[Desktop Entry]",
                "Type=Application",
                f"Name={APP_NAME}",
                f"Exec={cmd}",
                "X-GNOME-Autostart-enabled=true",
                "Terminal=false",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return desktop


def uninstall_linux() -> Path | None:
    desktop = Path.home() / ".config" / "autostart" / f"{APP_NAME}.desktop"
    if desktop.exists():
        desktop.unlink()
        return desktop
    return None


def install_macos(target: Path) -> Path:
    agents = Path.home() / "Library" / "LaunchAgents"
    agents.mkdir(parents=True, exist_ok=True)
    plist = agents / f"com.local.{APP_NAME}.plist"
    args = run_command(target)
    args_xml = "\n".join(f"        <string>{a}</string>" for a in args)
    plist.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.local.{APP_NAME}</string>
    <key>ProgramArguments</key>
    <array>
{args_xml}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
""",
        encoding="utf-8",
    )
    return plist


def uninstall_macos() -> Path | None:
    plist = Path.home() / "Library" / "LaunchAgents" / f"com.local.{APP_NAME}.plist"
    if plist.exists():
        plist.unlink()
        return plist
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=f"Autostart de {APP_NAME} (multiplataforma)")
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--install", action="store_true", help="Instalar arranque al login")
    g.add_argument("--uninstall", action="store_true", help="Quitar arranque al login")
    args = parser.parse_args()

    system = platform.system()
    target = resolve_target()

    if args.install:
        if not target.exists():
            print(f"No encontrado: {target}")
            return 1
        if system == "Windows":
            path = install_windows(target)
        elif system == "Linux":
            path = install_linux(target)
        elif system == "Darwin":
            path = install_macos(target)
        else:
            print(f"Sistema no soportado: {system}")
            return 1
        print(f"Instalado autostart -> {path}")
        print(f"Objetivo: {target}")
        print("Reinicia sesion (o ejecuta el acceso) para probarlo.")
        return 0

    if system == "Windows":
        path = uninstall_windows()
    elif system == "Linux":
        path = uninstall_linux()
    elif system == "Darwin":
        path = uninstall_macos()
    else:
        print(f"Sistema no soportado: {system}")
        return 1

    print(f"Eliminado: {path}" if path else "No habia nada instalado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
