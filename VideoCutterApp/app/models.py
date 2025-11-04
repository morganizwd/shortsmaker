"""
DTO (Data Transfer Objects): Job, FilterChain, Overlay, SubtitleSpec
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple


@dataclass
class FilterChain:
    """Цепочка видео фильтров."""
    filters: List[str] = field(default_factory=list)
    
    def add_filter(self, filter_str: str):
        """Добавляет фильтр в цепочку."""
        self.filters.append(filter_str)
    
    def clear(self):
        """Очищает цепочку фильтров."""
        self.filters.clear()
    
    def to_ffmpeg_string(self) -> str:
        """Преобразует в строку для ffmpeg."""
        return ",".join(self.filters) if self.filters else ""


@dataclass
class Overlay:
    """Параметры наложения (текст, изображение и т.д.)."""
    type: str = "text"  # text, image, video
    content: str = ""  # текст или путь к файлу
    x: int = 0
    y: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    opacity: float = 1.0
    font_size: int = 24
    font_color: str = "white"
    
    def to_ffmpeg_filter(self) -> str:
        """Преобразует в ffmpeg фильтр."""
        if self.type == "text":
            return (
                f"drawtext=text='{self.content}':"
                f"x={self.x}:y={self.y}:"
                f"fontsize={self.font_size}:"
                f"fontcolor={self.font_color}"
            )
        elif self.type == "image":
            return (
                f"overlay={self.x}:{self.y}:"
                f"enable='between(t,{self.start_time},{self.end_time})'"
            )
        return ""


@dataclass
class SubtitleSpec:
    """Параметры субтитров."""
    file_path: Optional[Path] = None
    track_index: int = 0
    encoding: str = "utf-8"
    offset: float = 0.0  # смещение времени в секундах
    
    def to_ffmpeg_args(self) -> List[str]:
        """Преобразует в аргументы ffmpeg."""
        if not self.file_path or not self.file_path.exists():
            return []
        
        return [
            "-vf", f"subtitles='{self.file_path}':encoding={self.encoding}"
        ]


@dataclass
class Job:
    """Задача на обработку видео."""
    input_file: Path
    output_file: Path
    start_time: float = 0.0
    end_time: float = 0.0
    speed: float = 1.0  # Скорость воспроизведения (0.5-3.0)
    filter_chain: FilterChain = field(default_factory=FilterChain)
    overlays: List[Overlay] = field(default_factory=list)
    subtitle_spec: Optional[SubtitleSpec] = None
    encoding_profile: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending, running, completed, failed, cancelled
    progress: float = 0.0
    error_message: Optional[str] = None
    
    def add_overlay(self, overlay: Overlay):
        """Добавляет наложение."""
        self.overlays.append(overlay)
    
    def get_all_filters(self) -> List[str]:
        """Получает все фильтры для ffmpeg."""
        filters = self.filter_chain.filters.copy()
        
        # Добавление фильтров наложений
        for overlay in self.overlays:
            overlay_filter = overlay.to_ffmpeg_filter()
            if overlay_filter:
                filters.append(overlay_filter)
        
        return filters
    
    def validate(self) -> Tuple[bool, Optional[str]]:
        """Проверяет валидность задачи."""
        if not self.input_file.exists():
            return False, f"Входной файл не найден: {self.input_file}"
        
        if self.start_time < 0:
            return False, "Время начала не может быть отрицательным"
        
        if self.end_time <= self.start_time:
            return False, "Время окончания должно быть больше времени начала"
        
        if not self.output_file.parent.exists():
            return False, f"Директория для выходного файла не существует: {self.output_file.parent}"
        
        return True, None

