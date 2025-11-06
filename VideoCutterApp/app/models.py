"""
DTO (Data Transfer Objects): Job, FilterChain, Overlay, SubtitleSpec, Segment, Project
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
import json


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
    aspect_ratio: str = "16:9"  # Соотношение сторон: "16:9" или "9:16"
    # Настройки цветокоррекции
    brightness: float = 0.0  # Яркость: -1.0 до 1.0
    contrast: float = 1.0  # Контрастность: 0.0 до 2.0
    saturation: float = 1.0  # Насыщенность: 0.0 до 2.0
    sharpness: float = 0.0  # Резкость: -1.0 до 1.0
    shadows: float = 0.0  # Тени: -1.0 до 1.0
    temperature: float = 0.0  # Температура (цвет): -100 до 100
    tint: float = 0.0  # Тон (оттенок): -100 до 100
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


@dataclass
class Segment:
    """Сегмент видео для многосегментного режима."""
    start_time: float = 0.0
    end_time: float = 0.0
    name: str = ""  # Имя/метка сегмента
    enabled: bool = True  # Включен ли сегмент для экспорта
    encoding_profile: str = "balanced"  # Профиль экспорта
    # Настройки обработки (как в Job, но для каждого сегмента)
    speed: float = 1.0
    aspect_ratio: str = "16:9"
    brightness: float = 0.0
    contrast: float = 1.0
    saturation: float = 1.0
    sharpness: float = 0.0
    shadows: float = 0.0
    temperature: float = 0.0
    tint: float = 0.0
    
    @property
    def duration(self) -> float:
        """Возвращает длительность сегмента."""
        return max(0.0, self.end_time - self.start_time)
    
    def validate(self) -> Tuple[bool, Optional[str]]:
        """Проверяет валидность сегмента."""
        if self.start_time < 0:
            return False, "Время начала не может быть отрицательным"
        
        if self.end_time <= self.start_time:
            return False, "Время окончания должно быть больше времени начала"
        
        return True, None
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразует сегмент в словарь для JSON."""
        return {
            "start_time": self.start_time,
            "end_time": self.end_time,
            "name": self.name,
            "enabled": self.enabled,
            "encoding_profile": self.encoding_profile,
            "speed": self.speed,
            "aspect_ratio": self.aspect_ratio,
            "brightness": self.brightness,
            "contrast": self.contrast,
            "saturation": self.saturation,
            "sharpness": self.sharpness,
            "shadows": self.shadows,
            "temperature": self.temperature,
            "tint": self.tint
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Segment":
        """Создает сегмент из словаря."""
        return cls(
            start_time=data.get("start_time", 0.0),
            end_time=data.get("end_time", 0.0),
            name=data.get("name", ""),
            enabled=data.get("enabled", True),
            encoding_profile=data.get("encoding_profile", "balanced"),
            speed=data.get("speed", 1.0),
            aspect_ratio=data.get("aspect_ratio", "16:9"),
            brightness=data.get("brightness", 0.0),
            contrast=data.get("contrast", 1.0),
            saturation=data.get("saturation", 1.0),
            sharpness=data.get("sharpness", 0.0),
            shadows=data.get("shadows", 0.0),
            temperature=data.get("temperature", 0.0),
            tint=data.get("tint", 0.0)
        )


@dataclass
class Project:
    """Проект многосегментного режима."""
    input_file: Path
    output_dir: Path  # Директория для выходных файлов
    segments: List[Segment] = field(default_factory=list)
    export_mode: str = "split"  # "split" (отдельные файлы) или "concat" (склейка)
    export_method: str = "fast"  # "fast" (copy) или "accurate" (re-encode)
    project_name: str = "Untitled Project"
    
    def add_segment(self, segment: Segment) -> bool:
        """Добавляет сегмент в проект."""
        is_valid, error = segment.validate()
        if not is_valid:
            return False
        
        # Проверяем пересечения с существующими сегментами
        for existing in self.segments:
            if (segment.start_time < existing.end_time and segment.end_time > existing.start_time):
                # Есть пересечение, но это допустимо (можно обрабатывать)
                pass
        
        self.segments.append(segment)
        return True
    
    def remove_segment(self, index: int) -> bool:
        """Удаляет сегмент по индексу."""
        if 0 <= index < len(self.segments):
            del self.segments[index]
            return True
        return False
    
    def get_enabled_segments(self) -> List[Segment]:
        """Возвращает только включенные сегменты."""
        return [s for s in self.segments if s.enabled]
    
    def validate(self) -> Tuple[bool, Optional[str]]:
        """Проверяет валидность проекта."""
        if not self.input_file.exists():
            return False, f"Входной файл не найден: {self.input_file}"
        
        if not self.segments:
            return False, "Проект не содержит сегментов"
        
        for i, segment in enumerate(self.segments):
            is_valid, error = segment.validate()
            if not is_valid:
                return False, f"Сегмент {i + 1}: {error}"
        
        return True, None
    
    def save_to_file(self, file_path: Path) -> bool:
        """Сохраняет проект в JSON файл."""
        try:
            project_data = {
                "project_name": self.project_name,
                "input_file": str(self.input_file),
                "output_dir": str(self.output_dir),
                "export_mode": self.export_mode,
                "export_method": self.export_method,
                "segments": [segment.to_dict() for segment in self.segments]
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(project_data, f, indent=2, ensure_ascii=False)
            
            return True
        except Exception as e:
            return False
    
    @classmethod
    def load_from_file(cls, file_path: Path) -> Optional["Project"]:
        """Загружает проект из JSON файла."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                project_data = json.load(f)
            
            segments = [Segment.from_dict(s) for s in project_data.get("segments", [])]
            
            return cls(
                input_file=Path(project_data["input_file"]),
                output_dir=Path(project_data["output_dir"]),
                segments=segments,
                export_mode=project_data.get("export_mode", "split"),
                export_method=project_data.get("export_method", "fast"),
                project_name=project_data.get("project_name", "Untitled Project")
            )
        except Exception as e:
            return None

