"""
Конфигурация приложения: пути, настройки, профили кодирования.
"""

import os
from pathlib import Path
from typing import Dict, List


# Пути к директориям
BASE_DIR = Path(__file__).parent.parent
APP_DIR = BASE_DIR / "app"
RESOURCES_DIR = APP_DIR / "resources"
BUILD_DIR = BASE_DIR / "build"
FFMPEG_DIR = BASE_DIR / "ffmpeg"

# Пути к исполняемым файлам
FFMPEG_EXE = FFMPEG_DIR / "ffmpeg.exe"
FFPROBE_EXE = FFMPEG_DIR / "ffprobe.exe"

# Пути к ресурсам
ICON_PATH = RESOURCES_DIR / "app.ico"

# Настройки по умолчанию
DEFAULT_OUTPUT_DIR = Path.home() / "Videos" / "VideoCutter"
DEFAULT_OUTPUT_EXTENSION = ".mp4"

# Профили кодирования
ENCODING_PROFILES: Dict[str, Dict[str, any]] = {
    "fast": {
        "preset": "ultrafast",
        "crf": 23,
        "codec": "libx264",
        "audio_codec": "aac",
        "audio_bitrate": "128k",
    },
    "balanced": {
        "preset": "medium",
        "crf": 20,
        "codec": "libx264",
        "audio_codec": "aac",
        "audio_bitrate": "192k",
    },
    "high_quality": {
        "preset": "slow",
        "crf": 18,
        "codec": "libx264",
        "audio_codec": "aac",
        "audio_bitrate": "256k",
    },
}

# Настройки UI
DEFAULT_WINDOW_WIDTH = 1200
DEFAULT_WINDOW_HEIGHT = 800
MIN_WINDOW_WIDTH = 800
MIN_WINDOW_HEIGHT = 600

# Настройки логирования
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "app.log"
LOG_LEVEL = "INFO"

# Настройки VLC плеера
VLC_TIMEOUT = 5000  # мс
VLC_PREVIEW_FPS = 30

# Настройки обновления прогресса
PROGRESS_UPDATE_INTERVAL = 100  # мс

