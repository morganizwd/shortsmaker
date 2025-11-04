"""
Код главного окна: кнопки, поля, плеер, прогресс.
"""

import os
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QFileDialog, QLabel, QLineEdit, QProgressBar, QTextEdit, QMessageBox,
    QGroupBox, QSpinBox, QDoubleSpinBox, QComboBox
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QIcon
from app.config import (
    ICON_PATH, DEFAULT_OUTPUT_DIR, ENCODING_PROFILES,
    DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT
)
from app.models import Job, FilterChain, Overlay
from app.ffmpeg_worker import FFmpegWorker
from app.ffprobe_utils import get_video_info
from app.player_vlc import VLCPlayer
from app.utils.timecode import seconds_to_timecode, timecode_to_seconds
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ProcessingThread(QThread):
    """Поток для обработки видео."""
    progress_updated = Signal(float, str)
    finished = Signal(bool, str)
    
    def __init__(self, job: Job):
        super().__init__()
        self.job = job
        self.worker = FFmpegWorker()
        self.worker.set_progress_callback(self._on_progress)
    
    def _on_progress(self, time: float, message: str):
        """Callback для обновления прогресса."""
        if self.job.end_time > self.job.start_time:
            progress = ((time - self.job.start_time) / 
                       (self.job.end_time - self.job.start_time)) * 100
            self.progress_updated.emit(progress, message)
    
    def run(self):
        """Запускает обработку."""
        try:
            self.job.status = "running"
            filters = self.job.get_all_filters()
            
            success = self.worker.execute(
                self.job.input_file,
                self.job.output_file,
                self.job.start_time,
                self.job.end_time,
                filters if filters else None,
                self.job.encoding_profile
            )
            
            if success:
                self.worker.process.wait()
                if self.worker.process.returncode == 0:
                    self.job.status = "completed"
                    self.finished.emit(True, "Обработка завершена успешно!")
                else:
                    self.job.status = "failed"
                    self.finished.emit(False, f"Ошибка обработки: код {self.worker.process.returncode}")
            else:
                self.job.status = "failed"
                self.finished.emit(False, "Не удалось запустить ffmpeg")
        except Exception as e:
            self.job.status = "failed"
            self.finished.emit(False, f"Ошибка: {str(e)}")


class MainWindow(QMainWindow):
    """Главное окно приложения."""
    
    def __init__(self):
        super().__init__()
        self.current_job: Job = None
        self.processing_thread: ProcessingThread = None
        self.video_info = None
        self.player = VLCPlayer()
        
        self.init_ui()
        self.setup_connections()
    
    def init_ui(self):
        """Инициализация интерфейса."""
        self.setWindowTitle("VideoCutterApp")
        self.setGeometry(100, 100, DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        
        # Установка иконки
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))
        
        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Главный layout
        main_layout = QVBoxLayout(central_widget)
        
        # Группа выбора файла
        file_group = QGroupBox("Выбор видео файла")
        file_layout = QHBoxLayout()
        
        self.input_file_edit = QLineEdit()
        self.input_file_edit.setPlaceholderText("Выберите входной видео файл...")
        self.input_file_btn = QPushButton("Обзор...")
        
        file_layout.addWidget(self.input_file_edit)
        file_layout.addWidget(self.input_file_btn)
        file_group.setLayout(file_layout)
        
        # Группа настроек времени
        time_group = QGroupBox("Временной диапазон")
        time_layout = QVBoxLayout()
        
        time_input_layout = QHBoxLayout()
        self.start_time_edit = QLineEdit()
        self.start_time_edit.setPlaceholderText("00:00:00.000")
        self.end_time_edit = QLineEdit()
        self.end_time_edit.setPlaceholderText("00:00:00.000")
        
        time_input_layout.addWidget(QLabel("Начало:"))
        time_input_layout.addWidget(self.start_time_edit)
        time_input_layout.addWidget(QLabel("Конец:"))
        time_input_layout.addWidget(self.end_time_edit)
        
        time_buttons_layout = QHBoxLayout()
        self.set_start_btn = QPushButton("Установить начало")
        self.set_end_btn = QPushButton("Установить конец")
        time_buttons_layout.addWidget(self.set_start_btn)
        time_buttons_layout.addWidget(self.set_end_btn)
        
        time_layout.addLayout(time_input_layout)
        time_layout.addLayout(time_buttons_layout)
        time_group.setLayout(time_layout)
        
        # Группа выходного файла
        output_group = QGroupBox("Выходной файл")
        output_layout = QHBoxLayout()
        
        self.output_file_edit = QLineEdit()
        self.output_file_edit.setPlaceholderText("Путь к выходному файлу...")
        self.output_file_btn = QPushButton("Обзор...")
        
        output_layout.addWidget(self.output_file_edit)
        output_layout.addWidget(self.output_file_btn)
        output_group.setLayout(output_layout)
        
        # Группа профиля кодирования
        encoding_group = QGroupBox("Профиль кодирования")
        encoding_layout = QHBoxLayout()
        
        self.encoding_profile_combo = QComboBox()
        self.encoding_profile_combo.addItems(list(ENCODING_PROFILES.keys()))
        self.encoding_profile_combo.setCurrentText("balanced")
        
        encoding_layout.addWidget(QLabel("Профиль:"))
        encoding_layout.addWidget(self.encoding_profile_combo)
        encoding_layout.addStretch()
        encoding_group.setLayout(encoding_layout)
        
        # Прогресс бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_label = QLabel("Готов к работе")
        
        # Кнопки управления
        buttons_layout = QHBoxLayout()
        self.preview_btn = QPushButton("Предпросмотр")
        self.process_btn = QPushButton("Обработать")
        self.stop_btn = QPushButton("Остановить")
        self.stop_btn.setEnabled(False)
        
        buttons_layout.addWidget(self.preview_btn)
        buttons_layout.addWidget(self.process_btn)
        buttons_layout.addWidget(self.stop_btn)
        buttons_layout.addStretch()
        
        # Лог
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        
        # Добавление в главный layout
        main_layout.addWidget(file_group)
        main_layout.addWidget(time_group)
        main_layout.addWidget(output_group)
        main_layout.addWidget(encoding_group)
        main_layout.addWidget(self.progress_label)
        main_layout.addWidget(self.progress_bar)
        main_layout.addLayout(buttons_layout)
        main_layout.addWidget(QLabel("Лог:"))
        main_layout.addWidget(self.log_text)
    
    def setup_connections(self):
        """Настройка сигналов и слотов."""
        self.input_file_btn.clicked.connect(self.select_input_file)
        self.output_file_btn.clicked.connect(self.select_output_file)
        self.set_start_btn.clicked.connect(self.set_start_time)
        self.set_end_btn.clicked.connect(self.set_end_time)
        self.preview_btn.clicked.connect(self.preview_video)
        self.process_btn.clicked.connect(self.process_video)
        self.stop_btn.clicked.connect(self.stop_processing)
    
    def log(self, message: str):
        """Добавляет сообщение в лог."""
        self.log_text.append(message)
        logger.info(message)
    
    def select_input_file(self):
        """Выбор входного файла."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите видео файл",
            "",
            "Video Files (*.mp4 *.avi *.mkv *.mov *.flv *.wmv);;All Files (*)"
        )
        
        if file_path:
            self.input_file_edit.setText(file_path)
            self.load_video_info(file_path)
            self.auto_set_output_path(file_path)
    
    def load_video_info(self, file_path: str):
        """Загружает информацию о видео."""
        video_path = Path(file_path)
        self.video_info = get_video_info(video_path)
        
        if self.video_info:
            duration = self.video_info.get("duration", 0)
            self.end_time_edit.setText(seconds_to_timecode(duration))
            self.log(f"Загружено видео: длительность {seconds_to_timecode(duration)}, "
                    f"FPS: {self.video_info.get('fps', 0):.2f}")
        else:
            QMessageBox.warning(self, "Ошибка", "Не удалось загрузить информацию о видео")
    
    def auto_set_output_path(self, input_path: str):
        """Автоматически устанавливает путь выходного файла."""
        input_path_obj = Path(input_path)
        output_dir = DEFAULT_OUTPUT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = output_dir / f"{input_path_obj.stem}_cut{input_path_obj.suffix}"
        self.output_file_edit.setText(str(output_path))
    
    def select_output_file(self):
        """Выбор выходного файла."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить видео как",
            "",
            "Video Files (*.mp4 *.avi *.mkv);;All Files (*)"
        )
        
        if file_path:
            self.output_file_edit.setText(file_path)
    
    def set_start_time(self):
        """Устанавливает время начала из текущей позиции плеера."""
        if self.player.is_playing():
            current_time = self.player.get_time()
            self.start_time_edit.setText(seconds_to_timecode(current_time))
    
    def set_end_time(self):
        """Устанавливает время окончания из текущей позиции плеера."""
        if self.player.is_playing():
            current_time = self.player.get_time()
            self.end_time_edit.setText(seconds_to_timecode(current_time))
    
    def preview_video(self):
        """Предпросмотр видео."""
        input_path = self.input_file_edit.text()
        if not input_path or not Path(input_path).exists():
            QMessageBox.warning(self, "Ошибка", "Выберите входной файл")
            return
        
        start_time_str = self.start_time_edit.text()
        end_time_str = self.end_time_edit.text()
        
        if not start_time_str or not end_time_str:
            QMessageBox.warning(self, "Ошибка", "Установите время начала и окончания")
            return
        
        start_time = timecode_to_seconds(start_time_str)
        end_time = timecode_to_seconds(end_time_str)
        
        if start_time >= end_time:
            QMessageBox.warning(self, "Ошибка", "Время начала должно быть меньше времени окончания")
            return
        
        self.player.play_file(Path(input_path), start_time, end_time)
        self.log(f"Предпросмотр: {start_time_str} - {end_time_str}")
    
    def process_video(self):
        """Обработка видео."""
        # Валидация
        input_path = self.input_file_edit.text()
        output_path = self.output_file_edit.text()
        
        if not input_path or not output_path:
            QMessageBox.warning(self, "Ошибка", "Заполните все поля")
            return
        
        start_time_str = self.start_time_edit.text()
        end_time_str = self.end_time_edit.text()
        
        if not start_time_str or not end_time_str:
            QMessageBox.warning(self, "Ошибка", "Установите время начала и окончания")
            return
        
        start_time = timecode_to_seconds(start_time_str)
        end_time = timecode_to_seconds(end_time_str)
        
        # Создание задачи
        job = Job(
            input_file=Path(input_path),
            output_file=Path(output_path),
            start_time=start_time,
            end_time=end_time,
            encoding_profile=ENCODING_PROFILES[self.encoding_profile_combo.currentText()]
        )
        
        is_valid, error = job.validate()
        if not is_valid:
            QMessageBox.critical(self, "Ошибка", error)
            return
        
        # Запуск обработки
        self.current_job = job
        self.processing_thread = ProcessingThread(job)
        self.processing_thread.progress_updated.connect(self.update_progress)
        self.processing_thread.finished.connect(self.on_processing_finished)
        
        self.process_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        
        self.log(f"Начало обработки: {input_path}")
        self.processing_thread.start()
    
    def update_progress(self, progress: float, message: str):
        """Обновление прогресса."""
        self.progress_bar.setValue(int(progress))
        self.progress_label.setText(message)
    
    def on_processing_finished(self, success: bool, message: str):
        """Обработка завершения."""
        self.process_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        
        if success:
            self.progress_bar.setValue(100)
            QMessageBox.information(self, "Успех", message)
        else:
            QMessageBox.critical(self, "Ошибка", message)
        
        self.log(message)
    
    def stop_processing(self):
        """Остановка обработки."""
        if self.processing_thread and self.processing_thread.isRunning():
            self.processing_thread.worker.stop()
            self.processing_thread.terminate()
            self.processing_thread.wait()
            self.current_job.status = "cancelled"
            self.log("Обработка остановлена пользователем")
            self.on_processing_finished(False, "Обработка остановлена")

