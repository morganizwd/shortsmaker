"""
Тесты для модуля ffprobe_utils.
"""

import unittest
from pathlib import Path
from app.ffprobe_utils import get_video_info, get_video_duration, get_video_fps


class TestFFprobeUtils(unittest.TestCase):
    """Тесты для работы с ffprobe."""
    
    def test_get_video_info_nonexistent_file(self):
        """Тест получения информации о несуществующем файле."""
        result = get_video_info(Path("nonexistent_file.mp4"))
        self.assertIsNone(result)
    
    def test_get_video_duration_nonexistent_file(self):
        """Тест получения длительности несуществующего файла."""
        result = get_video_duration(Path("nonexistent_file.mp4"))
        self.assertEqual(result, 0.0)
    
    def test_get_video_fps_nonexistent_file(self):
        """Тест получения FPS несуществующего файла."""
        result = get_video_fps(Path("nonexistent_file.mp4"))
        self.assertEqual(result, 0.0)
    
    # Примечание: Для полного тестирования нужны реальные видео файлы
    # Это можно добавить позже, используя тестовые видео файлы


if __name__ == "__main__":
    unittest.main()

