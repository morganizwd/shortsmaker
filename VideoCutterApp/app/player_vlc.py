"""
Воспроизведение видео через VLC (предпросмотр).
"""

import sys
import vlc
import tempfile
import subprocess
from pathlib import Path
from typing import Optional
from PySide6.QtCore import QTimer, QThread, Signal
from app.utils.logger import get_logger
from app.ffmpeg_worker import FFmpegWorker

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
        self.aspect_ratio: Optional[str] = None
        self.video_width: int = 1920
        self.video_height: int = 1080
        
        # Параметры цветокоррекции для предпросмотра
        self.brightness: float = 0.0
        self.contrast: float = 1.0
        self.saturation: float = 1.0
        self.hue: float = 0.0  # Используется для тона (tint)
        self.gamma: float = 1.0  # Используется для теней (shadows)
        self.sharpness: float = 0.0
        self.temperature: float = 0.0
        self.tint: float = 0.0
        
        # Для предпросмотра с FFmpeg фильтрами
        self.use_ffmpeg_preview: bool = False  # Использовать FFmpeg для предпросмотра (по умолчанию выключено из-за медленности)
        self.preview_temp_file: Optional[Path] = None
        self.ffmpeg_worker = FFmpegWorker()
        self._preview_update_timer = QTimer()
        self._preview_update_timer.setSingleShot(True)
        self._preview_update_timer.timeout.connect(self._update_preview_debounced)
        self._pending_color_params = None  # Параметры для отложенного обновления
        
        try:
            # Создаем instance с опциями для поддержки фильтров
            # Включаем поддержку видео фильтров
            vlc_options = [
                '--intf', 'dummy',  # Отключаем интерфейс
                '--quiet',  # Тихий режим
            ]
            self.instance = vlc.Instance(vlc_options)
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
    
    def set_aspect_ratio(self, aspect_ratio: str, video_width: int = 1920, video_height: int = 1080):
        """
        Устанавливает соотношение сторон для предпросмотра.
        
        Args:
            aspect_ratio: Соотношение сторон ("16:9" или "9:16")
            video_width: Ширина исходного видео
            video_height: Высота исходного видео
        """
        self.aspect_ratio = aspect_ratio
        self.video_width = video_width
        self.video_height = video_height
        
        if not self.player:
            return
        
        try:
            # Вычисляем параметры обрезки
            if aspect_ratio == "16:9":
                target_aspect = 16 / 9
            elif aspect_ratio == "9:16":
                target_aspect = 9 / 16
            else:
                return  # Неизвестное соотношение
            
            current_aspect = video_width / video_height if video_height > 0 else 1.0
            
            # Если соотношения совпадают, не нужно ничего делать
            if abs(current_aspect - target_aspect) < 0.01:
                # Сбрасываем crop через установку aspect ratio
                try:
                    # Используем стандартный aspect ratio
                    self.player.video_set_aspect_ratio(None)
                except:
                    pass
                return
            
            # Вычисляем параметры обрезки
            if current_aspect > target_aspect:
                # Обрезаем по ширине
                new_height = video_height
                new_width = int(new_height * target_aspect)
                x_offset = (video_width - new_width) // 2
                # Используем формат crop для VLC: width:height:x:y
                crop_geometry = f"{new_width}:{new_height}:{x_offset}:0"
            else:
                # Обрезаем по высоте
                new_width = video_width
                new_height = int(new_width / target_aspect)
                y_offset = (video_height - new_height) // 2
                crop_geometry = f"{new_width}:{new_height}:0:{y_offset}"
            
            # Применяем crop через VLC
            # Пробуем использовать различные методы VLC для обрезки
            crop_applied = False
            
            # Метод 1: video_set_crop_geometry (если доступен в python-vlc)
            if hasattr(self.player, 'video_set_crop_geometry'):
                try:
                    self.player.video_set_crop_geometry(crop_geometry)
                    crop_applied = True
                    logger.info(f"Установлен crop через video_set_crop_geometry: {crop_geometry}")
                except Exception as e:
                    logger.debug(f"video_set_crop_geometry не работает: {e}")
            
            # Метод 2: video_set_crop (альтернативный метод)
            if not crop_applied and hasattr(self.player, 'video_set_crop'):
                try:
                    self.player.video_set_crop(crop_geometry)
                    crop_applied = True
                    logger.info(f"Установлен crop через video_set_crop: {crop_geometry}")
                except Exception as e:
                    logger.debug(f"video_set_crop не работает: {e}")
            
            # Метод 3: Используем фильтры через опции media
            if not crop_applied:
                try:
                    # Парсим crop_geometry
                    parts = crop_geometry.split(':')
                    if len(parts) == 4:
                        crop_w, crop_h, crop_x, crop_y = parts
                        # Создаем фильтр crop для VLC
                        crop_filter = f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y}"
                        # Применяем через опции media
                        if self.current_file:
                            media = self.instance.media_new(str(self.current_file))
                            media.add_option(f':video-filter={crop_filter}')
                            self.player.set_media(media)
                            crop_applied = True
                            logger.info(f"Установлен crop через фильтры: {crop_filter}")
                except Exception as e:
                    logger.debug(f"Не удалось применить crop через фильтры: {e}")
            
            # Метод 4: Если ничего не сработало, используем aspect ratio (менее точно)
            if not crop_applied:
                try:
                    aspect_str = f"{target_aspect:.6f}"
                    self.player.video_set_aspect_ratio(aspect_str)
                    logger.warning("Метод crop недоступен, используется aspect ratio (может оставить черные полосы)")
                except Exception as e:
                    logger.error(f"Не удалось установить соотношение сторон: {e}")
            
        except Exception as e:
            logger.error(f"Ошибка установки соотношения сторон: {e}")
    
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
            
            # Создаем media с фильтрами crop, если нужно
            media = self.instance.media_new(str(file_path))
            
            # Применяем соотношение сторон через фильтры crop
            if self.aspect_ratio:
                # Вычисляем параметры crop
                if self.aspect_ratio == "16:9":
                    target_aspect = 16 / 9
                elif self.aspect_ratio == "9:16":
                    target_aspect = 9 / 16
                else:
                    target_aspect = None
                
                if target_aspect:
                    current_aspect = self.video_width / self.video_height if self.video_height > 0 else 1.0
                    if abs(current_aspect - target_aspect) >= 0.01:
                        # Вычисляем crop
                        if current_aspect > target_aspect:
                            new_height = self.video_height
                            new_width = int(new_height * target_aspect)
                            x_offset = (self.video_width - new_width) // 2
                            y_offset = 0
                        else:
                            new_width = self.video_width
                            new_height = int(new_width / target_aspect)
                            x_offset = 0
                            y_offset = (self.video_height - new_height) // 2
                        
                        # Добавляем фильтр к media
                        # VLC использует синтаксис фильтров через опции
                        # Пробуем разные форматы для фильтра crop
                        crop_applied = False
                        
                        # Формат 1: через video-filter с синтаксисом VLC (crop без параметров, только размеры)
                        try:
                            # В VLC фильтр crop может иметь формат: crop=width:height или через другие опции
                            # Попробуем использовать scale для масштабирования до нужного размера
                            # и затем crop через методы плеера
                            vlc_crop_filter = f"scale={new_width}:{new_height}"
                            media.add_option(f':video-filter={vlc_crop_filter}')
                            crop_applied = True
                            logger.info(f"Добавлен фильтр scale (формат 1): {vlc_crop_filter}")
                            # Сохраняем параметры для применения crop через методы
                            self._pending_crop = (new_width, new_height, x_offset, y_offset)
                        except Exception as e1:
                            logger.debug(f"Формат 1 не сработал: {e1}")
                        
                        # Формат 2: через video-filter с синтаксисом crop (без параметров позиции)
                        if not crop_applied:
                            try:
                                # VLC может использовать crop=width:height
                                simple_crop = f"crop={new_width}:{new_height}"
                                media.add_option(f':video-filter={simple_crop}')
                                crop_applied = True
                                logger.info(f"Добавлен фильтр crop (формат 2): {simple_crop}")
                            except Exception as e2:
                                logger.debug(f"Формат 2 не сработал: {e2}")
                        
                        # Сохраняем параметры для применения через методы плеера после загрузки
                        if not crop_applied:
                            self._pending_crop = (new_width, new_height, x_offset, y_offset)
                            logger.info("Параметры crop сохранены для применения через методы плеера")
            
            self.player.set_media(media)
            
            # Убеждаемся, что виджет установлен (если он был передан)
            if self.video_widget is not None:
                self.set_video_widget(self.video_widget)
            
            # Применяем crop через методы плеера, если фильтры через опции не сработали
            if hasattr(self, '_pending_crop'):
                try:
                    crop_w, crop_h, crop_x, crop_y = self._pending_crop
                    # Пробуем применить crop через методы плеера после небольшой задержки
                    QTimer.singleShot(100, lambda: self._apply_crop_after_play(crop_w, crop_h, crop_x, crop_y))
                    delattr(self, '_pending_crop')
                except Exception as e:
                    logger.error(f"Ошибка применения crop: {e}")
            
            # Применяем aspect ratio, если фильтр crop не сработал
            if hasattr(self, '_pending_aspect_ratio'):
                try:
                    # Используем небольшую задержку, чтобы media успел загрузиться
                    QTimer.singleShot(200, lambda: self.player.video_set_aspect_ratio(self._pending_aspect_ratio) if self.player else None)
                    delattr(self, '_pending_aspect_ratio')
                except:
                    pass
            
            # Применяем соотношение сторон через методы плеера (если установлено)
            if self.aspect_ratio:
                # Используем задержку для применения после начала воспроизведения
                QTimer.singleShot(300, lambda: self.set_aspect_ratio(self.aspect_ratio, self.video_width, self.video_height) if self.aspect_ratio else None)
            
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
    
    def _apply_crop_after_play(self, crop_w: int, crop_h: int, crop_x: int, crop_y: int):
        """Применяет crop после начала воспроизведения."""
        if not self.player:
            return
        
        # Ждем, пока видео начнет воспроизводиться
        max_attempts = 10
        attempt = 0
        
        def try_apply_crop():
            nonlocal attempt
            attempt += 1
            
            if not self.player or attempt > max_attempts:
                return
            
            # Проверяем, что видео загружено
            if self.player.get_state() == vlc.State.Playing or self.player.get_state() == vlc.State.Paused:
                try:
                    # Пробуем разные методы для применения crop
                    # Метод 1: через video_adjust (если доступен)
                    if hasattr(self.player, 'video_set_crop_ratio'):
                        try:
                            # VLC использует формат "число:число" для crop
                            crop_ratio = f"{crop_w}:{crop_h}"
                            self.player.video_set_crop_ratio(crop_ratio)
                            logger.info(f"Применен crop через video_set_crop_ratio: {crop_ratio}")
                            return
                        except Exception as e:
                            logger.debug(f"video_set_crop_ratio не сработал: {e}")
                    
                    # Метод 2: через crop geometry
                    crop_geometry = f"{crop_w}:{crop_h}:{crop_x}:{crop_y}"
                    if hasattr(self.player, 'video_set_crop_geometry'):
                        try:
                            self.player.video_set_crop_geometry(crop_geometry)
                            logger.info(f"Применен crop через video_set_crop_geometry: {crop_geometry}")
                            return
                        except Exception as e:
                            logger.debug(f"video_set_crop_geometry не сработал: {e}")
                    
                    # Метод 3: через video_set_crop
                    if hasattr(self.player, 'video_set_crop'):
                        try:
                            self.player.video_set_crop(crop_geometry)
                            logger.info(f"Применен crop через video_set_crop: {crop_geometry}")
                            return
                        except Exception as e:
                            logger.debug(f"video_set_crop не сработал: {e}")
                    
                    # Метод 4: через масштабирование и обрезку через aspect ratio с zoom
                    try:
                        # Вычисляем масштаб для заполнения виджета
                        widget_aspect = crop_w / crop_h if crop_h > 0 else 1.0
                        aspect_str = f"{widget_aspect:.6f}"
                        self.player.video_set_aspect_ratio(aspect_str)
                        logger.info(f"Применен aspect ratio (временное решение): {aspect_str}")
                    except Exception as e:
                        logger.warning(f"Не удалось применить aspect ratio: {e}")
                except Exception as e:
                    logger.error(f"Ошибка применения crop: {e}")
            else:
                # Если видео еще не загружено, пробуем еще раз через 100мс
                QTimer.singleShot(100, try_apply_crop)
        
        # Запускаем первую попытку
        QTimer.singleShot(200, try_apply_crop)
    
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
    
    class PreviewThread(QThread):
        """Поток для создания предпросмотра с FFmpeg фильтрами."""
        preview_ready = Signal(Path)
        preview_failed = Signal(str)
        
        def __init__(self, ffmpeg_worker, input_file, start_time, end_time, brightness, contrast, 
                     saturation, sharpness, shadows, temperature, tint, aspect_ratio, speed,
                     video_width, video_height, temp_file_path):
            super().__init__()
            self.ffmpeg_worker = ffmpeg_worker
            self.input_file = input_file
            self.start_time = start_time
            self.end_time = end_time
            self.brightness = brightness
            self.contrast = contrast
            self.saturation = saturation
            self.sharpness = sharpness
            self.shadows = shadows
            self.temperature = temperature
            self.tint = tint
            self.aspect_ratio = aspect_ratio
            self.speed = speed
            self.video_width = video_width
            self.video_height = video_height
            self.temp_file_path = temp_file_path
        
        def run(self):
            """Создает предпросмотр в отдельном потоке."""
            try:
                # Используем FFmpegWorker для создания предпросмотра
                preview_profile = {
                    "codec": "libx264",
                    "preset": "ultrafast",
                    "crf": "28",
                    "audio_codec": "aac",
                    "audio_bitrate": "128k"
                }
                
                # Вычисляем длительность
                input_duration = self.end_time - self.start_time if self.end_time > self.start_time else 0.0
                if input_duration <= 0:
                    input_duration = 10.0
                    self.end_time = self.start_time + input_duration
                
                # Создаем команду FFmpeg
                cmd = self.ffmpeg_worker.build_command(
                    input_file=self.input_file,
                    output_file=self.temp_file_path,
                    start_time=self.start_time,
                    end_time=self.end_time,
                    filters=None,
                    encoding_profile=preview_profile,
                    speed=self.speed,
                    aspect_ratio=self.aspect_ratio,
                    input_width=self.video_width,
                    input_height=self.video_height,
                    brightness=self.brightness,
                    contrast=self.contrast,
                    saturation=self.saturation,
                    sharpness=self.sharpness,
                    shadows=self.shadows,
                    temperature=self.temperature,
                    tint=self.tint
                )
                
                # Запускаем FFmpeg
                logger.info(f"Создание предпросмотра с FFmpeg фильтрами: {self.temp_file_path}")
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True
                )
                
                # Ждем завершения (с таймаутом)
                try:
                    stdout, stderr = process.communicate(timeout=30)
                    if process.returncode == 0 and self.temp_file_path.exists():
                        logger.info(f"Предпросмотр создан: {self.temp_file_path}")
                        self.preview_ready.emit(self.temp_file_path)
                    else:
                        error_msg = stderr if stderr else "Неизвестная ошибка"
                        logger.error(f"Ошибка создания предпросмотра: {error_msg}")
                        self.preview_failed.emit(error_msg)
                except subprocess.TimeoutExpired:
                    process.kill()
                    logger.error("Таймаут при создании предпросмотра")
                    self.preview_failed.emit("Таймаут при создании предпросмотра")
                    
            except Exception as e:
                logger.error(f"Ошибка создания предпросмотра с FFmpeg: {e}")
                self.preview_failed.emit(str(e))
    
    def _update_preview_debounced(self):
        """Обновляет предпросмотр после задержки (debounce)."""
        if not self._pending_color_params:
            return
        
        params = self._pending_color_params
        self._pending_color_params = None
        
        if not self.current_file or not self.current_file.exists():
            return
        
        # Получаем текущую скорость
        current_rate = self.get_rate()
        
        # Вычисляем end_time для предпросмотра
        preview_end_time = self.end_time if self.end_time > self.start_time else 0.0
        if preview_end_time == 0.0:
            video_length = self.get_length()
            if video_length > 0:
                preview_end_time = min(self.start_time + 10.0, video_length)
            else:
                preview_end_time = self.start_time + 10.0
        
        # Удаляем старый временный файл, если он существует
        if self.preview_temp_file and self.preview_temp_file.exists():
            try:
                self.preview_temp_file.unlink()
            except:
                pass
        
        # Создаем новый временный файл
        temp_dir = tempfile.gettempdir()
        temp_file = Path(temp_dir) / f"videocutter_preview_{id(self)}.mp4"
        self.preview_temp_file = temp_file
        
        # Создаем поток для создания предпросмотра
        self._preview_thread = self.PreviewThread(
            self.ffmpeg_worker,
            self.current_file,
            self.start_time,
            preview_end_time,
            params['brightness'],
            params['contrast'],
            params['saturation'],
            params['sharpness'],
            params['shadows'],
            params['temperature'],
            params['tint'],
            params['aspect_ratio'],
            current_rate,
            self.video_width,
            self.video_height,
            temp_file
        )
        self._preview_thread.preview_ready.connect(self._on_preview_ready)
        self._preview_thread.preview_failed.connect(self._on_preview_failed)
        self._preview_thread.start()
    
    def _on_preview_ready(self, preview_file: Path):
        """Обработчик успешного создания предпросмотра."""
        if preview_file and preview_file.exists():
            # Воспроизводим временный файл
            was_playing = self.is_playing()
            current_pos = self.get_time()
            
            # Останавливаем текущее воспроизведение
            self.stop()
            
            # Загружаем новый файл
            self.play_file(preview_file, 0.0, 0.0)
            
            # Восстанавливаем позицию и состояние воспроизведения
            if current_pos > 0:
                QTimer.singleShot(500, lambda: self.set_time(current_pos))
            if was_playing:
                QTimer.singleShot(600, lambda: self.play())
            
            # ВАЖНО: Отключаем video_adjust, чтобы не "удваивать" коррекцию
            try:
                if hasattr(self.player, 'video_set_adjust_float'):
                    self.player.video_set_adjust_float(vlc.VideoAdjustOption.Enable, 0.0)
                elif hasattr(self.player, 'video_set_adjust_int'):
                    self.player.video_set_adjust_int(vlc.VideoAdjustOption.Enable, 0)
            except Exception:
                pass
            
            logger.info("Предпросмотр обновлен с применением FFmpeg фильтров")
    
    def _on_preview_failed(self, error_msg: str):
        """Обработчик ошибки создания предпросмотра."""
        logger.error(f"Не удалось создать предпросмотр: {error_msg}")
        # Fallback: используем стандартный метод VLC
        self.use_ffmpeg_preview = False
        # Применяем цветокоррекцию через VLC
        self._apply_vlc_color_correction(
            self.brightness, self.contrast, self.saturation, 
            self.sharpness, self.shadows, self.temperature, self.tint
        )
    
    def set_color_correction(
        self,
        brightness: float = 0.0,
        contrast: float = 1.0,
        saturation: float = 1.0,
        sharpness: float = 0.0,
        shadows: float = 0.0,
        temperature: float = 0.0,
        tint: float = 0.0
    ):
        """
        Применяет настройки цветокоррекции к предпросмотру.
        
        Args:
            brightness: Яркость (-1.0 до 1.0)
            contrast: Контрастность (0.0 до 2.0)
            saturation: Насыщенность (0.0 до 2.0)
            sharpness: Резкость (-1.0 до 1.0)
            shadows: Тени (-1.0 до 1.0, преобразуется в gamma)
            temperature: Температура (-100 до 100)
            tint: Тон (-100 до 100)
        """
        if not self.player or not self.current_file:
            return
        
        # Сохраняем параметры
        self.brightness = brightness
        self.contrast = contrast
        self.saturation = saturation
        self.sharpness = sharpness
        self.temperature = temperature
        self.tint = tint
        
        # Преобразуем shadows в gamma для VLC
        # shadows > 0 осветляет тени (gamma < 1.0), shadows < 0 затемняет (gamma > 1.0)
        # VLC использует gamma от 0.01 до 10.0
        if abs(shadows) >= 0.01:
            self.gamma = max(0.01, min(10.0, 1.0 / (1.0 + shadows * 0.5)))
        else:
            self.gamma = 1.0
        
        # Если используем FFmpeg для предпросмотра, планируем обновление с задержкой (debounce)
        if self.use_ffmpeg_preview:
            # Сохраняем параметры для отложенного обновления
            self._pending_color_params = {
                'brightness': brightness,
                'contrast': contrast,
                'saturation': saturation,
                'sharpness': sharpness,
                'shadows': shadows,
                'temperature': temperature,
                'tint': tint,
                'aspect_ratio': self.aspect_ratio or "16:9"
            }
            # Перезапускаем таймер (debounce: обновляем только после остановки движения слайдера)
            self._preview_update_timer.stop()
            self._preview_update_timer.start(500)  # 500мс задержка
            return
        
        # Иначе используем стандартный метод VLC
        self._apply_vlc_color_correction(brightness, contrast, saturation, sharpness, shadows, temperature, tint)
    
    def _apply_vlc_color_correction(
        self,
        brightness: float,
        contrast: float,
        saturation: float,
        sharpness: float,
        shadows: float,
        temperature: float,
        tint: float
    ):
        """Применяет цветокоррекцию через VLC video_adjust."""
        try:
            # Проверяем, есть ли какие-либо настройки, которые нужно применить
            has_adjustments = (
                abs(brightness) >= 0.01 or
                abs(contrast - 1.0) >= 0.01 or
                abs(saturation - 1.0) >= 0.01 or
                abs(self.gamma - 1.0) >= 0.01 or
                abs(tint) >= 0.01 or
                abs(temperature) >= 0.01
            )
            
            # Включаем или отключаем video_adjust в зависимости от наличия настроек
            if hasattr(self.player, 'video_set_adjust_float') or hasattr(self.player, 'video_set_adjust_int'):
                try:
                    if hasattr(self.player, 'video_set_adjust_float'):
                        # Включаем только если есть настройки, иначе отключаем
                        enable_value = 1.0 if has_adjustments else 0.0
                        self.player.video_set_adjust_float(vlc.VideoAdjustOption.Enable, enable_value)
                        logger.debug(f"Video adjust Enable установлен: {enable_value}")
                        
                        # ВАЖНО: Если включаем, сначала сбрасываем все значения на нейтральные
                        if enable_value > 0:
                            self.player.video_set_adjust_float(vlc.VideoAdjustOption.Brightness, 1.0)  # Нейтраль = 1.0!
                            self.player.video_set_adjust_float(vlc.VideoAdjustOption.Contrast, 1.0)
                            self.player.video_set_adjust_float(vlc.VideoAdjustOption.Saturation, 1.0)
                            self.player.video_set_adjust_float(vlc.VideoAdjustOption.Gamma, 1.0)
                            self.player.video_set_adjust_float(vlc.VideoAdjustOption.Hue, 0.0)
                            logger.debug("Все параметры video_adjust сброшены на нейтральные значения")
                    elif hasattr(self.player, 'video_set_adjust_int'):
                        enable_value = 1 if has_adjustments else 0
                        self.player.video_set_adjust_int(vlc.VideoAdjustOption.Enable, enable_value)
                        logger.debug(f"Video adjust Enable установлен: {enable_value}")
                        
                        # ВАЖНО: Если включаем, сначала сбрасываем все значения на нейтральные
                        if enable_value > 0:
                            self.player.video_set_adjust_int(vlc.VideoAdjustOption.Brightness, 100)  # 1.0 * 100
                            self.player.video_set_adjust_int(vlc.VideoAdjustOption.Contrast, 100)  # 1.0 * 100
                            self.player.video_set_adjust_int(vlc.VideoAdjustOption.Saturation, 100)  # 1.0 * 100
                            self.player.video_set_adjust_int(vlc.VideoAdjustOption.Gamma, 100)  # 1.0 * 100
                            self.player.video_set_adjust_int(vlc.VideoAdjustOption.Hue, 0)
                            logger.debug("Все параметры video_adjust сброшены на нейтральные значения")
                except Exception as e:
                    logger.debug(f"Не удалось установить Enable через video_adjust: {e}")
            
            # Если нет настроек, выходим
            if not has_adjustments:
                return
            
            # Применяем значения слайдеров, корректно промапив под VLC
            try:
                # ВАЖНО: В VLC нейтральная яркость = 1.0, а не 0.0!
                # Маппинг: brightness ∈ [-1..1] → [0..2], где 1.0 = нейтраль
                brightness_vlc = max(0.0, min(2.0, 1.0 + brightness))
                
                contrast_vlc = max(0.0, min(2.0, contrast))  # Нейтраль 1.0
                saturation_vlc = max(0.0, min(3.0, saturation))  # Нейтраль 1.0
                gamma_vlc = max(0.01, min(10.0, self.gamma))  # Нейтраль 1.0
                
                # Hue: tint преобразуем в градусы, затем нормализуем к 0..360
                hue_deg = tint * 1.8  # -180..180
                # Температура также влияет на hue
                if abs(temperature) >= 0.01:
                    hue_deg += (temperature / 100.0) * 30.0
                hue_vlc = (hue_deg + 360.0) % 360.0  # 0..360
                
                if hasattr(self.player, 'video_set_adjust_float'):
                    self.player.video_set_adjust_float(vlc.VideoAdjustOption.Brightness, brightness_vlc)
                    self.player.video_set_adjust_float(vlc.VideoAdjustOption.Contrast, contrast_vlc)
                    self.player.video_set_adjust_float(vlc.VideoAdjustOption.Saturation, saturation_vlc)
                    self.player.video_set_adjust_float(vlc.VideoAdjustOption.Gamma, gamma_vlc)
                    self.player.video_set_adjust_float(vlc.VideoAdjustOption.Hue, hue_vlc)
                    logger.debug(f"Применены значения VLC: brightness={brightness_vlc:.2f}, contrast={contrast_vlc:.2f}, "
                               f"saturation={saturation_vlc:.2f}, gamma={gamma_vlc:.2f}, hue={hue_vlc:.2f}")
                elif hasattr(self.player, 'video_set_adjust_int'):
                    brightness_int = int(brightness_vlc * 100)
                    contrast_int = int(contrast_vlc * 100)
                    saturation_int = int(saturation_vlc * 100)
                    gamma_int = int(gamma_vlc * 100)
                    hue_int = int(hue_vlc)
                    self.player.video_set_adjust_int(vlc.VideoAdjustOption.Brightness, brightness_int)
                    self.player.video_set_adjust_int(vlc.VideoAdjustOption.Contrast, contrast_int)
                    self.player.video_set_adjust_int(vlc.VideoAdjustOption.Saturation, saturation_int)
                    self.player.video_set_adjust_int(vlc.VideoAdjustOption.Gamma, gamma_int)
                    self.player.video_set_adjust_int(vlc.VideoAdjustOption.Hue, hue_int)
                    logger.debug(f"Применены значения VLC (int): brightness={brightness_int}, contrast={contrast_int}, "
                               f"saturation={saturation_int}, gamma={gamma_int}, hue={hue_int}")
            except Exception as e:
                logger.debug(f"Не удалось применить значения через video_adjust: {e}")
            
            logger.info(f"Применена цветокоррекция: brightness={brightness:.2f}, contrast={contrast:.2f}, "
                       f"saturation={saturation:.2f}, shadows={shadows:.2f}, temperature={temperature}, tint={tint}")
            
        except Exception as e:
            logger.error(f"Ошибка применения цветокоррекции: {e}")
    
    def release(self):
        """Освобождает ресурсы."""
        if self.player:
            self.player.stop()
            self.player.release()
        if self.instance:
            self.instance.release()
        
        # Удаляем временный файл предпросмотра
        if self.preview_temp_file and self.preview_temp_file.exists():
            try:
                self.preview_temp_file.unlink()
                logger.info(f"Временный файл предпросмотра удален: {self.preview_temp_file}")
            except Exception as e:
                logger.warning(f"Не удалось удалить временный файл предпросмотра: {e}")

