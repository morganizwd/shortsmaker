"""
UI для многосегментного режима: таблица сегментов, визуализация на временной шкале, управление.
"""

from pathlib import Path
from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QGroupBox, QLabel, QComboBox, QCheckBox, QLineEdit, QFileDialog,
    QMessageBox, QSlider, QAbstractItemView, QProgressBar
)
from PySide6.QtCore import Qt, Signal, QTimer, QRect, QPoint
from PySide6.QtGui import QShortcut, QKeySequence, QColor, QPainter, QPen, QBrush, QPolygon
from app.models import Segment, Project
from app.utils.timecode import seconds_to_timecode, timecode_to_seconds
from app.utils.logger import get_logger
from app.config import ENCODING_PROFILES, DEFAULT_OUTPUT_DIR

logger = get_logger(__name__)


class SegmentsTimelineWidget(QWidget):
    """Виджет для визуализации сегментов на временной шкале."""
    
    segment_clicked = Signal(int)  # Сигнал при клике на сегмент (index)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.segments: list[Segment] = []
        self.video_duration: float = 0.0
        self.current_time: float = 0.0
        self.selected_index: int = -1
        self.in_marker: Optional[float] = None  # Метка In (начало сегмента)
        self.out_marker: Optional[float] = None  # Метка Out (конец сегмента)
        self.setMinimumHeight(120)  # Увеличиваем для меток In/Out и текста
        self.setMaximumHeight(160)
    
    def set_segments(self, segments: list[Segment]):
        """Устанавливает список сегментов для отображения."""
        self.segments = segments
        self.update()
    
    def set_video_duration(self, duration: float):
        """Устанавливает длительность видео."""
        self.video_duration = duration
        self.update()
    
    def set_current_time(self, time: float):
        """Устанавливает текущее время воспроизведения."""
        self.current_time = time
        self.update()
    
    def set_selected_index(self, index: int):
        """Устанавливает выбранный сегмент."""
        self.selected_index = index
        self.update()
    
    def set_in_marker(self, time: Optional[float]):
        """Устанавливает метку In."""
        self.in_marker = time
        self.update()
    
    def set_out_marker(self, time: Optional[float]):
        """Устанавливает метку Out."""
        self.out_marker = time
        logger.debug(f"Установлена метка Out: {time}, video_duration: {self.video_duration}")
        self.update()
    
    def paintEvent(self, event):
        """Отрисовка временной шкалы с сегментами."""
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            
            rect = self.rect()
            margin = 10
            timeline_y = rect.height() // 2
            timeline_width = rect.width() - 2 * margin
            timeline_x = margin
            
            # Рисуем фон
            painter.fillRect(rect, QColor(240, 240, 240))
            
            if self.video_duration <= 0:
                painter.end()
                return
            
            # Рисуем временную шкалу (базовая линия)
            painter.setPen(QPen(QColor(100, 100, 100), 2))
            painter.drawLine(timeline_x, timeline_y, timeline_x + timeline_width, timeline_y)
        
            # Рисуем сегменты (ПЕРЕД метками In/Out, чтобы метки были поверх)
            colors = [
                QColor(65, 105, 225),   # Royal Blue
                QColor(220, 20, 60),    # Crimson
                QColor(34, 139, 34),    # Forest Green
                QColor(255, 165, 0),    # Orange
                QColor(138, 43, 226),   # Blue Violet
                QColor(255, 20, 147),   # Deep Pink
                QColor(32, 178, 170),   # Light Sea Green
                QColor(255, 140, 0),    # Dark Orange
            ]
            
            for i, segment in enumerate(self.segments):
                if not segment.enabled:
                    continue
                
                # Вычисляем позицию сегмента на шкале
                start_ratio = segment.start_time / self.video_duration if self.video_duration > 0 else 0
                end_ratio = segment.end_time / self.video_duration if self.video_duration > 0 else 0
                
                # Ограничиваем значения от 0 до 1
                start_ratio = max(0.0, min(1.0, start_ratio))
                end_ratio = max(0.0, min(1.0, end_ratio))
                
                segment_x = timeline_x + start_ratio * timeline_width
                segment_width = (end_ratio - start_ratio) * timeline_width
                
                # Выбираем цвет (циклически)
                color = colors[i % len(colors)]
                if i == self.selected_index:
                    # Выделенный сегмент - более яркий
                    color = color.lighter(120)
                
                # Рисуем прямоугольник сегмента (правильные координаты)
                segment_left = int(segment_x)
                segment_top = timeline_y - 15
                segment_width_int = max(1, int(segment_width))  # Минимальная ширина 1 пиксель
                segment_height = 30
                
                segment_rect = QRect(segment_left, segment_top, segment_width_int, segment_height)
                painter.fillRect(segment_rect, color)
                painter.setPen(QPen(QColor(0, 0, 0), 1))
                painter.drawRect(segment_rect)
                
                # Рисуем название сегмента (если есть место)
                if segment_width > 50 and segment.name:
                    painter.setPen(QPen(QColor(255, 255, 255), 1))
                    font = painter.font()
                    font.setPointSize(8)
                    painter.setFont(font)
                    painter.drawText(segment_rect, Qt.AlignCenter, segment.name)
            
            # Рисуем метку In (зеленый маркер) - ПОСЛЕ сегментов, чтобы была поверх
            if self.in_marker is not None and self.video_duration > 0:
                in_marker_clamped = max(0.0, min(self.video_duration, self.in_marker))
                in_ratio = in_marker_clamped / self.video_duration
                in_x = timeline_x + in_ratio * timeline_width
                # Рисуем зеленую вертикальную линию (толще и выше)
                painter.setPen(QPen(QColor(0, 200, 0), 4))  # Зеленый, толще
                painter.drawLine(int(in_x), timeline_y - 30, int(in_x), timeline_y + 30)
                # Рисуем треугольник вверх для метки In
                triangle_size = 10
                triangle = QPolygon([
                    QPoint(int(in_x), int(timeline_y - 30 - triangle_size)),
                    QPoint(int(in_x) - triangle_size, int(timeline_y - 30)),
                    QPoint(int(in_x) + triangle_size, int(timeline_y - 30))
                ])
                painter.setBrush(QBrush(QColor(0, 200, 0)))  # Зеленая заливка
                painter.setPen(QPen(QColor(0, 150, 0), 2))  # Более темная граница
                painter.drawPolygon(triangle)
                # Рисуем текст "IN"
                # Рисуем фон для текста для лучшей читаемости
                text_bg_rect = QRect(int(in_x) - 25, int(timeline_y - 50), 50, 18)
                painter.fillRect(text_bg_rect, QColor(0, 200, 0))
                painter.setPen(QPen(QColor(255, 255, 255), 2))  # Белый текст для лучшей видимости
                font = painter.font()
                font.setBold(True)
                font.setPointSize(11)
                painter.setFont(font)
                painter.drawText(text_bg_rect, Qt.AlignCenter, "IN")
            
            # Рисуем метку Out (красный маркер) - ПОСЛЕ сегментов, чтобы была поверх
            if self.out_marker is not None and self.video_duration > 0:
                out_marker_clamped = max(0.0, min(self.video_duration, self.out_marker))
                out_ratio = out_marker_clamped / self.video_duration
                out_x = timeline_x + out_ratio * timeline_width
                
                # Отладочное логирование
                logger.debug(f"Рисую метку Out: out_marker={self.out_marker}, out_ratio={out_ratio}, out_x={out_x}, "
                            f"timeline_y={timeline_y}, rect.height()={rect.height()}")
                
                # Рисуем красную вертикальную линию (толще и выше)
                painter.setPen(QPen(QColor(255, 0, 0), 5))  # Ярко-красный, еще толще для видимости
                painter.drawLine(int(out_x), timeline_y - 30, int(out_x), timeline_y + 30)
                # Рисуем треугольник вниз для метки Out
                triangle_size = 12
                triangle = QPolygon([
                    QPoint(int(out_x), int(timeline_y + 30 + triangle_size)),
                    QPoint(int(out_x) - triangle_size, int(timeline_y + 30)),
                    QPoint(int(out_x) + triangle_size, int(timeline_y + 30))
                ])
                painter.setBrush(QBrush(QColor(255, 0, 0)))  # Ярко-красная заливка
                painter.setPen(QPen(QColor(150, 0, 0), 2))  # Более темная граница
                painter.drawPolygon(triangle)
                # Рисуем текст "OUT"
                painter.setPen(QPen(QColor(255, 255, 255), 2))  # Белый текст для лучшей видимости
                font = painter.font()
                font.setBold(True)
                font.setPointSize(11)
                painter.setFont(font)
                # Рисуем фон для текста для лучшей читаемости
                text_bg_rect = QRect(int(out_x) - 30, int(timeline_y + 35), 60, 18)
                painter.fillRect(text_bg_rect, QColor(200, 0, 0))
                painter.drawText(text_bg_rect, Qt.AlignCenter, "OUT")
            
            # Рисуем указатель текущего времени (синяя линия) - поверх всего, но под метками In/Out
            if self.video_duration > 0:
                current_time_clamped = max(0.0, min(self.video_duration, self.current_time))
                time_ratio = current_time_clamped / self.video_duration
                time_x = timeline_x + time_ratio * timeline_width
                # Не рисуем текущее время, если оно совпадает с метками In/Out
                draw_current_time = True
                if self.in_marker is not None and abs(self.current_time - self.in_marker) < 0.1:
                    draw_current_time = False
                if self.out_marker is not None and abs(self.current_time - self.out_marker) < 0.1:
                    draw_current_time = False
                if draw_current_time:
                    painter.setPen(QPen(QColor(0, 100, 255), 2))  # Синий для текущего времени
                    painter.setBrush(QBrush())  # Без заливки
                    painter.drawLine(int(time_x), timeline_y - 22, int(time_x), timeline_y + 22)
            
            # Рисуем метки времени
            painter.setPen(QPen(QColor(80, 80, 80), 1))
            font = painter.font()
            font.setPointSize(8)
            painter.setFont(font)
            for i in range(0, 6):  # 5 меток
                ratio = i / 5.0
                label_x = timeline_x + ratio * timeline_width
                time_value = ratio * self.video_duration
                time_str = seconds_to_timecode(time_value)
                painter.drawLine(int(label_x), timeline_y - 5, int(label_x), timeline_y + 5)
                painter.drawText(int(label_x) - 30, timeline_y - 20, 60, 15, Qt.AlignCenter, time_str)
            
            # Завершаем отрисовку
            painter.end()
        except Exception as e:
            logger.error(f"Ошибка при отрисовке временной шкалы: {e}", exc_info=True)
            try:
                if 'painter' in locals():
                    painter.end()
            except:
                pass
    
    def mousePressEvent(self, event):
        """Обработка клика по временной шкале."""
        if self.video_duration <= 0:
            return
        
        margin = 10
        timeline_width = self.width() - 2 * margin
        click_x = event.position().x() - margin
        
        if 0 <= click_x <= timeline_width:
            click_ratio = click_x / timeline_width
            click_time = click_ratio * self.video_duration
            
            # Ищем сегмент, в который попал клик
            for i, segment in enumerate(self.segments):
                if segment.start_time <= click_time <= segment.end_time:
                    self.segment_clicked.emit(i)
                    self.set_selected_index(i)
                    break


class SegmentsModeWidget(QWidget):
    """Виджет для многосегментного режима."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: Optional[Project] = None
        self.current_segment_index: int = -1
        self.export_in_progress: bool = False
        self.init_ui()
    
    def init_ui(self):
        """Инициализация UI."""
        layout = QVBoxLayout(self)
        
        # Группа управления сегментами
        controls_group = QGroupBox("Управление сегментами")
        controls_layout = QVBoxLayout()
        
        # Кнопки управления
        buttons_layout = QHBoxLayout()
        self.set_in_btn = QPushButton("I - Set In")
        self.set_out_btn = QPushButton("O - Set Out")
        self.add_segment_btn = QPushButton("A - Add Clip")
        self.delete_segment_btn = QPushButton("Del - Удалить")
        self.duplicate_segment_btn = QPushButton("D - Дублировать")
        
        buttons_layout.addWidget(self.set_in_btn)
        buttons_layout.addWidget(self.set_out_btn)
        buttons_layout.addWidget(self.add_segment_btn)
        buttons_layout.addWidget(self.delete_segment_btn)
        buttons_layout.addWidget(self.duplicate_segment_btn)
        buttons_layout.addStretch()
        
        controls_layout.addLayout(buttons_layout)
        
        # Временная шкала с сегментами
        self.timeline_widget = SegmentsTimelineWidget()
        controls_layout.addWidget(self.timeline_widget)
        
        controls_group.setLayout(controls_layout)
        layout.addWidget(controls_group)
        
        # Таблица сегментов
        segments_group = QGroupBox("Список сегментов")
        segments_layout = QVBoxLayout()
        
        self.segments_table = QTableWidget()
        self.segments_table.setColumnCount(7)
        self.segments_table.setHorizontalHeaderLabels([
            "№", "Начало", "Конец", "Длительность", "Имя", "Профиль", "Включить"
        ])
        
        # Настройка таблицы
        header = self.segments_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)  # №
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Начало
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Конец
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Длительность
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)  # Имя
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Профиль
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)  # Включить
        
        self.segments_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.segments_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.segments_table.setAlternatingRowColors(True)
        
        segments_layout.addWidget(self.segments_table)
        segments_group.setLayout(segments_layout)
        layout.addWidget(segments_group)
        
        # Группа экспорта
        export_group = QGroupBox("Экспорт")
        export_layout = QVBoxLayout()
        
        # Режим экспорта
        export_mode_layout = QHBoxLayout()
        export_mode_layout.addWidget(QLabel("Режим экспорта:"))
        self.export_mode_combo = QComboBox()
        self.export_mode_combo.addItems(["Отдельные файлы (Split)", "Склейка (Concat)"])
        export_mode_layout.addWidget(self.export_mode_combo)
        export_mode_layout.addStretch()
        
        # Метод экспорта
        export_method_layout = QHBoxLayout()
        export_method_layout.addWidget(QLabel("Метод:"))
        self.export_method_combo = QComboBox()
        self.export_method_combo.addItems(["Быстро (copy)", "Точно (re-encode)"])
        export_method_layout.addWidget(self.export_method_combo)
        export_method_layout.addStretch()
        
        export_layout.addLayout(export_mode_layout)
        export_layout.addLayout(export_method_layout)
        
        # Кнопки управления проектом
        project_buttons_layout = QHBoxLayout()
        self.save_project_btn = QPushButton("Сохранить проект")
        self.load_project_btn = QPushButton("Загрузить проект")
        self.export_btn = QPushButton("Экспортировать")
        
        project_buttons_layout.addWidget(self.save_project_btn)
        project_buttons_layout.addWidget(self.load_project_btn)
        project_buttons_layout.addStretch()
        project_buttons_layout.addWidget(self.export_btn)
        
        export_layout.addLayout(project_buttons_layout)
        
        # Прогресс-бар для экспорта
        progress_layout = QVBoxLayout()
        self.export_progress_bar = QProgressBar()
        self.export_progress_bar.setMinimum(0)
        self.export_progress_bar.setMaximum(100)
        self.export_progress_bar.setValue(0)
        self.export_progress_bar.setVisible(False)  # Скрыт по умолчанию
        
        self.export_status_label = QLabel("")
        self.export_status_label.setVisible(False)  # Скрыт по умолчанию
        
        progress_layout.addWidget(self.export_progress_bar)
        progress_layout.addWidget(self.export_status_label)
        
        export_layout.addLayout(progress_layout)
        
        export_group.setLayout(export_layout)
        layout.addWidget(export_group)
        
        layout.addStretch()
    
    def setup_shortcuts(self, parent_window):
        """Настраивает горячие клавиши."""
        # I - Set In
        shortcut_i = QShortcut(QKeySequence("I"), parent_window)
        shortcut_i.activated.connect(self.set_in_btn.click)
        
        # O - Set Out
        shortcut_o = QShortcut(QKeySequence("O"), parent_window)
        shortcut_o.activated.connect(self.set_out_btn.click)
        
        # A - Add Clip
        shortcut_a = QShortcut(QKeySequence("A"), parent_window)
        shortcut_a.activated.connect(self.add_segment_btn.click)
        
        # Del - Удалить
        shortcut_del = QShortcut(QKeySequence(Qt.Key.Key_Delete), parent_window)
        shortcut_del.activated.connect(self.delete_segment_btn.click)
        
        # D - Дублировать
        shortcut_d = QShortcut(QKeySequence("D"), parent_window)
        shortcut_d.activated.connect(self.duplicate_segment_btn.click)
    
    def update_segments_table(self):
        """Обновляет таблицу сегментов."""
        if not self.project:
            self.segments_table.setRowCount(0)
            return
        
        # Отключаем сигналы для предотвращения множественных вызовов
        self.segments_table.blockSignals(True)
        
        self.segments_table.setRowCount(len(self.project.segments))
        
        for i, segment in enumerate(self.project.segments):
            # №
            self.segments_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            
            # Начало
            self.segments_table.setItem(i, 1, QTableWidgetItem(seconds_to_timecode(segment.start_time)))
            
            # Конец
            self.segments_table.setItem(i, 2, QTableWidgetItem(seconds_to_timecode(segment.end_time)))
            
            # Длительность
            self.segments_table.setItem(i, 3, QTableWidgetItem(seconds_to_timecode(segment.duration)))
            
            # Имя (редактируемое)
            name_item = QTableWidgetItem(segment.name)
            self.segments_table.setItem(i, 4, name_item)
            
            # Профиль (выпадающий список)
            profile_combo = QComboBox()
            profile_combo.addItems(list(ENCODING_PROFILES.keys()))
            profile_combo.setCurrentText(segment.encoding_profile)
            profile_combo.currentTextChanged.connect(lambda text, idx=i: self._on_profile_changed(idx, text))
            self.segments_table.setCellWidget(i, 5, profile_combo)
            
            # Включить (чекбокс)
            enabled_checkbox = QCheckBox()
            enabled_checkbox.setChecked(segment.enabled)
            enabled_checkbox.stateChanged.connect(lambda state, idx=i: self._on_enabled_changed(idx, state))
            self.segments_table.setCellWidget(i, 6, enabled_checkbox)
        
        # Включаем сигналы обратно
        self.segments_table.blockSignals(False)
        
        # Подключаем обработчик изменения имени (глобально, проверяем колонку в обработчике)
        self.segments_table.itemChanged.connect(self._on_table_item_changed)
        
        # Обновляем визуализацию
        self.timeline_widget.set_segments(self.project.segments)
    
    def _on_profile_changed(self, index: int, profile: str):
        """Обработчик изменения профиля сегмента."""
        if self.project and 0 <= index < len(self.project.segments):
            self.project.segments[index].encoding_profile = profile
    
    def _on_enabled_changed(self, index: int, state: int):
        """Обработчик изменения состояния включения сегмента."""
        if self.project and 0 <= index < len(self.project.segments):
            self.project.segments[index].enabled = (state == Qt.CheckState.Checked.value)
            self.timeline_widget.update()
    
    def _on_table_item_changed(self, item: QTableWidgetItem):
        """Обработчик изменения элемента таблицы."""
        if item.column() == 4:  # Колонка с именем
            row = item.row()
            if self.project and 0 <= row < len(self.project.segments):
                self.project.segments[row].name = item.text()
                self.timeline_widget.update()
    
    def set_project(self, project: Project):
        """Устанавливает проект для отображения."""
        self.project = project
        self.update_segments_table()
    
    def set_video_duration(self, duration: float):
        """Устанавливает длительность видео."""
        self.timeline_widget.set_video_duration(duration)
    
    def set_current_time(self, time: float):
        """Устанавливает текущее время воспроизведения."""
        self.timeline_widget.set_current_time(time)
    
    def set_export_progress(self, current: int, total: int, message: str = ""):
        """Устанавливает прогресс экспорта."""
        if total > 0:
            progress_percent = int((current / total) * 100)
            self.export_progress_bar.setValue(progress_percent)
            if message:
                self.export_status_label.setText(f"{message} ({current}/{total})")
            else:
                self.export_status_label.setText(f"Прогресс: {current}/{total} ({progress_percent}%)")
        else:
            # Для concat режима - устанавливаем просто процент
            if message:
                self.export_status_label.setText(message)
    
    def show_export_progress(self, show: bool = True):
        """Показывает или скрывает прогресс-бар экспорта."""
        self.export_progress_bar.setVisible(show)
        self.export_status_label.setVisible(show)
        if not show:
            self.export_progress_bar.setValue(0)
            self.export_status_label.setText("")
    
    def reset_export_progress(self):
        """Сбрасывает прогресс экспорта."""
        self.export_progress_bar.setValue(0)
        self.export_status_label.setText("")
        self.show_export_progress(False)

