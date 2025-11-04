"""
Получение метаданных видео: длительность, fps, треки.
"""

import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional
from app.utils.paths import find_ffprobe
from app.utils.logger import get_logger

logger = get_logger(__name__)


def get_video_info(video_path: Path) -> Optional[Dict]:
    """
    Получает информацию о видео файле.
    
    Returns:
        Dict с ключами: duration, fps, width, height, codec, bitrate, audio_tracks
    """
    ffprobe_path = find_ffprobe()
    
    cmd = [
        str(ffprobe_path),
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(video_path)
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        data = json.loads(result.stdout)
        
        # Поиск видео потока
        video_stream = None
        audio_streams = []
        
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video" and video_stream is None:
                video_stream = stream
            elif stream.get("codec_type") == "audio":
                audio_streams.append(stream)
        
        if not video_stream:
            logger.error("Видео поток не найден")
            return None
        
        # Извлечение информации
        duration = float(data.get("format", {}).get("duration", 0))
        fps_str = video_stream.get("r_frame_rate", "0/1")
        
        # Парсинг fps (формат: "30/1")
        fps = 0
        if "/" in fps_str:
            num, den = map(float, fps_str.split("/"))
            fps = num / den if den != 0 else 0
        
        width = int(video_stream.get("width", 0))
        height = int(video_stream.get("height", 0))
        codec = video_stream.get("codec_name", "unknown")
        bitrate = int(data.get("format", {}).get("bit_rate", 0))
        
        # Информация об аудио треках
        audio_info = []
        for audio_stream in audio_streams:
            audio_info.append({
                "index": audio_stream.get("index"),
                "codec": audio_stream.get("codec_name", "unknown"),
                "bitrate": int(audio_stream.get("bit_rate", 0)),
                "channels": int(audio_stream.get("channels", 0)),
                "sample_rate": int(audio_stream.get("sample_rate", 0)),
                "language": audio_stream.get("tags", {}).get("language", "unknown"),
            })
        
        return {
            "duration": duration,
            "fps": fps,
            "width": width,
            "height": height,
            "codec": codec,
            "bitrate": bitrate,
            "audio_tracks": audio_info,
            "format": data.get("format", {}).get("format_name", "unknown"),
        }
    
    except subprocess.CalledProcessError as e:
        logger.error(f"Ошибка выполнения ffprobe: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка парсинга JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
        return None


def get_video_duration(video_path: Path) -> float:
    """Получает длительность видео в секундах."""
    info = get_video_info(video_path)
    return info.get("duration", 0.0) if info else 0.0


def get_video_fps(video_path: Path) -> float:
    """Получает FPS видео."""
    info = get_video_info(video_path)
    return info.get("fps", 0.0) if info else 0.0


def get_audio_tracks(video_path: Path) -> List[Dict]:
    """Получает список аудио треков."""
    info = get_video_info(video_path)
    return info.get("audio_tracks", []) if info else []

