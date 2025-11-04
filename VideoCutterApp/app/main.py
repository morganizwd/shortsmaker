"""
Точка входа приложения VideoCutterApp.
Запускает GUI интерфейс.
"""

import sys
from PySide6.QtWidgets import QApplication
from app.ui_main import MainWindow


def main():
    """Главная функция запуска приложения."""
    app = QApplication(sys.argv)
    
    # Настройка приложения
    app.setApplicationName("VideoCutterApp")
    app.setOrganizationName("VideoCutter")
    
    # Создание и отображение главного окна
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

