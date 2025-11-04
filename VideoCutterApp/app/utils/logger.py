"""
Логирование в файл.
"""

import logging
import sys
from pathlib import Path
from app.config import LOG_DIR, LOG_FILE, LOG_LEVEL


def get_logger(name: str) -> logging.Logger:
    """
    Получает настроенный logger.
    
    Args:
        name: Имя logger (обычно __name__)
    
    Returns:
        Настроенный logger
    """
    logger = logging.getLogger(name)
    
    # Если logger уже настроен, возвращаем его
    if logger.handlers:
        return logger
    
    # Создание директории для логов
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    # Настройка уровня логирования
    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(level)
    
    # Формат сообщений
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Обработчик для файла
    file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Обработчик для консоли
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger

