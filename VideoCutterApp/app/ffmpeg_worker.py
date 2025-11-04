"""
Запуск ffmpeg, парсинг прогресса, обёртки команд.
"""

import subprocess
import re
import threading
from pathlib import Path
from typing import Optional, Callable, Dict, List, Tuple
from app.config import FFMPEG_EXE
from app.utils.paths import find_ffmpeg
from app.utils.logger import get_logger

logger = get_logger(__name__)


class FFmpegWorker:
    """Класс для работы с ffmpeg."""
    
    def __init__(self):
        self.ffmpeg_path = find_ffmpeg()
        self.process: Optional[subprocess.Popen] = None
        self.is_running = False
        self.progress_callback: Optional[Callable[[float, str], None]] = None
        
    def set_progress_callback(self, callback: Callable[[float, str], None]):
        """Установить callback для обновления прогресса."""
        self.progress_callback = callback
    
    def parse_progress(self, line: str) -> Optional[Dict[str, any]]:
        """
        Парсит строку вывода ffmpeg для извлечения прогресса.
        Формат: frame=  123 fps= 25 q=28.0 size=    1024kB time=00:00:05.00 bitrate=1677.7kbits/s
        """
        # Извлечение времени
        time_match = re.search(r'time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})', line)
        if time_match:
            hours, minutes, seconds, centiseconds = map(int, time_match.groups())
            total_seconds = hours * 3600 + minutes * 60 + seconds + centiseconds / 100.0
            
            # Извлечение frame
            frame_match = re.search(r'frame=\s*(\d+)', line)
            frame = int(frame_match.group(1)) if frame_match else 0
            
            # Извлечение fps
            fps_match = re.search(r'fps=\s*([\d.]+)', line)
            fps = float(fps_match.group(1)) if fps_match else 0
            
            # Извлечение размера
            size_match = re.search(r'size=\s*(\d+)([kKmMgG]?)B', line)
            size_kb = 0
            if size_match:
                size_val = int(size_match.group(1))
                unit = size_match.group(2).upper()
                multipliers = {'': 1, 'K': 1024, 'M': 1024**2, 'G': 1024**3}
                size_kb = size_val * multipliers.get(unit, 1) / 1024
            
            return {
                'time': total_seconds,
                'frame': frame,
                'fps': fps,
                'size_kb': size_kb,
            }
        return None
    
    def _build_speed_filters(self, speed: float) -> Tuple[List[str], List[str]]:
        """
        Строит фильтры для изменения скорости.
        
        Args:
            speed: Скорость воспроизведения
        
        Returns:
            tuple: (видео фильтры, аудио фильтры)
        """
        video_filters = []
        audio_filters = []
        
        if abs(speed - 1.0) < 0.01:  # Скорость близка к 1.0
            return video_filters, audio_filters
        
        # Видео фильтр: setpts изменяет PTS (presentation timestamp)
        # setpts=PTS/speed - ускоряет видео (чем больше speed, тем быстрее)
        video_filters.append(f"setpts=PTS/{speed}")
        
        # Аудио фильтр: atempo работает в диапазоне 0.5-2.0
        # Для значений вне диапазона нужно применять несколько раз
        if speed >= 0.5 and speed <= 2.0:
            audio_filters.append(f"atempo={speed}")
        elif speed > 2.0:
            # Для speed > 2.0: применяем atempo=2.0 несколько раз, затем оставшуюся часть
            remaining = speed
            while remaining > 2.0:
                audio_filters.append("atempo=2.0")
                remaining = remaining / 2.0
            if remaining > 1.0:
                audio_filters.append(f"atempo={remaining}")
        elif speed < 0.5:
            # Для speed < 0.5: применяем atempo=0.5 несколько раз, затем оставшуюся часть
            remaining = speed
            while remaining < 0.5:
                audio_filters.append("atempo=0.5")
                remaining = remaining / 0.5
            if remaining < 1.0:
                audio_filters.append(f"atempo={remaining}")
        
        return video_filters, audio_filters
    
    def build_command(
        self,
        input_file: Path,
        output_file: Path,
        start_time: float,
        end_time: float,
        filters: List[str] = None,
        encoding_profile: Dict[str, any] = None,
        speed: float = 1.0
    ) -> List[str]:
        """Строит команду ffmpeg."""
        # Вычисляем длительность исходного видео для обрезки
        input_duration = end_time - start_time
        
        cmd = [
            str(self.ffmpeg_path),
            "-y",  # Перезаписать выходной файл
        ]
        
        # Используем -ss после -i для более точной обрезки
        # Это важно при использовании фильтров скорости, чтобы избежать проблем с ключевыми кадрами
        cmd.extend(["-i", str(input_file)])
        cmd.extend(["-ss", str(start_time)])
        cmd.extend(["-t", str(input_duration)])
        # Добавляем параметры для корректной обработки временных меток
        cmd.extend(["-avoid_negative_ts", "make_zero"])
        cmd.extend(["-async", "1"])  # Синхронизация аудио и видео
        
        # Построение фильтров скорости
        video_filters_list = []
        audio_filters_list = []
        
        # Применяем фильтры скорости (если скорость != 1.0)
        if abs(speed - 1.0) >= 0.01:
            speed_video_filters, speed_audio_filters = self._build_speed_filters(speed)
            video_filters_list.extend(speed_video_filters)
            audio_filters_list.extend(speed_audio_filters)
        
        # Добавление пользовательских фильтров
        if filters:
            video_filters_list.extend(filters)
        
        # Добавление видео фильтров
        if video_filters_list:
            cmd.extend(["-vf", ",".join(video_filters_list)])
        
        # Добавление аудио фильтров
        if audio_filters_list:
            cmd.extend(["-af", ",".join(audio_filters_list)])
        
        # Добавление параметров кодирования
        if encoding_profile:
            cmd.extend(["-c:v", encoding_profile.get("codec", "libx264")])
            cmd.extend(["-preset", encoding_profile.get("preset", "medium")])
            cmd.extend(["-crf", str(encoding_profile.get("crf", 20))])
            cmd.extend(["-c:a", encoding_profile.get("audio_codec", "aac")])
            cmd.extend(["-b:a", encoding_profile.get("audio_bitrate", "192k")])
        
        cmd.append(str(output_file))
        return cmd
    
    def execute(
        self,
        input_file: Path,
        output_file: Path,
        start_time: float,
        end_time: float,
        filters: List[str] = None,
        encoding_profile: Dict[str, any] = None,
        speed: float = 1.0
    ) -> bool:
        """Выполняет команду ffmpeg."""
        if self.is_running:
            logger.warning("FFmpeg уже выполняется")
            return False
        
        cmd = self.build_command(
            input_file, output_file, start_time, end_time, filters, encoding_profile, speed
        )
        
        logger.info(f"Запуск ffmpeg: {' '.join(cmd)}")
        
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            self.is_running = True
            
            # Чтение вывода в отдельном потоке
            thread = threading.Thread(target=self._read_output, daemon=True)
            thread.start()
            
            return True
        except Exception as e:
            logger.error(f"Ошибка запуска ffmpeg: {e}")
            self.is_running = False
            return False
    
    def _read_output(self):
        """Читает вывод ffmpeg и парсит прогресс."""
        if not self.process:
            return
        
        try:
            for line in iter(self.process.stdout.readline, ''):
                if not line:
                    break
                
                progress_data = self.parse_progress(line)
                if progress_data and self.progress_callback:
                    self.progress_callback(
                        progress_data['time'],
                        f"Время: {progress_data['time']:.1f}s, "
                        f"FPS: {progress_data['fps']:.1f}, "
                        f"Размер: {progress_data['size_kb']:.1f} KB"
                    )
            
            self.process.wait()
            return_code = self.process.returncode
            
            if return_code == 0:
                logger.info("FFmpeg успешно завершил работу")
                if self.progress_callback:
                    self.progress_callback(100.0, "Готово!")
            else:
                logger.error(f"FFmpeg завершился с ошибкой: код {return_code}")
                if self.progress_callback:
                    self.progress_callback(-1.0, f"Ошибка: код {return_code}")
        except Exception as e:
            logger.error(f"Ошибка чтения вывода ffmpeg: {e}")
        finally:
            self.is_running = False
    
    def stop(self):
        """Останавливает выполнение ffmpeg."""
        if self.process and self.is_running:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.is_running = False
            logger.info("FFmpeg остановлен")

