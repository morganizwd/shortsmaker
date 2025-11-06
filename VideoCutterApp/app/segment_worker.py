"""
Модуль для обработки многосегментного режима: экспорт отдельных файлов и склейка.
"""

import subprocess
import time
from pathlib import Path
from typing import List, Optional, Dict, Any, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.models import Segment, Project
from app.ffmpeg_worker import FFmpegWorker
from app.utils.logger import get_logger
from app.config import ENCODING_PROFILES

logger = get_logger(__name__)


class SegmentWorker:
    """Класс для обработки сегментов видео."""
    
    def __init__(self, max_workers: int = 4):
        """
        Инициализация worker для обработки сегментов.
        
        Args:
            max_workers: Максимальное количество параллельных процессов FFmpeg
        """
        self.max_workers = max_workers
        self.ffmpeg_worker = FFmpegWorker()
        self.processing = False
        self.cancelled = False
    
    def stop(self):
        """Останавливает обработку."""
        self.cancelled = True
        logger.info("Обработка сегментов остановлена")
    
    def export_segments_fast(
        self,
        input_file: Path,
        segments: List[Segment],
        output_dir: Path,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> List[Path]:
        """
        Экспортирует сегменты в отдельные файлы (быстрый режим, без перекодирования).
        
        Args:
            input_file: Входной видео файл
            segments: Список сегментов для экспорта
            output_dir: Директория для выходных файлов
            progress_callback: Функция обратного вызова для прогресса (current, total, message)
        
        Returns:
            Список путей к созданным файлам
        """
        if not input_file.exists():
            logger.error(f"Входной файл не найден: {input_file}")
            return []
        
        output_dir.mkdir(parents=True, exist_ok=True)
        self.processing = True
        self.cancelled = False
        
        enabled_segments = [s for s in segments if s.enabled]
        total = len(enabled_segments)
        completed = 0
        output_files = []
        
        def process_segment(segment: Segment, index: int) -> Optional[Path]:
            """Обрабатывает один сегмент."""
            if self.cancelled:
                return None
            
            # Генерируем имя выходного файла
            if segment.name:
                safe_name = "".join(c for c in segment.name if c.isalnum() or c in (' ', '-', '_')).strip()
                output_filename = f"{index + 1:03d}_{safe_name}.mp4"
            else:
                output_filename = f"{index + 1:03d}_segment_{segment.start_time:.2f}-{segment.end_time:.2f}.mp4"
            
            output_file = output_dir / output_filename
            
            try:
                duration = segment.end_time - segment.start_time
                
                # Быстрый режим: используем -c copy (без перекодирования)
                cmd = [
                    "ffmpeg",
                    "-y",  # Перезаписать выходной файл
                    "-ss", str(segment.start_time),
                    "-i", str(input_file),
                    "-t", str(duration),
                    "-c", "copy",  # Копирование без перекодирования
                    "-movflags", "+faststart",
                    str(output_file)
                ]
                
                logger.info(f"Экспорт сегмента {index + 1}/{total}: {output_filename}")
                
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True
                )
                
                # Ждем завершения
                stdout, stderr = process.communicate()
                
                if process.returncode == 0 and output_file.exists():
                    logger.info(f"Сегмент {index + 1} успешно экспортирован: {output_file}")
                    return output_file
                else:
                    logger.error(f"Ошибка экспорта сегмента {index + 1}: {stderr}")
                    return None
                    
            except Exception as e:
                logger.error(f"Исключение при экспорте сегмента {index + 1}: {e}")
                return None
        
        # Обрабатываем сегменты параллельно
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Запускаем задачи
            future_to_segment = {
                executor.submit(process_segment, segment, i): (segment, i)
                for i, segment in enumerate(enabled_segments)
            }
            
            # Собираем результаты
            for future in as_completed(future_to_segment):
                if self.cancelled:
                    # Отменяем оставшиеся задачи
                    for f in future_to_segment:
                        f.cancel()
                    break
                
                segment, index = future_to_segment[future]
                try:
                    result = future.result()
                    if result:
                        output_files.append(result)
                    completed += 1
                    
                    if progress_callback:
                        progress_callback(completed, total, f"Обработан сегмент {index + 1}/{total}")
                except Exception as e:
                    logger.error(f"Ошибка при обработке сегмента {index + 1}: {e}")
                    completed += 1
        
        self.processing = False
        logger.info(f"Экспорт завершен: {len(output_files)}/{total} сегментов")
        return output_files
    
    def export_segments_accurate(
        self,
        input_file: Path,
        segments: List[Segment],
        output_dir: Path,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> List[Path]:
        """
        Экспортирует сегменты в отдельные файлы (точный режим, с перекодированием).
        
        Args:
            input_file: Входной видео файл
            segments: Список сегментов для экспорта
            output_dir: Директория для выходных файлов
            progress_callback: Функция обратного вызова для прогресса (current, total, message)
        
        Returns:
            Список путей к созданным файлам
        """
        if not input_file.exists():
            logger.error(f"Входной файл не найден: {input_file}")
            return []
        
        output_dir.mkdir(parents=True, exist_ok=True)
        self.processing = True
        self.cancelled = False
        
        enabled_segments = [s for s in segments if s.enabled]
        total = len(enabled_segments)
        completed = 0
        output_files = []
        
        # Получаем информацию о видео
        from app.ffprobe_utils import get_video_info
        video_info = get_video_info(input_file)
        input_width = video_info.get("width", 1920) if video_info else 1920
        input_height = video_info.get("height", 1080) if video_info else 1080
        
        def process_segment(segment: Segment, index: int) -> Optional[Path]:
            """Обрабатывает один сегмент."""
            if self.cancelled:
                return None
            
            # Генерируем имя выходного файла
            if segment.name:
                safe_name = "".join(c for c in segment.name if c.isalnum() or c in (' ', '-', '_')).strip()
                output_filename = f"{index + 1:03d}_{safe_name}.mp4"
            else:
                output_filename = f"{index + 1:03d}_segment_{segment.start_time:.2f}-{segment.end_time:.2f}.mp4"
            
            output_file = output_dir / output_filename
            
            try:
                # Получаем профиль кодирования
                profile = ENCODING_PROFILES.get(segment.encoding_profile, ENCODING_PROFILES["balanced"])
                
                # Используем FFmpegWorker для создания команды
                cmd = self.ffmpeg_worker.build_command(
                    input_file=input_file,
                    output_file=output_file,
                    start_time=segment.start_time,
                    end_time=segment.end_time,
                    filters=None,
                    encoding_profile=profile,
                    speed=segment.speed,
                    aspect_ratio=segment.aspect_ratio,
                    input_width=input_width,
                    input_height=input_height,
                    brightness=segment.brightness,
                    contrast=segment.contrast,
                    saturation=segment.saturation,
                    sharpness=segment.sharpness,
                    shadows=segment.shadows,
                    temperature=segment.temperature,
                    tint=segment.tint
                )
                
                logger.info(f"Экспорт сегмента {index + 1}/{total} (точный режим): {output_filename}")
                
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True
                )
                
                # Ждем завершения
                stdout, stderr = process.communicate()
                
                if process.returncode == 0 and output_file.exists():
                    logger.info(f"Сегмент {index + 1} успешно экспортирован: {output_file}")
                    return output_file
                else:
                    logger.error(f"Ошибка экспорта сегмента {index + 1}: {stderr}")
                    return None
                    
            except Exception as e:
                logger.error(f"Исключение при экспорте сегмента {index + 1}: {e}")
                return None
        
        # Обрабатываем сегменты параллельно
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Запускаем задачи
            future_to_segment = {
                executor.submit(process_segment, segment, i): (segment, i)
                for i, segment in enumerate(enabled_segments)
            }
            
            # Собираем результаты
            for future in as_completed(future_to_segment):
                if self.cancelled:
                    # Отменяем оставшиеся задачи
                    for f in future_to_segment:
                        f.cancel()
                    break
                
                segment, index = future_to_segment[future]
                try:
                    result = future.result()
                    if result:
                        output_files.append(result)
                    completed += 1
                    
                    if progress_callback:
                        progress_callback(completed, total, f"Обработан сегмент {index + 1}/{total}")
                except Exception as e:
                    logger.error(f"Ошибка при обработке сегмента {index + 1}: {e}")
                    completed += 1
        
        self.processing = False
        logger.info(f"Экспорт завершен: {len(output_files)}/{total} сегментов")
        return output_files
    
    def export_concat(
        self,
        input_file: Path,
        segments: List[Segment],
        output_file: Path,
        fast_mode: bool = True,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> bool:
        """
        Экспортирует все сегменты в один файл (склейка).
        
        Args:
            input_file: Входной видео файл
            segments: Список сегментов для склейки
            output_file: Выходной файл
            fast_mode: Использовать быстрый режим (copy) или точный (re-encode)
            progress_callback: Функция обратного вызова для прогресса (progress, message)
        
        Returns:
            True если успешно, False в противном случае
        """
        if not input_file.exists():
            logger.error(f"Входной файл не найден: {input_file}")
            return False
        
        enabled_segments = [s for s in segments if s.enabled]
        if not enabled_segments:
            logger.error("Нет включенных сегментов для склейки")
            return False
        
        self.processing = True
        self.cancelled = False
        
        try:
            if fast_mode:
                # Быстрый режим: создаем временные файлы и склеиваем через concat demuxer
                return self._export_concat_fast(input_file, enabled_segments, output_file, progress_callback)
            else:
                # Точный режим: обрабатываем каждый сегмент и склеиваем
                return self._export_concat_accurate(input_file, enabled_segments, output_file, progress_callback)
        finally:
            self.processing = False
    
    def _export_concat_fast(
        self,
        input_file: Path,
        segments: List[Segment],
        output_file: Path,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> bool:
        """Быстрая склейка через concat demuxer."""
        import tempfile
        
        # Создаем временные файлы для каждого сегмента
        temp_dir = Path(tempfile.gettempdir()) / f"videocutter_concat_{int(time.time())}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_files = []
        
        try:
            if progress_callback:
                progress_callback(0.1, "Создание временных файлов сегментов...")
            
            # Создаем временные файлы для каждого сегмента
            for i, segment in enumerate(segments):
                if self.cancelled:
                    return False
                
                duration = segment.end_time - segment.start_time
                temp_file = temp_dir / f"segment_{i:03d}.mp4"
                
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-ss", str(segment.start_time),
                    "-i", str(input_file),
                    "-t", str(duration),
                    "-c", "copy",
                    "-movflags", "+faststart",
                    str(temp_file)
                ]
                
                process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
                if process.returncode == 0 and temp_file.exists():
                    temp_files.append(temp_file)
                else:
                    logger.error(f"Ошибка создания временного файла для сегмента {i + 1}")
                    return False
                
                if progress_callback:
                    progress_callback(0.1 + (i + 1) / len(segments) * 0.3, f"Создан временный файл {i + 1}/{len(segments)}")
            
            # Создаем файл списка для concat demuxer
            concat_list = temp_dir / "concat_list.txt"
            with open(concat_list, 'w', encoding='utf-8') as f:
                for temp_file in temp_files:
                    f.write(f"file '{temp_file}'\n")
            
            if progress_callback:
                progress_callback(0.5, "Склейка сегментов...")
            
            # Склеиваем файлы
            cmd = [
                "ffmpeg",
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_list),
                "-c", "copy",
                "-movflags", "+faststart",
                str(output_file)
            ]
            
            process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            
            if process.returncode == 0 and output_file.exists():
                if progress_callback:
                    progress_callback(1.0, "Склейка завершена успешно!")
                logger.info(f"Склейка завершена: {output_file}")
                return True
            else:
                logger.error(f"Ошибка склейки: {process.stderr.decode('utf-8', errors='ignore')}")
                return False
                
        finally:
            # Удаляем временные файлы
            try:
                import shutil
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Не удалось удалить временную директорию: {e}")
    
    def _export_concat_accurate(
        self,
        input_file: Path,
        segments: List[Segment],
        output_file: Path,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> bool:
        """Точная склейка с перекодированием каждого сегмента."""
        import tempfile
        
        # Создаем временные файлы для каждого сегмента с применением фильтров
        temp_dir = Path(tempfile.gettempdir()) / f"videocutter_concat_{int(time.time())}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_files = []
        
        from app.ffprobe_utils import get_video_info
        video_info = get_video_info(input_file)
        input_width = video_info.get("width", 1920) if video_info else 1920
        input_height = video_info.get("height", 1080) if video_info else 1080
        
        try:
            if progress_callback:
                progress_callback(0.1, "Обработка сегментов...")
            
            # Обрабатываем каждый сегмент
            for i, segment in enumerate(segments):
                if self.cancelled:
                    return False
                
                temp_file = temp_dir / f"segment_{i:03d}.mp4"
                profile = ENCODING_PROFILES.get(segment.encoding_profile, ENCODING_PROFILES["balanced"])
                
                cmd = self.ffmpeg_worker.build_command(
                    input_file=input_file,
                    output_file=temp_file,
                    start_time=segment.start_time,
                    end_time=segment.end_time,
                    filters=None,
                    encoding_profile=profile,
                    speed=segment.speed,
                    aspect_ratio=segment.aspect_ratio,
                    input_width=input_width,
                    input_height=input_height,
                    brightness=segment.brightness,
                    contrast=segment.contrast,
                    saturation=segment.saturation,
                    sharpness=segment.sharpness,
                    shadows=segment.shadows,
                    temperature=segment.temperature,
                    tint=segment.tint
                )
                
                process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
                if process.returncode == 0 and temp_file.exists():
                    temp_files.append(temp_file)
                else:
                    logger.error(f"Ошибка обработки сегмента {i + 1}: {process.stderr.decode('utf-8', errors='ignore')}")
                    return False
                
                if progress_callback:
                    progress_callback(0.1 + (i + 1) / len(segments) * 0.6, f"Обработан сегмент {i + 1}/{len(segments)}")
            
            # Создаем файл списка для concat demuxer
            concat_list = temp_dir / "concat_list.txt"
            with open(concat_list, 'w', encoding='utf-8') as f:
                for temp_file in temp_files:
                    f.write(f"file '{temp_file}'\n")
            
            if progress_callback:
                progress_callback(0.8, "Склейка сегментов...")
            
            # Склеиваем файлы
            cmd = [
                "ffmpeg",
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_list),
                "-c", "copy",
                "-movflags", "+faststart",
                str(output_file)
            ]
            
            process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            
            if process.returncode == 0 and output_file.exists():
                if progress_callback:
                    progress_callback(1.0, "Склейка завершена успешно!")
                logger.info(f"Склейка завершена: {output_file}")
                return True
            else:
                logger.error(f"Ошибка склейки: {process.stderr.decode('utf-8', errors='ignore')}")
                return False
                
        finally:
            # Удаляем временные файлы
            try:
                import shutil
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Не удалось удалить временную директорию: {e}")

