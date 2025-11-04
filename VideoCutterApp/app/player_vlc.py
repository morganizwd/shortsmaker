"""
Воспроизведение видео через VLC (предпросмотр).
"""

import sys
import vlc
from pathlib import Path
from typing import Optional
from PySide6.QtCore import QTimer
from app.utils.logger import get_logger

logger = get_logger(__name__)


class VLCPlayer:
    """Класс для воспроизведения видео через VLC."""
    
    def __init__(self, video_widget=None):
        """
        Инициализация VLC плеера.
        
        Args:
            video_widget: Qt виджет для встраивания видео (опционально)
        """
        self.instance: Optional[vlc.Instance] = None
        self.player: Optional[vlc.MediaPlayer] = None
        self.current_file: Optional[Path] = None
        self.start_time: float = 0.0
        self.end_time: float = 0.0
        self.video_widget = video_widget
        self.end_timer = QTimer()
        self.end_timer.timeout.connect(self._check_end_time)
        
        try:
            self.instance = vlc.Instance()
            self.player = self.instance.media_player_new()
            
            # Если передан виджет, встраиваем видео в него
            if video_widget is not None:
                self.set_video_widget(video_widget)
            
            logger.info("VLC плеер инициализирован")
        except Exception as e:
            logger.error(f"Ошибка инициализации VLC: {e}")
    
    def set_video_widget(self, widget):
        """
        Устанавливает виджет для встраивания видео.
        
        Args:
            widget: Qt виджет для отображения видео
        """
        self.video_widget = widget
        if not self.player:
            return
        
        # Убеждаемся, что виджет виден перед получением winId
        if widget is not None:
            widget.show()
        
        try:
            # Определяем платформу и используем соответствующий метод
            if sys.platform == "win32":
                # Windows
                if hasattr(widget, 'winId'):
                    # На Windows нужно дождаться, пока виджет будет отображен
                    widget_id = int(widget.winId())
                    if widget_id:
                        self.player.set_hwnd(widget_id)
                    else:
                        logger.warning("Не удалось получить winId виджета")
                else:
                    logger.warning("Виджет не поддерживает winId()")
            elif sys.platform == "darwin":
                # macOS
                if hasattr(widget, 'winId'):
                    widget_id = int(widget.winId())
                    if widget_id:
                        self.player.set_nsobject(widget_id)
                    else:
                        logger.warning("Не удалось получить winId виджета")
                else:
                    logger.warning("Виджет не поддерживает winId()")
            else:
                # Linux и другие Unix-подобные системы
                if hasattr(widget, 'winId'):
                    widget_id = int(widget.winId())
                    if widget_id:
                        self.player.set_xwindow(widget_id)
                    else:
                        logger.warning("Не удалось получить winId виджета")
                else:
                    logger.warning("Виджет не поддерживает winId()")
            
            logger.info("Виджет для видео установлен")
        except Exception as e:
            logger.error(f"Ошибка установки виджета: {e}")
    
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
            
            # Убеждаемся, что виджет установлен (если он был передан)
            if self.video_widget is not None:
                self.set_video_widget(self.video_widget)
            
            # Установка времени начала
            if start_time > 0:
                self.player.set_time(int(start_time * 1000))
            
            # Воспроизведение
            self.player.play()
            
            # Если указано время окончания и оно больше 0, запускаем таймер для остановки
            # Если end_time = 0, значит воспроизводим до конца
            if end_time > 0 and end_time > start_time:
                self._setup_end_time_handler(end_time)
            
            logger.info(f"Воспроизведение: {file_path} ({start_time}s - {end_time}s)")
            return True
        
        except Exception as e:
            logger.error(f"Ошибка воспроизведения: {e}")
            return False
    
    def _setup_end_time_handler(self, end_time: float):
        """Настраивает обработчик для остановки в указанное время."""
        self.end_time = end_time
        # Запускаем таймер, который будет проверять текущее время каждые 100мс
        self.end_timer.start(100)  # Проверка каждые 100 миллисекунд
    
    def _check_end_time(self):
        """Проверяет текущее время и останавливает воспроизведение при достижении end_time."""
        if not self.player or not self.player.is_playing():
            self.end_timer.stop()
            return
        
        current_time = self.get_time()
        if current_time >= self.end_time:
            self.stop()
            self.end_timer.stop()
            logger.info(f"Воспроизведение остановлено в {self.end_time}s")
    
    def stop(self):
        """Останавливает воспроизведение."""
        self.end_timer.stop()
        if self.player:
            self.player.stop()
            logger.info("Воспроизведение остановлено")
    
    def pause(self):
        """Приостанавливает воспроизведение."""
        if self.player:
            self.player.pause()
    
    def play(self):
        """Начинает воспроизведение."""
        if self.player:
            self.player.play()
    
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
    
    def set_rate(self, rate: float):
        """
        Устанавливает скорость воспроизведения.
        
        Args:
            rate: Скорость воспроизведения (0.5 = 0.5x, 1.0 = нормальная, 2.0 = 2x)
        """
        if self.player:
            # Ограничиваем диапазон от 0.5 до 3.0
            rate = max(0.5, min(3.0, rate))
            self.player.set_rate(rate)
            logger.info(f"Скорость воспроизведения установлена: {rate}x")
    
    def get_rate(self) -> float:
        """Получает текущую скорость воспроизведения."""
        if self.player:
            return self.player.get_rate()
        return 1.0
    
    def release(self):
        """Освобождает ресурсы."""
        if self.player:
            self.player.stop()
            self.player.release()
        if self.instance:
            self.instance.release()

