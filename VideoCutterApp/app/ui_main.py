"""
Код главного окна: кнопки, поля, плеер, прогресс.
"""

import os
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QFileDialog, QLabel, QLineEdit, QProgressBar, QTextEdit, QMessageBox,
    QGroupBox, QSpinBox, QDoubleSpinBox, QComboBox, QSplitter, QSlider,
    QStackedWidget, QTabWidget
)
from PySide6.QtGui import QRegion
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QIcon
from app.config import (
    ICON_PATH, DEFAULT_OUTPUT_DIR, ENCODING_PROFILES,
    DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT
)
from app.models import Job, FilterChain, Overlay, Segment, Project
from typing import Optional
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
            
            # Получаем размеры исходного видео
            video_info = get_video_info(self.job.input_file)
            input_width = video_info.get("width", 1920) if video_info else 1920
            input_height = video_info.get("height", 1080) if video_info else 1080
            
            success = self.worker.execute(
                self.job.input_file,
                self.job.output_file,
                self.job.start_time,
                self.job.end_time,
                filters if filters else None,
                self.job.encoding_profile,
                self.job.speed,
                self.job.aspect_ratio,
                input_width,
                input_height,
                self.job.brightness,
                self.job.contrast,
                self.job.saturation,
                self.job.sharpness,
                self.job.shadows,
                self.job.temperature,
                self.job.tint
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
        self.video_widget = None  # Будет создан в init_ui
        self.player = None  # Будет создан после video_widget
        self.preview_start_time = None  # Время начала для предпросмотра
        self.preview_end_time = None  # Время окончания для предпросмотра
        self.current_project: Optional[Project] = None  # Проект многосегментного режима
        self.temp_in_time: Optional[float] = None  # Временная метка In для создания сегмента
        self.temp_out_time: Optional[float] = None  # Временная метка Out для создания сегмента
        
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
        
        # Главный layout с разделителем (splitter)
        main_layout = QHBoxLayout(central_widget)
        splitter = QSplitter(Qt.Horizontal)
        
        # Левая панель: элементы управления
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # Правая панель: предпросмотр видео
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # Виджет для видео с элементами управления
        video_group = QGroupBox("Предпросмотр видео")
        video_layout = QVBoxLayout()
        
        # Контейнер для видео и индикатора загрузки
        video_container = QWidget()
        video_container_layout = QVBoxLayout(video_container)
        video_container_layout.setContentsMargins(0, 0, 0, 0)
        
        # Виджет для видео с поддержкой масштабирования
        # Используем QWidget для встраивания VLC
        self.video_widget = QWidget()
        self.video_widget.setMinimumSize(320, 180)  # Минимальный размер для маленьких окон
        # Разрешаем виджету расширяться
        from PySide6.QtWidgets import QSizePolicy
        self.video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_widget.setStyleSheet("background-color: black;")
        
        # Индикатор загрузки (скрыт по умолчанию)
        self.preview_loading_widget = QWidget()
        self.preview_loading_widget.setStyleSheet("background-color: rgba(0, 0, 0, 200);")
        loading_layout = QVBoxLayout(self.preview_loading_widget)
        loading_layout.setAlignment(Qt.AlignCenter)
        
        self.preview_loading_label = QLabel("Создание предпросмотра...")
        self.preview_loading_label.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")
        self.preview_loading_label.setAlignment(Qt.AlignCenter)
        
        self.preview_loading_progress = QProgressBar()
        self.preview_loading_progress.setRange(0, 0)  # Неопределенный прогресс
        self.preview_loading_progress.setStyleSheet("""
            QProgressBar {
                border: 2px solid white;
                border-radius: 5px;
                text-align: center;
                color: white;
                background-color: rgba(255, 255, 255, 50);
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 3px;
            }
        """)
        self.preview_loading_progress.setFixedWidth(200)
        self.preview_loading_progress.setFixedHeight(20)
        
        loading_layout.addWidget(self.preview_loading_label)
        loading_layout.addWidget(self.preview_loading_progress, alignment=Qt.AlignCenter)
        
        # Используем QStackedWidget для переключения между видео и индикатором
        self.video_stack = QStackedWidget()
        self.video_stack.addWidget(self.video_widget)
        self.video_stack.addWidget(self.preview_loading_widget)
        self.video_stack.setCurrentWidget(self.video_widget)  # По умолчанию показываем видео
        
        video_container_layout.addWidget(self.video_stack, stretch=1)
        video_layout.addWidget(video_container, stretch=1)  # Добавляем stretch для расширения
        
        # Элементы управления воспроизведением
        controls_layout = QVBoxLayout()
        
        # Таймлайн (слайдер)
        timeline_layout = QHBoxLayout()
        self.time_label = QLabel("00:00:00.000 / 00:00:00.000")
        self.timeline_slider = QSlider(Qt.Horizontal)
        self.timeline_slider.setMinimum(0)
        self.timeline_slider.setMaximum(1000)
        self.timeline_slider.setValue(0)
        self.timeline_slider.setEnabled(False)
        timeline_layout.addWidget(self.time_label)
        timeline_layout.addWidget(self.timeline_slider)
        controls_layout.addLayout(timeline_layout)
        
        # Кнопки управления
        buttons_controls_layout = QHBoxLayout()
        self.play_pause_btn = QPushButton("▶ Воспроизвести")
        self.stop_btn_player = QPushButton("⏹ Остановить")
        self.frame_back_btn = QPushButton("⏮ Кадр назад")
        self.frame_forward_btn = QPushButton("Кадр вперед ⏭")
        
        buttons_controls_layout.addWidget(self.play_pause_btn)
        buttons_controls_layout.addWidget(self.stop_btn_player)
        buttons_controls_layout.addWidget(self.frame_back_btn)
        buttons_controls_layout.addWidget(self.frame_forward_btn)
        buttons_controls_layout.addStretch()
        controls_layout.addLayout(buttons_controls_layout)
        
        # Слайдер скорости воспроизведения
        speed_layout = QHBoxLayout()
        speed_label = QLabel("Скорость:")
        self.speed_value_label = QLabel("1.0x")
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setMinimum(5)  # 0.5x
        self.speed_slider.setMaximum(30)  # 3.0x
        self.speed_slider.setValue(10)  # 1.0x (нормальная скорость)
        self.speed_slider.setTickPosition(QSlider.TicksBelow)
        self.speed_slider.setTickInterval(5)
        self.speed_slider.setSingleStep(1)
        speed_layout.addWidget(speed_label)
        speed_layout.addWidget(self.speed_slider)
        speed_layout.addWidget(self.speed_value_label)
        controls_layout.addLayout(speed_layout)
        
        video_layout.addLayout(controls_layout)
        video_group.setLayout(video_layout)
        
        right_layout.addWidget(video_group)
        right_panel.setLayout(right_layout)
        
        # Таймер для обновления позиции слайдера
        self.position_timer = QTimer()
        self.position_timer.timeout.connect(self.update_video_position)
        self.is_seeking = False  # Флаг для предотвращения конфликтов при перемотке
        
        # Инициализация плеера (будет настроен после показа окна)
        self.player = None
        
        # Создаем вкладки для переключения между режимами
        self.mode_tabs = QTabWidget()
        self.mode_tabs.setTabPosition(QTabWidget.TabPosition.North)
        
        # Обычный режим (существующие элементы)
        normal_mode_widget = QWidget()
        normal_mode_layout = QVBoxLayout(normal_mode_widget)
        normal_mode_layout.setContentsMargins(0, 0, 0, 0)
        
        # Группа выбора файла
        file_group = QGroupBox("Выбор видео файла")
        file_layout = QVBoxLayout()
        
        # Поле ввода и кнопка
        file_input_layout = QHBoxLayout()
        self.input_file_edit = QLineEdit()
        self.input_file_edit.setPlaceholderText("Выберите входной видео файл...")
        self.input_file_btn = QPushButton("Обзор...")
        
        file_input_layout.addWidget(self.input_file_edit)
        file_input_layout.addWidget(self.input_file_btn)
        file_layout.addLayout(file_input_layout)
        
        # Метаданные видео (мелким шрифтом)
        self.video_metadata_label = QLabel("")
        self.video_metadata_label.setStyleSheet("color: gray; font-size: 9pt;")
        self.video_metadata_label.setWordWrap(True)
        self.video_metadata_label.setVisible(False)  # Скрыт по умолчанию
        file_layout.addWidget(self.video_metadata_label)
        
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
        
        # Группа соотношения сторон
        aspect_group = QGroupBox("Соотношение сторон")
        aspect_layout = QHBoxLayout()
        
        self.aspect_ratio_combo = QComboBox()
        self.aspect_ratio_combo.addItems(["16:9", "9:16"])
        self.aspect_ratio_combo.setCurrentText("16:9")
        self.aspect_ratio_combo.currentTextChanged.connect(self.on_aspect_ratio_changed)
        
        aspect_layout.addWidget(QLabel("Соотношение:"))
        aspect_layout.addWidget(self.aspect_ratio_combo)
        aspect_layout.addStretch()
        aspect_group.setLayout(aspect_layout)
        
        # Группа настроек цветокоррекции
        color_group = QGroupBox("Цветокоррекция")
        color_layout = QVBoxLayout()
        
        # Яркость
        brightness_layout = QHBoxLayout()
        brightness_label = QLabel("Яркость:")
        self.brightness_slider = QSlider(Qt.Horizontal)
        self.brightness_slider.setRange(0, 200)  # 0-200, где 100 = 0.0 (нейтральная яркость)
        self.brightness_slider.setValue(100)  # Дефолт = нейтральная яркость
        self.brightness_value_label = QLabel("0.0")
        self.brightness_value_label.setMinimumWidth(50)
        brightness_layout.addWidget(brightness_label)
        brightness_layout.addWidget(self.brightness_slider)
        brightness_layout.addWidget(self.brightness_value_label)
        color_layout.addLayout(brightness_layout)
        
        # Контрастность
        contrast_layout = QHBoxLayout()
        contrast_label = QLabel("Контраст:")
        self.contrast_slider = QSlider(Qt.Horizontal)
        self.contrast_slider.setRange(0, 200)  # 0.0 до 2.0 (будет делить на 100)
        self.contrast_slider.setValue(100)
        self.contrast_value_label = QLabel("1.0")
        self.contrast_value_label.setMinimumWidth(50)
        contrast_layout.addWidget(contrast_label)
        contrast_layout.addWidget(self.contrast_slider)
        contrast_layout.addWidget(self.contrast_value_label)
        color_layout.addLayout(contrast_layout)
        
        # Насыщенность
        saturation_layout = QHBoxLayout()
        saturation_label = QLabel("Насыщенность:")
        self.saturation_slider = QSlider(Qt.Horizontal)
        self.saturation_slider.setRange(0, 200)  # 0.0 до 2.0 (будет делить на 100)
        self.saturation_slider.setValue(100)
        self.saturation_value_label = QLabel("1.0")
        self.saturation_value_label.setMinimumWidth(50)
        saturation_layout.addWidget(saturation_label)
        saturation_layout.addWidget(self.saturation_slider)
        saturation_layout.addWidget(self.saturation_value_label)
        color_layout.addLayout(saturation_layout)
        
        # Резкость
        sharpness_layout = QHBoxLayout()
        sharpness_label = QLabel("Резкость:")
        self.sharpness_slider = QSlider(Qt.Horizontal)
        self.sharpness_slider.setRange(-100, 100)  # -1.0 до 1.0 (будет делить на 100)
        self.sharpness_slider.setValue(0)
        self.sharpness_value_label = QLabel("0.0")
        self.sharpness_value_label.setMinimumWidth(50)
        sharpness_layout.addWidget(sharpness_label)
        sharpness_layout.addWidget(self.sharpness_slider)
        sharpness_layout.addWidget(self.sharpness_value_label)
        color_layout.addLayout(sharpness_layout)
        
        # Тени
        shadows_layout = QHBoxLayout()
        shadows_label = QLabel("Тени:")
        self.shadows_slider = QSlider(Qt.Horizontal)
        self.shadows_slider.setRange(-100, 100)  # -1.0 до 1.0 (будет делить на 100)
        self.shadows_slider.setValue(0)
        self.shadows_value_label = QLabel("0.0")
        self.shadows_value_label.setMinimumWidth(50)
        shadows_layout.addWidget(shadows_label)
        shadows_layout.addWidget(self.shadows_slider)
        shadows_layout.addWidget(self.shadows_value_label)
        color_layout.addLayout(shadows_layout)
        
        # Температура
        temperature_layout = QHBoxLayout()
        temperature_label = QLabel("Температура:")
        self.temperature_slider = QSlider(Qt.Horizontal)
        self.temperature_slider.setRange(-100, 100)  # -100 до 100
        self.temperature_slider.setValue(0)
        self.temperature_value_label = QLabel("0")
        self.temperature_value_label.setMinimumWidth(50)
        temperature_layout.addWidget(temperature_label)
        temperature_layout.addWidget(self.temperature_slider)
        temperature_layout.addWidget(self.temperature_value_label)
        color_layout.addLayout(temperature_layout)
        
        # Тон
        tint_layout = QHBoxLayout()
        tint_label = QLabel("Тон:")
        self.tint_slider = QSlider(Qt.Horizontal)
        self.tint_slider.setRange(-100, 100)  # -100 до 100
        self.tint_slider.setValue(0)
        self.tint_value_label = QLabel("0")
        self.tint_value_label.setMinimumWidth(50)
        tint_layout.addWidget(tint_label)
        tint_layout.addWidget(self.tint_slider)
        tint_layout.addWidget(self.tint_value_label)
        color_layout.addLayout(tint_layout)
        
        # Кнопка сброса параметров
        reset_layout = QHBoxLayout()
        reset_layout.addStretch()
        self.reset_color_btn = QPushButton("Сбросить к значениям по умолчанию")
        reset_layout.addWidget(self.reset_color_btn)
        color_layout.addLayout(reset_layout)
        
        color_group.setLayout(color_layout)
        
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
        
        # Добавление в обычный режим
        normal_mode_layout.addWidget(file_group)
        normal_mode_layout.addWidget(time_group)
        normal_mode_layout.addWidget(output_group)
        normal_mode_layout.addWidget(aspect_group)
        normal_mode_layout.addWidget(color_group)
        normal_mode_layout.addWidget(encoding_group)
        normal_mode_layout.addWidget(self.progress_label)
        normal_mode_layout.addWidget(self.progress_bar)
        normal_mode_layout.addLayout(buttons_layout)
        normal_mode_layout.addWidget(QLabel("Лог:"))
        normal_mode_layout.addWidget(self.log_text)
        normal_mode_layout.addStretch()
        normal_mode_widget.setLayout(normal_mode_layout)
        
        # Многосегментный режим
        from app.ui_segments import SegmentsModeWidget
        self.segments_widget = SegmentsModeWidget()
        self.segments_widget.setup_shortcuts(self)
        
        # Добавляем вкладки
        self.mode_tabs.addTab(normal_mode_widget, "Обычный режим")
        self.mode_tabs.addTab(self.segments_widget, "Многосегментный режим")
        
        # Добавление вкладок в левую панель
        left_layout.addWidget(self.mode_tabs)
        left_panel.setLayout(left_layout)
        
        # Добавление панелей в splitter
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)  # Левая панель может изменяться
        splitter.setStretchFactor(1, 2)  # Правая панель (видео) занимает больше места
        
        # Добавление splitter в главный layout
        main_layout.addWidget(splitter)
        
        # Инициализация плеера после создания виджета
        # Используем single-shot timer, чтобы убедиться, что виджет виден
        QTimer.singleShot(100, self._init_player)
    
    def _init_player(self):
        """Инициализирует VLC плеер после того, как виджет будет виден."""
        if self.video_widget is not None:
            # Создаем callback функции для показа/скрытия индикатора загрузки
            def show_preview_loading():
                """Показывает индикатор загрузки."""
                if hasattr(self, 'video_stack'):
                    self.video_stack.setCurrentWidget(self.preview_loading_widget)
            
            def hide_preview_loading():
                """Скрывает индикатор загрузки."""
                if hasattr(self, 'video_stack'):
                    self.video_stack.setCurrentWidget(self.video_widget)
            
            self.player = VLCPlayer(
                self.video_widget,
                on_preview_start=show_preview_loading,
                on_preview_end=hide_preview_loading
            )
            # Убеждаемся, что виджет правильно настроен
            if self.player:
                self.player.set_video_widget(self.video_widget)
    
    def setup_connections(self):
        """Настройка сигналов и слотов."""
        self.input_file_btn.clicked.connect(self.select_input_file)
        self.output_file_btn.clicked.connect(self.select_output_file)
        self.set_start_btn.clicked.connect(self.set_start_time)
        self.set_end_btn.clicked.connect(self.set_end_time)
        self.preview_btn.clicked.connect(self.preview_video)
        self.process_btn.clicked.connect(self.process_video)
        self.stop_btn.clicked.connect(self.stop_processing)
        
        # Элементы управления видео
        self.play_pause_btn.clicked.connect(self.toggle_play_pause)
        self.stop_btn_player.clicked.connect(self.stop_video_playback)
        self.frame_back_btn.clicked.connect(self.on_frame_back_clicked)
        self.frame_forward_btn.clicked.connect(self.on_frame_forward_clicked)
        
        # Подключение обработчиков многосегментного режима
        if hasattr(self, 'segments_widget'):
            self.segments_widget.set_in_btn.clicked.connect(self.segments_set_in)
            self.segments_widget.set_out_btn.clicked.connect(self.segments_set_out)
            self.segments_widget.add_segment_btn.clicked.connect(self.segments_add_clip)
            self.segments_widget.delete_segment_btn.clicked.connect(self.segments_delete)
            self.segments_widget.duplicate_segment_btn.clicked.connect(self.segments_duplicate)
            self.segments_widget.save_project_btn.clicked.connect(self.segments_save_project)
            self.segments_widget.load_project_btn.clicked.connect(self.segments_load_project)
            self.segments_widget.export_btn.clicked.connect(self.segments_export)
            self.segments_widget.timeline_widget.segment_clicked.connect(self.segments_on_click)
            
            # Обновление временной шкалы при изменении времени воспроизведения
            self.position_timer.timeout.connect(self.segments_update_timeline)
        self.timeline_slider.sliderPressed.connect(self.on_slider_pressed)
        self.timeline_slider.sliderReleased.connect(self.on_slider_released)
        self.timeline_slider.valueChanged.connect(self.on_slider_value_changed)
        self.speed_slider.valueChanged.connect(self.on_speed_changed)
        
        # Подключение обработчиков для слайдеров цветокоррекции
        self.brightness_slider.valueChanged.connect(lambda v: self.on_color_slider_changed('brightness', v, 0, 200))
        self.contrast_slider.valueChanged.connect(lambda v: self.on_color_slider_changed('contrast', v, 0, 200))
        self.saturation_slider.valueChanged.connect(lambda v: self.on_color_slider_changed('saturation', v, 0, 200))
        self.sharpness_slider.valueChanged.connect(lambda v: self.on_color_slider_changed('sharpness', v, -100, 100))
        self.shadows_slider.valueChanged.connect(lambda v: self.on_color_slider_changed('shadows', v, -100, 100))
        self.temperature_slider.valueChanged.connect(self.on_temperature_changed)
        self.tint_slider.valueChanged.connect(self.on_tint_changed)
        
        # Кнопка сброса параметров цветокоррекции
        self.reset_color_btn.clicked.connect(self.reset_color_correction)
    
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
            # Сбрасываем метаданные перед загрузкой нового файла
            self.video_metadata_label.setVisible(False)
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
            
            # Обновляем метаданные видео
            self._update_video_metadata(video_path)
            
            # Обновляем размер виджета в соответствии с текущим соотношением сторон
            self._update_video_widget_size()
            
            # Обновляем многосегментный режим
            if hasattr(self, 'segments_widget'):
                self.segments_widget.set_video_duration(duration)
                # Инициализируем проект, если его еще нет
                if not self.current_project:
                    output_dir = DEFAULT_OUTPUT_DIR / "segments"
                    output_dir.mkdir(parents=True, exist_ok=True)
                    self.current_project = Project(
                        input_file=video_path,
                        output_dir=output_dir,
                        project_name=video_path.stem
                    )
                    self.segments_widget.set_project(self.current_project)
            
            # Автоматически загружаем видео для предпросмотра
            if self.player and self.video_widget:
                # Небольшая задержка, чтобы убедиться, что виджет готов
                QTimer.singleShot(200, lambda: self._auto_preview(video_path, duration))
        else:
            # Скрываем метаданные, если не удалось загрузить видео
            self.video_metadata_label.setVisible(False)
            QMessageBox.warning(self, "Ошибка", "Не удалось загрузить информацию о видео")
    
    def _auto_preview(self, video_path: Path, duration: float):
        """Автоматический предпросмотр видео при загрузке."""
        if self.player and self.video_widget:
            # Сбрасываем ограничения диапазона при автоматической загрузке
            self.preview_start_time = None
            self.preview_end_time = None
            
            # Сбрасываем скорость на нормальную
            self.speed_slider.setValue(10)  # 1.0x
            if self.player:
                self.player.set_rate(1.0)
            
            # Применяем соотношение сторон в плеере
            if self.video_info:
                width = self.video_info.get("width", 1920)
                height = self.video_info.get("height", 1080)
                fps = self.video_info.get("fps", 30.0)
                aspect_ratio = self.aspect_ratio_combo.currentText()
                # Сохраняем размеры и FPS в плеере для использования в play_file
                self.player.video_width = width
                self.player.video_height = height
                self.player.video_fps = fps
                self.player.aspect_ratio = aspect_ratio
            
            # Загружаем видео без ограничения по времени (без автоматического воспроизведения)
            self.player.play_file(video_path, 0.0, 0.0, auto_play=False)  # 0.0 означает до конца
            
            # Применяем текущие настройки цветокоррекции после загрузки
            QTimer.singleShot(300, lambda: self._apply_color_correction_to_preview())
            
            # Настраиваем слайдер
            self.timeline_slider.setMaximum(int(duration * 1000))  # в миллисекундах
            self.timeline_slider.setEnabled(True)
            # Обновляем метку времени
            length_str = seconds_to_timecode(duration)
            self.time_label.setText(f"00:00:00.000 / {length_str}")
            # Устанавливаем кнопку в состояние "Воспроизвести" (видео уже загружено, но не играет)
            # и запускаем обновление позиции
            QTimer.singleShot(300, lambda: self._setup_after_load())
    
    def _apply_color_correction_to_preview(self):
        """Применяет текущие настройки цветокоррекции к предпросмотру."""
        if not self.player:
            return
        
        brightness = (self.brightness_slider.value() - 100) / 100.0
        contrast = self.contrast_slider.value() / 100.0
        saturation = self.saturation_slider.value() / 100.0
        sharpness = self.sharpness_slider.value() / 100.0
        shadows = self.shadows_slider.value() / 100.0
        temperature = self.temperature_slider.value()
        tint = self.tint_slider.value()
        
        self.player.set_color_correction(
            brightness=brightness,
            contrast=contrast,
            saturation=saturation,
            sharpness=sharpness,
            shadows=shadows,
            temperature=temperature,
            tint=tint
        )
    
    def _setup_after_load(self):
        """Настраивает UI после загрузки видео (без автоматического воспроизведения)."""
        if self.player:
            # Убеждаемся, что видео на паузе (play_file не запускает воспроизведение)
            if self.player.is_playing():
                self.player.pause()
            self.play_pause_btn.setText("▶ Воспроизвести")
            # Начинаем обновление позиции
            self.position_timer.start(100)
    
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
        if self.player and self.player.is_playing():
            current_time = self.player.get_time()
            self.start_time_edit.setText(seconds_to_timecode(current_time))
    
    def set_end_time(self):
        """Устанавливает время окончания из текущей позиции плеера."""
        if self.player and self.player.is_playing():
            current_time = self.player.get_time()
            self.end_time_edit.setText(seconds_to_timecode(current_time))
    
    def preview_video(self):
        """Предпросмотр видео."""
        if not self.player:
            QMessageBox.warning(self, "Ошибка", "Плеер не инициализирован")
            return
        
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
        
        # Сохраняем диапазон предпросмотра
        self.preview_start_time = start_time
        self.preview_end_time = end_time
        
        # Применяем соотношение сторон в плеере перед воспроизведением
        if self.video_info:
            width = self.video_info.get("width", 1920)
            height = self.video_info.get("height", 1080)
            fps = self.video_info.get("fps", 30.0)
            aspect_ratio = self.aspect_ratio_combo.currentText()
            # Сохраняем размеры и FPS в плеере для использования в play_file
            self.player.video_width = width
            self.player.video_height = height
            self.player.video_fps = fps
            self.player.aspect_ratio = aspect_ratio
        
        # Загружаем видео с указанным диапазоном
        self.player.play_file(Path(input_path), start_time, end_time)
        
        # Применяем текущие настройки цветокоррекции после загрузки
        QTimer.singleShot(300, lambda: self._apply_color_correction_to_preview())
        
        # Настраиваем слайдер для предпросмотра
        if self.video_info:
            duration = self.video_info.get("duration", 0)
            self.timeline_slider.setMaximum(int(duration * 1000))
            # Устанавливаем слайдер на начало диапазона
            self.timeline_slider.setValue(int(start_time * 1000))
        self.timeline_slider.setEnabled(True)
        self.position_timer.start(100)
        self.log(f"Предпросмотр диапазона: {start_time_str} - {end_time_str}")
    
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
        
        # Получаем текущую скорость из слайдера
        speed_value = self.speed_slider.value()
        speed = speed_value / 10.0  # Конвертируем из значения слайдера (5-30) в скорость (0.5-3.0)
        
        # Получаем соотношение сторон
        aspect_ratio = self.aspect_ratio_combo.currentText()
        
        # Получаем параметры цветокоррекции
        brightness = (self.brightness_slider.value() - 100) / 100.0
        contrast = self.contrast_slider.value() / 100.0
        saturation = self.saturation_slider.value() / 100.0
        sharpness = self.sharpness_slider.value() / 100.0
        shadows = self.shadows_slider.value() / 100.0
        temperature = self.temperature_slider.value()
        tint = self.tint_slider.value()
        
        # Создание задачи
        job = Job(
            input_file=Path(input_path),
            output_file=Path(output_path),
            start_time=start_time,
            end_time=end_time,
            speed=speed,
            aspect_ratio=aspect_ratio,
            brightness=brightness,
            contrast=contrast,
            saturation=saturation,
            sharpness=sharpness,
            shadows=shadows,
            temperature=temperature,
            tint=tint,
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
    
    def toggle_play_pause(self):
        """Переключение между воспроизведением и паузой."""
        if not self.player:
            return
        
        if self.player.is_playing():
            self.player.pause()
            self.play_pause_btn.setText("▶ Воспроизвести")
            # Не останавливаем таймер, чтобы позиция продолжала обновляться
        else:
            current_time = self.player.get_time()
            
            # Если есть ограничение диапазона предпросмотра, проверяем его
            if self.preview_end_time is not None and current_time >= self.preview_end_time:
                # Если достигли конца диапазона, начинаем с начала диапазона
                start = self.preview_start_time if self.preview_start_time is not None else 0.0
                self.player.set_time(start)
                self.timeline_slider.setValue(int(start * 1000))
            else:
                # Проверяем, не достиг ли конец видео
                length = self.player.get_length()
                if length > 0 and current_time >= length - 0.1:
                    # Если достигли конца, начинаем с начала
                    start = self.preview_start_time if self.preview_start_time is not None else 0.0
                    self.player.set_time(start)
                    self.timeline_slider.setValue(int(start * 1000))
            
            self.player.play()
            self.play_pause_btn.setText("⏸ Пауза")
            if not self.position_timer.isActive():
                self.position_timer.start(100)
    
    def stop_video_playback(self):
        """Остановка воспроизведения видео."""
        if not self.player:
            return
        
        self.player.stop()
        self.play_pause_btn.setText("▶ Воспроизвести")
        self.position_timer.stop()
        self.timeline_slider.setValue(0)
        self.time_label.setText("00:00:00.000 / " + self.time_label.text().split(" / ")[-1])
    
    def on_frame_back_clicked(self):
        """Обработчик нажатия кнопки перемотки на кадр назад."""
        if self.player:
            self.player.previous_frame()
            # Обновляем позицию слайдера и метку времени
            QTimer.singleShot(50, self.update_video_position)
    
    def on_frame_forward_clicked(self):
        """Обработчик нажатия кнопки перемотки на кадр вперед."""
        if self.player:
            self.player.next_frame()
            # Обновляем позицию слайдера и метку времени
            QTimer.singleShot(50, self.update_video_position)
    
    def update_video_position(self):
        """Обновление позиции слайдера во время воспроизведения."""
        if not self.player or self.is_seeking:
            return
        
        try:
            current_time = self.player.get_time()
            length = self.player.get_length()
            
            # Если есть ограничение диапазона предпросмотра, проверяем его
            if self.preview_end_time is not None and current_time >= self.preview_end_time:
                self.player.stop()
                self.play_pause_btn.setText("▶ Воспроизвести")
                self.position_timer.stop()
                # Устанавливаем слайдер на конец диапазона
                if self.preview_end_time is not None:
                    self.timeline_slider.setValue(int(self.preview_end_time * 1000))
                return
            
            if length > 0:
                # Обновляем слайдер
                self.timeline_slider.setValue(int(current_time * 1000))
                
                # Обновляем метку времени
                current_str = seconds_to_timecode(current_time)
                
                # Если есть ограничение диапазона, показываем его
                if self.preview_start_time is not None and self.preview_end_time is not None:
                    length_str = seconds_to_timecode(self.preview_end_time)
                    # Показываем прогресс относительно диапазона
                    range_str = f"{seconds_to_timecode(self.preview_start_time)} - {length_str}"
                    self.time_label.setText(f"{current_str} / {range_str}")
                else:
                    length_str = seconds_to_timecode(length)
                    self.time_label.setText(f"{current_str} / {length_str}")
            
            # Проверяем, не достиг ли конец видео (если нет ограничения диапазона)
            if (self.preview_end_time is None and 
                not self.player.is_playing() and 
                length > 0 and 
                current_time >= length - 0.1):
                self.play_pause_btn.setText("▶ Воспроизвести")
                self.position_timer.stop()
        except Exception as e:
            logger.error(f"Ошибка обновления позиции: {e}")
    
    def on_slider_pressed(self):
        """Обработчик нажатия на слайдер."""
        self.is_seeking = True
        if self.player and self.player.is_playing():
            self.player.pause()
    
    def on_slider_released(self):
        """Обработчик отпускания слайдера."""
        if not self.player:
            self.is_seeking = False
            return
        
        # Получаем позицию из слайдера
        position_ms = self.timeline_slider.value()
        position_seconds = position_ms / 1000.0
        
        # Если есть ограничение диапазона предпросмотра, ограничиваем позицию
        if self.preview_start_time is not None and position_seconds < self.preview_start_time:
            position_seconds = self.preview_start_time
            self.timeline_slider.setValue(int(position_seconds * 1000))
        if self.preview_end_time is not None and position_seconds > self.preview_end_time:
            position_seconds = self.preview_end_time
            self.timeline_slider.setValue(int(position_seconds * 1000))
        
        # Устанавливаем позицию в плеере
        was_playing = self.player.is_playing()
        
        # Если используется временный файл предпросмотра, нужно пересчитать позицию относительно оригинального файла
        # Но для простоты просто устанавливаем позицию напрямую
        try:
            self.player.set_time(position_seconds)
        except Exception as e:
            logger.error(f"Ошибка установки времени: {e}")
        
        # Если было воспроизведение, продолжаем (но только если не вышли за пределы диапазона)
        if was_playing:
            if (self.preview_end_time is None or position_seconds < self.preview_end_time):
                # Используем небольшую задержку перед возобновлением воспроизведения
                QTimer.singleShot(100, lambda: self.player.play() if self.player else None)
                self.play_pause_btn.setText("⏸ Пауза")
            else:
                self.player.stop()
                self.play_pause_btn.setText("▶ Воспроизвести")
        else:
            self.play_pause_btn.setText("▶ Воспроизвести")
        
        self.is_seeking = False
    
    def on_slider_value_changed(self, value):
        """Обработчик изменения значения слайдера."""
        if not self.player or not self.is_seeking:
            return
        
        # Обновляем метку времени во время перемотки
        position_seconds = value / 1000.0
        current_str = seconds_to_timecode(position_seconds)
        
        if self.video_info:
            duration = self.video_info.get("duration", 0)
            length_str = seconds_to_timecode(duration)
            self.time_label.setText(f"{current_str} / {length_str}")
        else:
            length = self.player.get_length()
            if length > 0:
                length_str = seconds_to_timecode(length)
                self.time_label.setText(f"{current_str} / {length_str}")
    
    def on_speed_changed(self, value: int):
        """Обработчик изменения скорости воспроизведения."""
        # Конвертируем значение слайдера (5-30) в скорость (0.5-3.0)
        # 5 = 0.5x, 10 = 1.0x, 15 = 1.5x, 20 = 2.0x, 25 = 2.5x, 30 = 3.0x
        speed = value / 10.0
        self.speed_value_label.setText(f"{speed:.1f}x")
        
        # Устанавливаем скорость в плеере
        if self.player:
            self.player.set_rate(speed)
    
    def on_color_slider_changed(self, param_name: str, value: int, min_val: int, max_val: int):
        """Обработчик изменения слайдеров цветокоррекции (кроме температуры и тона)."""
        # Конвертируем значение слайдера в реальное значение
        if param_name == 'brightness':
            # Для яркости: 0-200 -> -1.0 до 1.0, где 100 = 0.0
            real_value = (value - 100) / 100.0
            label = getattr(self, f"{param_name}_value_label")
            label.setText(f"{real_value:.2f}")
        elif param_name in ['sharpness', 'shadows']:
            # Для параметров от -1.0 до 1.0
            real_value = value / 100.0
            label = getattr(self, f"{param_name}_value_label")
            label.setText(f"{real_value:.2f}")
        elif param_name in ['contrast', 'saturation']:
            # Для параметров от 0.0 до 2.0
            real_value = value / 100.0
            label = getattr(self, f"{param_name}_value_label")
            label.setText(f"{real_value:.2f}")
        
        # Применяем цветокоррекцию к предпросмотру
        if self.player:
            brightness = (self.brightness_slider.value() - 100) / 100.0
            contrast = self.contrast_slider.value() / 100.0
            saturation = self.saturation_slider.value() / 100.0
            sharpness = self.sharpness_slider.value() / 100.0
            shadows = self.shadows_slider.value() / 100.0
            temperature = self.temperature_slider.value()
            tint = self.tint_slider.value()
            
            self.player.set_color_correction(
                brightness=brightness,
                contrast=contrast,
                saturation=saturation,
                sharpness=sharpness,
                shadows=shadows,
                temperature=temperature,
                tint=tint
            )
    
    def on_temperature_changed(self, value: int):
        """Обработчик изменения температуры."""
        self.temperature_value_label.setText(str(value))
        
        # Применяем цветокоррекцию к предпросмотру
        if self.player:
            brightness = (self.brightness_slider.value() - 100) / 100.0
            contrast = self.contrast_slider.value() / 100.0
            saturation = self.saturation_slider.value() / 100.0
            sharpness = self.sharpness_slider.value() / 100.0
            shadows = self.shadows_slider.value() / 100.0
            temperature = value
            tint = self.tint_slider.value()
            
            self.player.set_color_correction(
                brightness=brightness,
                contrast=contrast,
                saturation=saturation,
                sharpness=sharpness,
                shadows=shadows,
                temperature=temperature,
                tint=tint
            )
    
    def on_tint_changed(self, value: int):
        """Обработчик изменения тона."""
        self.tint_value_label.setText(str(value))
        
        # Применяем цветокоррекцию к предпросмотру
        if self.player:
            brightness = (self.brightness_slider.value() - 100) / 100.0
            contrast = self.contrast_slider.value() / 100.0
            saturation = self.saturation_slider.value() / 100.0
            sharpness = self.sharpness_slider.value() / 100.0
            shadows = self.shadows_slider.value() / 100.0
            temperature = self.temperature_slider.value()
            tint = value
            
            self.player.set_color_correction(
                brightness=brightness,
                contrast=contrast,
                saturation=saturation,
                sharpness=sharpness,
                shadows=shadows,
                temperature=temperature,
                tint=tint
            )
    
    def reset_color_correction(self):
        """Сбрасывает все параметры цветокоррекции к значениям по умолчанию."""
        # Временно отключаем сигналы, чтобы избежать множественных обновлений
        self.brightness_slider.blockSignals(True)
        self.contrast_slider.blockSignals(True)
        self.saturation_slider.blockSignals(True)
        self.sharpness_slider.blockSignals(True)
        self.shadows_slider.blockSignals(True)
        self.temperature_slider.blockSignals(True)
        self.tint_slider.blockSignals(True)
        
        # Сбрасываем все слайдеры к значениям по умолчанию
        self.brightness_slider.setValue(100)  # 0.0
        self.contrast_slider.setValue(100)  # 1.0
        self.saturation_slider.setValue(100)  # 1.0
        self.sharpness_slider.setValue(0)  # 0.0
        self.shadows_slider.setValue(0)  # 0.0
        self.temperature_slider.setValue(0)  # 0
        self.tint_slider.setValue(0)  # 0
        
        # Обновляем метки значений
        self.brightness_value_label.setText("0.0")
        self.contrast_value_label.setText("1.0")
        self.saturation_value_label.setText("1.0")
        self.sharpness_value_label.setText("0.0")
        self.shadows_value_label.setText("0.0")
        self.temperature_value_label.setText("0")
        self.tint_value_label.setText("0")
        
        # Включаем сигналы обратно
        self.brightness_slider.blockSignals(False)
        self.contrast_slider.blockSignals(False)
        self.saturation_slider.blockSignals(False)
        self.sharpness_slider.blockSignals(False)
        self.shadows_slider.blockSignals(False)
        self.temperature_slider.blockSignals(False)
        self.tint_slider.blockSignals(False)
        
        # Применяем сброс к предпросмотру (если видео загружено)
        if self.player:
            self.player.set_color_correction(
                brightness=0.0,
                contrast=1.0,
                saturation=1.0,
                sharpness=0.0,
                shadows=0.0,
                temperature=0.0,
                tint=0.0
            )
        
        self.log("Параметры цветокоррекции сброшены к значениям по умолчанию")
    
    def on_aspect_ratio_changed(self, aspect_ratio: str):
        """Обработчик изменения соотношения сторон."""
        # Обновляем размер виджета видео для предпросмотра
        self._update_video_widget_size(aspect_ratio)
        
        # Применяем соотношение сторон в плеере для предпросмотра
        if self.player and self.video_info:
            width = self.video_info.get("width", 1920)
            height = self.video_info.get("height", 1080)
            # Сохраняем размеры и соотношение сторон в плеере
            self.player.video_width = width
            self.player.video_height = height
            self.player.aspect_ratio = aspect_ratio
            
            # Если видео уже воспроизводится, перезагружаем его с новыми фильтрами
            if self.player.current_file and self.player.current_file.exists():
                was_playing = self.player.is_playing()
                current_time = self.player.get_time()
                self.player.play_file(self.player.current_file, current_time, 0.0)
                if not was_playing:
                    self.player.pause()
    
    def _update_video_metadata(self, video_path: Path):
        """Обновляет отображение метаданных видео."""
        if not video_path.exists():
            self.video_metadata_label.setVisible(False)
            return
        
        try:
            # Получаем размер файла
            file_size = video_path.stat().st_size
            # Преобразуем размер в читаемый формат
            if file_size < 1024:
                size_str = f"{file_size} B"
            elif file_size < 1024 * 1024:
                size_str = f"{file_size / 1024:.2f} KB"
            elif file_size < 1024 * 1024 * 1024:
                size_str = f"{file_size / (1024 * 1024):.2f} MB"
            else:
                size_str = f"{file_size / (1024 * 1024 * 1024):.2f} GB"
            
            # Получаем название файла
            file_name = video_path.name
            
            # Получаем формат (расширение)
            file_format = video_path.suffix.upper().lstrip('.') or "Unknown"
            
            # Получаем длительность
            duration = self.video_info.get("duration", 0) if self.video_info else 0
            duration_str = seconds_to_timecode(duration) if duration > 0 else "N/A"

            # Получаем разрешение
            width = self.video_info.get("width", 0) if self.video_info else 0
            height = self.video_info.get("height", 0) if self.video_info else 0
            try:
                width = int(width)
                height = int(height)
            except (TypeError, ValueError):
                width = 0
                height = 0

            resolution_str = f"{width}x{height}" if width > 0 and height > 0 else "N/A"
            
            # Формируем строку метаданных
            metadata_text = (
                f"📹 {file_name} | 💾 {size_str} | 📐 {resolution_str} | 🎬 {file_format} | ⏱ {duration_str}"
            )
            self.video_metadata_label.setText(metadata_text)
            self.video_metadata_label.setVisible(True)
        except Exception as e:
            logger.warning(f"Не удалось обновить метаданные видео: {e}")
            self.video_metadata_label.setVisible(False)
    
    def _update_video_widget_size(self, aspect_ratio: str = None):
        """Обновляет минимальный размер виджета видео в соответствии с соотношением сторон."""
        if not self.video_widget:
            return
        
        if aspect_ratio is None:
            aspect_ratio = self.aspect_ratio_combo.currentText()
        
        # Устанавливаем только минимальный размер для сохранения соотношения сторон
        # Виджет может расширяться, но сохраняет минимальное соотношение сторон
        if aspect_ratio == "9:16":
            # Вертикальное видео - минимальный размер
            min_width = 180
            min_height = 320
        else:  # 16:9
            # Горизонтальное видео - минимальный размер
            min_width = 320
            min_height = 180
        
        self.video_widget.setMinimumSize(min_width, min_height)
        # НЕ устанавливаем максимальный размер - виджет может расширяться
        # Устанавливаем стиль для масштабирования содержимого
        self.video_widget.setStyleSheet("background-color: black;")
        # Обновляем виджет, чтобы применить изменения
        self.video_widget.update()
    
    # Методы для многосегментного режима
    def segments_set_in(self):
        """Устанавливает метку In (начало сегмента)."""
        if self.player:
            current_time = self.player.get_time()
            self.temp_in_time = current_time
            # Обновляем визуализацию метки In на временной шкале
            if hasattr(self, 'segments_widget'):
                self.segments_widget.timeline_widget.set_in_marker(current_time)
                # Обновляем текст кнопки для визуальной индикации
                self.segments_widget.set_in_btn.setText(f"I - Set In ({seconds_to_timecode(current_time)})")
            self.log(f"Установлена метка In: {seconds_to_timecode(current_time)}")
    
    def segments_set_out(self):
        """Устанавливает метку Out (конец сегмента)."""
        if self.player:
            current_time = self.player.get_time()
            self.temp_out_time = current_time
            # Обновляем визуализацию метки Out на временной шкале
            if hasattr(self, 'segments_widget'):
                self.segments_widget.timeline_widget.set_out_marker(current_time)
                # Обновляем текст кнопки для визуальной индикации
                self.segments_widget.set_out_btn.setText(f"O - Set Out ({seconds_to_timecode(current_time)})")
            self.log(f"Установлена метка Out: {seconds_to_timecode(current_time)}")
    
    def segments_add_clip(self):
        """Добавляет новый сегмент из установленных меток In/Out."""
        if not self.current_project:
            # Создаем новый проект, если его нет
            input_path = self.input_file_edit.text()
            if not input_path:
                QMessageBox.warning(self, "Ошибка", "Сначала выберите входной видео файл")
                return
            
            output_dir = DEFAULT_OUTPUT_DIR / "segments"
            output_dir.mkdir(parents=True, exist_ok=True)
            self.current_project = Project(
                input_file=Path(input_path),
                output_dir=output_dir,
                project_name="New Project"
            )
            if hasattr(self, 'segments_widget'):
                self.segments_widget.set_project(self.current_project)
        
        if self.temp_in_time is None or self.temp_out_time is None:
            QMessageBox.warning(self, "Ошибка", "Установите метки In и Out (клавиши I и O)")
            return
        
        start_time = min(self.temp_in_time, self.temp_out_time)
        end_time = max(self.temp_in_time, self.temp_out_time)
        
        # Создаем новый сегмент с текущими настройками из обычного режима
        segment = Segment(
            start_time=start_time,
            end_time=end_time,
            name=f"Segment {len(self.current_project.segments) + 1}",
            enabled=True,
            encoding_profile=self.encoding_profile_combo.currentText(),
            speed=self.speed_slider.value() / 10.0,
            aspect_ratio=self.aspect_ratio_combo.currentText(),
            brightness=(self.brightness_slider.value() - 100) / 100.0,
            contrast=self.contrast_slider.value() / 100.0,
            saturation=self.saturation_slider.value() / 100.0,
            sharpness=self.sharpness_slider.value() / 100.0,
            shadows=self.shadows_slider.value() / 100.0,
            temperature=self.temperature_slider.value(),
            tint=self.tint_slider.value()
        )
        
        if self.current_project.add_segment(segment):
            self.segments_widget.update_segments_table()
            self.log(f"Добавлен сегмент: {seconds_to_timecode(start_time)} - {seconds_to_timecode(end_time)}")
            # Сбрасываем метки и обновляем визуализацию
            self.temp_in_time = None
            self.temp_out_time = None
            if hasattr(self, 'segments_widget'):
                self.segments_widget.timeline_widget.set_in_marker(None)
                self.segments_widget.timeline_widget.set_out_marker(None)
                # Сбрасываем текст кнопок
                self.segments_widget.set_in_btn.setText("I - Set In")
                self.segments_widget.set_out_btn.setText("O - Set Out")
        else:
            QMessageBox.warning(self, "Ошибка", "Не удалось добавить сегмент")
    
    def segments_delete(self):
        """Удаляет выбранный сегмент."""
        if not self.current_project:
            return
        
        selected_row = self.segments_widget.segments_table.currentRow()
        if selected_row >= 0:
            if self.current_project.remove_segment(selected_row):
                self.segments_widget.update_segments_table()
                self.log(f"Удален сегмент {selected_row + 1}")
    
    def segments_duplicate(self):
        """Дублирует выбранный сегмент."""
        if not self.current_project:
            return
        
        selected_row = self.segments_widget.segments_table.currentRow()
        if 0 <= selected_row < len(self.current_project.segments):
            original = self.current_project.segments[selected_row]
            # Создаем копию сегмента
            from copy import deepcopy
            duplicate = deepcopy(original)
            duplicate.name = f"{original.name} (копия)"
            if self.current_project.add_segment(duplicate):
                self.segments_widget.update_segments_table()
                self.log(f"Дублирован сегмент {selected_row + 1}")
    
    def segments_on_click(self, index: int):
        """Обработчик клика по сегменту на временной шкале."""
        if self.current_project and 0 <= index < len(self.current_project.segments):
            segment = self.current_project.segments[index]
            self.segments_widget.segments_table.selectRow(index)
            # Перематываем к началу сегмента
            if self.player:
                self.player.set_time(segment.start_time)
    
    def segments_update_timeline(self):
        """Обновляет временную шкалу сегментов при изменении времени воспроизведения."""
        if hasattr(self, 'segments_widget') and self.player:
            current_time = self.player.get_time()
            self.segments_widget.set_current_time(current_time)
    
    def segments_save_project(self):
        """Сохраняет проект в JSON файл."""
        if not self.current_project:
            QMessageBox.warning(self, "Ошибка", "Нет активного проекта для сохранения")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить проект",
            "",
            "JSON Files (*.json);;All Files (*)"
        )
        
        if file_path:
            if self.current_project.save_to_file(Path(file_path)):
                self.log(f"Проект сохранен: {file_path}")
                QMessageBox.information(self, "Успех", "Проект успешно сохранен")
            else:
                QMessageBox.critical(self, "Ошибка", "Не удалось сохранить проект")
    
    def segments_load_project(self):
        """Загружает проект из JSON файла."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Загрузить проект",
            "",
            "JSON Files (*.json);;All Files (*)"
        )
        
        if file_path:
            project = Project.load_from_file(Path(file_path))
            if project:
                self.current_project = project
                # Загружаем видео файл проекта
                if project.input_file.exists():
                    self.input_file_edit.setText(str(project.input_file))
                    # Сбрасываем метаданные перед загрузкой
                    self.video_metadata_label.setVisible(False)
                    self.load_video_info(str(project.input_file))
                else:
                    QMessageBox.warning(self, "Предупреждение", 
                                      f"Входной файл проекта не найден: {project.input_file}\n"
                                      "Проект загружен, но файл необходимо выбрать вручную")
                
                # Обновляем UI
                if hasattr(self, 'segments_widget'):
                    self.segments_widget.set_project(project)
                    if self.video_info:
                        duration = self.video_info.get("duration", 0)
                        self.segments_widget.set_video_duration(duration)
                
                self.log(f"Проект загружен: {file_path}")
                QMessageBox.information(self, "Успех", "Проект успешно загружен")
            else:
                QMessageBox.critical(self, "Ошибка", "Не удалось загрузить проект")
    
    def segments_export(self):
        """Экспортирует сегменты."""
        if not self.current_project or not self.current_project.segments:
            QMessageBox.warning(self, "Ошибка", "Нет сегментов для экспорта")
            return
        
        enabled_segments = self.current_project.get_enabled_segments()
        if not enabled_segments:
            QMessageBox.warning(self, "Ошибка", "Нет включенных сегментов для экспорта")
            return
        
        # Получаем настройки экспорта
        export_mode = self.segments_widget.export_mode_combo.currentText()
        export_method = self.segments_widget.export_method_combo.currentText()
        
        fast_mode = "Быстро" in export_method
        split_mode = "Отдельные" in export_mode
        
        from app.segment_worker import SegmentWorker
        from PySide6.QtCore import QThread, Signal
        
        class SegmentExportThread(QThread):
            """Поток для экспорта сегментов."""
            progress_updated = Signal(int, int, str)  # current, total, message для split режима
            progress_updated_float = Signal(float, str)  # progress (0.0-1.0), message для concat режима
            finished_signal = Signal(bool, str)
            
            def __init__(self, project: Project, fast_mode: bool, split_mode: bool):
                super().__init__()
                self.project = project
                self.fast_mode = fast_mode
                self.split_mode = split_mode
                self.worker = SegmentWorker(max_workers=4)
            
            def run(self):
                try:
                    if self.split_mode:
                        # Экспорт отдельных файлов
                        if self.fast_mode:
                            output_files = self.worker.export_segments_fast(
                                self.project.input_file,
                                self.project.segments,
                                self.project.output_dir,
                                progress_callback=lambda c, t, m: self.progress_updated.emit(c, t, m)
                            )
                        else:
                            output_files = self.worker.export_segments_accurate(
                                self.project.input_file,
                                self.project.segments,
                                self.project.output_dir,
                                progress_callback=lambda c, t, m: self.progress_updated.emit(c, t, m)
                            )
                        
                        if output_files:
                            self.finished_signal.emit(True, f"Экспортировано {len(output_files)} файлов")
                        else:
                            self.finished_signal.emit(False, "Ошибка экспорта сегментов")
                    else:
                        # Экспорт склейки
                        output_file = self.project.output_dir / "concatenated.mp4"
                        success = self.worker.export_concat(
                            self.project.input_file,
                            self.project.segments,
                            output_file,
                            fast_mode=self.fast_mode,
                            progress_callback=lambda p, m: self.progress_updated_float.emit(p, m)
                        )
                        
                        if success:
                            self.finished_signal.emit(True, f"Склейка завершена: {output_file}")
                        else:
                            self.finished_signal.emit(False, "Ошибка склейки сегментов")
                except Exception as e:
                    self.finished_signal.emit(False, f"Ошибка: {str(e)}")
        
        # Выбор директории для экспорта (если режим Split)
        if split_mode:
            output_dir = QFileDialog.getExistingDirectory(
                self,
                "Выберите директорию для экспорта",
                str(self.current_project.output_dir)
            )
            if output_dir:
                self.current_project.output_dir = Path(output_dir)
            else:
                return
        else:
            # Режим склейки - выбираем выходной файл
            output_file, _ = QFileDialog.getSaveFileName(
                self,
                "Сохранить склеенное видео",
                str(self.current_project.output_dir / "concatenated.mp4"),
                "Video Files (*.mp4);;All Files (*)"
            )
            if output_file:
                self.current_project.output_dir = Path(output_file).parent
            else:
                return
        
        # Запускаем экспорт в отдельном потоке
        self.segment_export_thread = SegmentExportThread(
            self.current_project,
            fast_mode,
            split_mode
        )
        
        # Подключаем сигналы для прогресса
        def on_progress_updated(current: int, total: int, message: str):
            """Обновляет прогресс для split режима."""
            if hasattr(self, 'segments_widget'):
                self.segments_widget.set_export_progress(current, total, message)
            # Также обновляем основной прогресс-бар для совместимости
            if total > 0:
                progress_percent = int((current / total) * 100)
                self.progress_bar.setValue(progress_percent)
        
        def on_progress_updated_float(progress: float, message: str):
            """Обновляет прогресс для concat режима."""
            if hasattr(self, 'segments_widget'):
                progress_percent = int(progress * 100)
                self.segments_widget.export_progress_bar.setValue(progress_percent)
                if message:
                    self.segments_widget.export_status_label.setText(f"{message} ({progress_percent}%)")
                else:
                    self.segments_widget.export_status_label.setText(f"Прогресс: {progress_percent}%")
            # Также обновляем основной прогресс-бар
            self.progress_bar.setValue(int(progress * 100))
        
        self.segment_export_thread.progress_updated.connect(on_progress_updated)
        self.segment_export_thread.progress_updated_float.connect(on_progress_updated_float)
        self.segment_export_thread.finished_signal.connect(
            lambda success, msg: self.on_segment_export_finished(success, msg)
        )
        
        # Показываем прогресс-бар в виджете сегментов
        if hasattr(self, 'segments_widget'):
            self.segments_widget.show_export_progress(True)
            self.segments_widget.export_btn.setEnabled(False)  # Отключаем кнопку во время экспорта
        
        self.process_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.log(f"Начало экспорта: {export_mode}, метод: {export_method}")
        self.segment_export_thread.start()
    
    def on_segment_export_finished(self, success: bool, message: str):
        """Обработчик завершения экспорта сегментов."""
        # Скрываем прогресс-бар и включаем кнопку экспорта
        if hasattr(self, 'segments_widget'):
            self.segments_widget.show_export_progress(False)
            self.segments_widget.export_btn.setEnabled(True)
        
        self.process_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        
        if success:
            self.progress_bar.setValue(100)
            QMessageBox.information(self, "Успех", message)
        else:
            self.progress_bar.setValue(0)
            QMessageBox.critical(self, "Ошибка", message)
        
        self.log(message)

