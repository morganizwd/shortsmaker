"""
Поиск ffmpeg/ffprobe рядом с exe или в PATH.
"""

import os
import sys
from pathlib import Path
from shutil import which
from app.config import FFMPEG_EXE, FFPROBE_EXE
from app.utils.logger import get_logger

logger = get_logger(__name__)


def find_ffmpeg() -> Path:
    """
    Ищет ffmpeg.exe в следующем порядке:
    1. В директории ffmpeg/ рядом с приложением
    2. В PATH
    3. Рядом с исполняемым файлом (для pyinstaller)
    
    Returns:
        Path к ffmpeg.exe
        
    Raises:
        FileNotFoundError: если ffmpeg не найден
    """
    # 1. Проверка в локальной директории ffmpeg/
    if FFMPEG_EXE.exists():
        logger.info(f"Найден ffmpeg в локальной директории: {FFMPEG_EXE}")
        return FFMPEG_EXE
    
    # 2. Проверка рядом с exe (для pyinstaller)
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).parent
        local_ffmpeg = exe_dir / "ffmpeg.exe"
        if local_ffmpeg.exists():
            logger.info(f"Найден ffmpeg рядом с exe: {local_ffmpeg}")
            return local_ffmpeg
    
    # 3. Поиск в PATH
    ffmpeg_path = which("ffmpeg")
    if ffmpeg_path:
        logger.info(f"Найден ffmpeg в PATH: {ffmpeg_path}")
        return Path(ffmpeg_path)
    
    # Если не найден
    error_msg = "ffmpeg не найден. Установите ffmpeg или поместите ffmpeg.exe в директорию ffmpeg/"
    logger.error(error_msg)
    raise FileNotFoundError(error_msg)


def find_ffprobe() -> Path:
    """
    Ищет ffprobe.exe в следующем порядке:
    1. В директории ffmpeg/ рядом с приложением
    2. В PATH
    3. Рядом с исполняемым файлом (для pyinstaller)
    
    Returns:
        Path к ffprobe.exe
        
    Raises:
        FileNotFoundError: если ffprobe не найден
    """
    # 1. Проверка в локальной директории ffmpeg/
    if FFPROBE_EXE.exists():
        logger.info(f"Найден ffprobe в локальной директории: {FFPROBE_EXE}")
        return FFPROBE_EXE
    
    # 2. Проверка рядом с exe (для pyinstaller)
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).parent
        local_ffprobe = exe_dir / "ffprobe.exe"
        if local_ffprobe.exists():
            logger.info(f"Найден ffprobe рядом с exe: {local_ffprobe}")
            return local_ffprobe
    
    # 3. Поиск в PATH
    ffprobe_path = which("ffprobe")
    if ffprobe_path:
        logger.info(f"Найден ffprobe в PATH: {ffprobe_path}")
        return Path(ffprobe_path)
    
    # Если не найден
    error_msg = "ffprobe не найден. Установите ffmpeg или поместите ffprobe.exe в директорию ffmpeg/"
    logger.error(error_msg)
    raise FileNotFoundError(error_msg)

