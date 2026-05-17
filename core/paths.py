"""Application paths and default values."""

import sys
from dataclasses import dataclass
from pathlib import Path


IS_FROZEN = getattr(sys, "frozen", False)
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
TOOL_DIR = Path(sys.executable).resolve().parent if IS_FROZEN else Path(__file__).resolve().parents[1]


def first_existing_path(*paths):
    for path in paths:
        if path.exists():
            return path
    return paths[0]


def find_workspace_root():
    if not IS_FROZEN:
        return TOOL_DIR.parent

    candidates = [
        Path.cwd(),
        TOOL_DIR,
        TOOL_DIR.parent,
        TOOL_DIR.parent.parent,
    ]
    for candidate in candidates:
        if (candidate / "YoloV8-TensorRT-Jetson_Nano").exists():
            return candidate
    return TOOL_DIR


APP_DIR = find_workspace_root()
SCRIPT_DIR = first_existing_path(
    TOOL_DIR / "scripts",
    BUNDLE_DIR / "scripts",
    APP_DIR / "jetson_tool_panel" / "scripts",
)
CONFIG_PATH = TOOL_DIR / "settings.ini"

WINDOWS_PROXY_SCRIPT = first_existing_path(
    SCRIPT_DIR / "windows-clash-lan-temp.ps1",
    BUNDLE_DIR / "scripts" / "windows-clash-lan-temp.ps1",
    APP_DIR / "windows-clash-lan-temp.ps1",
)
JETSON_PROXY_SCRIPT = first_existing_path(
    SCRIPT_DIR / "jetson-proxy-session.sh",
    BUNDLE_DIR / "scripts" / "jetson-proxy-session.sh",
    APP_DIR / "jetson-proxy-session.sh",
)
PROJECT_DIR = first_existing_path(
    APP_DIR / "YoloV8-TensorRT-Jetson_Nano",
    TOOL_DIR / "YoloV8-TensorRT-Jetson_Nano",
)
SYNC_SCRIPT = PROJECT_DIR / "sync-to-jetson.py"


@dataclass(frozen=True)
class AppDefaults:
    proxy_port: int = 7897
    remote: str = "jetson@192.168.55.1"
    remote_path: str = "/home/jetson/YoloV8-TensorRT-Jetson_Nano"
    clash_program: str = r"C:\Program Files\Clash Verge\verge-mihomo.exe"


@dataclass(frozen=True)
class AppPaths:
    app_dir: Path = APP_DIR
    bundle_dir: Path = BUNDLE_DIR
    tool_dir: Path = TOOL_DIR
    script_dir: Path = SCRIPT_DIR
    config_path: Path = CONFIG_PATH
    windows_proxy_script: Path = WINDOWS_PROXY_SCRIPT
    jetson_proxy_script: Path = JETSON_PROXY_SCRIPT
    project_dir: Path = PROJECT_DIR
    sync_script: Path = SYNC_SCRIPT


DEFAULTS = AppDefaults()
PATHS = AppPaths()
