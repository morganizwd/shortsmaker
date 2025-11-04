"""
Воспроизведение видео через VLC (предпросмотр).
"""

import vlc
from pathlib import Path
from typing import Optional
from app.utils.logger import get_logger

logger = get_logger(__name__)


class VLCPlayer:
    """Класс для воспроизведения видео через VLC."""
    
    def __init__(self):
        self.instance: Optional[vlc.Instance] = None
        self.player: Optional[vlc.MediaPlayer] = None
        self.current_file: Optional[Path] = None
        self.start_time: float = 0.0
        self.end_time: float = 0.0
        
        try:
            self.instance = vlc.Instance()
            self.player = self.instance.media_player_new()
            logger.info("VLC плеер инициализирован")
        except Exception as e:
            logger.error(f"Ошибка инициализации VLC: {e}")
    
    def play_file(self, file_path: Path, start_time: float = 0.0, end_time: float = 0.0):
        """
        Воспроизводит файл с указанным временным диапазоном.
        
        Args:
            file_path: Путь к видео файлу
            start_time: Время начала в секундах
            end_time: Время окончания в секундах (0 = до конца)
        """
        if not self.player:
            logger.error("VLC плеер не инициализирован")
            return False
        
        if not file_path.exists():
            logger.error(f"Файл не найден: {file_path}")
            return False
        
        try:
            self.current_file = file_path
            self.start_time = start_time
            self.end_time = end_time
            
            media = self.instance.media_new(str(file_path))
            self.player.set_media(media)
            
            # Установка времени начала
            if start_time > 0:
                self.player.set_time(int(start_time * 1000))
            
            # Воспроизведение
            self.player.play()
            
            # Если указано время окончания, запускаем таймер для остановки
            if end_time > 0:
                self._setup_end_time_handler(end_time)
            
            logger.info(f"Воспроизведение: {file_path} ({start_time}s - {end_time}s)")
            return True
        
        except Exception as e:
            logger.error(f"Ошибка воспроизведения: {e}")
            return False
    
    def _setup_end_time_handler(self, end_time: float):
        """Настраивает обработчик для остановки в указанное время."""
        # Это упрощенная версия - в реальности нужно использовать таймер
        # для проверки текущего времени и остановки при достижении end_time
        pass
    
    def stop(self):
        """Останавливает воспроизведение."""
        if self.player:
            self.player.stop()
            logger.info("Воспроизведение остановлено")
    
    def pause(self):
        """Приостанавливает воспроизведение."""
        if self.player:
            self.player.pause()
    
    def resume(self):
        """Возобновляет воспроизведение."""
        if self.player:
            self.player.play()
    
    def get_time(self) -> float:
        """Получает текущее время воспроизведения в секундах."""
        if self.player:
            return self.player.get_time() / 1000.0
        return 0.0
    
    def set_time(self, time: float):
        """Устанавливает время воспроизведения в секундах."""
        if self.player:
            self.player.set_time(int(time * 1000))
    
    def is_playing(self) -> bool:
        """Проверяет, воспроизводится ли видео."""
        if self.player:
            return self.player.is_playing() == 1
        return False
    
    def get_position(self) -> float:
        """Получает позицию воспроизведения (0.0 - 1.0)."""
        if self.player:
            return self.player.get_position()
        return 0.0
    
    def set_position(self, position: float):
        """Устанавливает позицию воспроизведения (0.0 - 1.0)."""
        if self.player:
            self.player.set_position(position)
    
    def get_length(self) -> float:
        """Получает длительность в секундах."""
        if self.player:
            return self.player.get_length() / 1000.0
        return 0.0
    
    def release(self):
        """Освобождает ресурсы."""
        if self.player:
            self.player.stop()
            self.player.release()
        if self.instance:
            self.instance.release()

