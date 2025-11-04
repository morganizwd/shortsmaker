"""
Конвертации между форматом времени 00:00:00.000 и секундами/кадрами.
"""

import re
from typing import Optional


def timecode_to_seconds(timecode: str) -> float:
    """
    Конвертирует время из формата 00:00:00.000 в секунды.
    
    Args:
        timecode: Строка времени в формате HH:MM:SS.mmm или MM:SS.mmm или SS.mmm
    
    Returns:
        Количество секунд (float)
    
    Examples:
        >>> timecode_to_seconds("00:01:30.500")
        90.5
        >>> timecode_to_seconds("01:30.500")
        90.5
        >>> timecode_to_seconds("90.500")
        90.5
    """
    if not timecode or not timecode.strip():
        return 0.0
    
    # Удаление пробелов
    timecode = timecode.strip()
    
    # Разделение на части
    parts = timecode.split(":")
    
    total_seconds = 0.0
    
    if len(parts) == 3:
        # Формат HH:MM:SS.mmm
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds_part = parts[2]
        total_seconds = hours * 3600 + minutes * 60
    elif len(parts) == 2:
        # Формат MM:SS.mmm
        minutes = int(parts[0])
        seconds_part = parts[1]
        total_seconds = minutes * 60
    elif len(parts) == 1:
        # Формат SS.mmm или просто секунды
        seconds_part = parts[0]
    else:
        raise ValueError(f"Неверный формат времени: {timecode}")
    
    # Парсинг секунд и миллисекунд
    seconds_with_ms = float(seconds_part)
    total_seconds += seconds_with_ms
    
    return total_seconds


def seconds_to_timecode(seconds: float, include_hours: bool = True) -> str:
    """
    Конвертирует секунды в формат времени 00:00:00.000.
    
    Args:
        seconds: Количество секунд (float)
        include_hours: Включать ли часы в вывод (если False, формат MM:SS.mmm)
    
    Returns:
        Строка времени в формате HH:MM:SS.mmm или MM:SS.mmm
    
    Examples:
        >>> seconds_to_timecode(90.5)
        "00:01:30.500"
        >>> seconds_to_timecode(90.5, include_hours=False)
        "01:30.500"
    """
    if seconds < 0:
        seconds = 0.0
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    
    milliseconds = int((secs - int(secs)) * 1000)
    secs_int = int(secs)
    
    if include_hours or hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs_int:02d}.{milliseconds:03d}"
    else:
        return f"{minutes:02d}:{secs_int:02d}.{milliseconds:03d}"


def seconds_to_frames(seconds: float, fps: float) -> int:
    """
    Конвертирует секунды в количество кадров.
    
    Args:
        seconds: Количество секунд
        fps: Кадров в секунду
    
    Returns:
        Количество кадров (int)
    """
    return int(seconds * fps)


def frames_to_seconds(frames: int, fps: float) -> float:
    """
    Конвертирует количество кадров в секунды.
    
    Args:
        frames: Количество кадров
        fps: Кадров в секунду
    
    Returns:
        Количество секунд (float)
    """
    return frames / fps


def frames_to_timecode(frames: int, fps: float, include_hours: bool = True) -> str:
    """
    Конвертирует количество кадров в формат времени.
    
    Args:
        frames: Количество кадров
        fps: Кадров в секунду
        include_hours: Включать ли часы в вывод
    
    Returns:
        Строка времени в формате HH:MM:SS.mmm или MM:SS.mmm
    """
    seconds = frames_to_seconds(frames, fps)
    return seconds_to_timecode(seconds, include_hours)


def timecode_to_frames(timecode: str, fps: float) -> int:
    """
    Конвертирует время из формата 00:00:00.000 в количество кадров.
    
    Args:
        timecode: Строка времени в формате HH:MM:SS.mmm или MM:SS.mmm
        fps: Кадров в секунду
    
    Returns:
        Количество кадров (int)
    """
    seconds = timecode_to_seconds(timecode)
    return seconds_to_frames(seconds, fps)

