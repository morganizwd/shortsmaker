"""
Тесты для модуля timecode.
"""

import unittest
from app.utils.timecode import (
    timecode_to_seconds,
    seconds_to_timecode,
    seconds_to_frames,
    frames_to_seconds,
    frames_to_timecode,
    timecode_to_frames
)


class TestTimecode(unittest.TestCase):
    """Тесты для конвертации времени."""
    
    def test_timecode_to_seconds_hms(self):
        """Тест конвертации HH:MM:SS.mmm в секунды."""
        self.assertAlmostEqual(timecode_to_seconds("00:00:00.000"), 0.0)
        self.assertAlmostEqual(timecode_to_seconds("00:01:30.500"), 90.5)
        self.assertAlmostEqual(timecode_to_seconds("01:30:45.250"), 5445.25)
    
    def test_timecode_to_seconds_ms(self):
        """Тест конвертации MM:SS.mmm в секунды."""
        self.assertAlmostEqual(timecode_to_seconds("01:30.500"), 90.5)
        self.assertAlmostEqual(timecode_to_seconds("05:30.250"), 330.25)
    
    def test_timecode_to_seconds_seconds(self):
        """Тест конвертации SS.mmm в секунды."""
        self.assertAlmostEqual(timecode_to_seconds("90.500"), 90.5)
        self.assertAlmostEqual(timecode_to_seconds("30.250"), 30.25)
    
    def test_seconds_to_timecode_with_hours(self):
        """Тест конвертации секунд в HH:MM:SS.mmm."""
        self.assertEqual(seconds_to_timecode(0.0), "00:00:00.000")
        self.assertEqual(seconds_to_timecode(90.5), "00:01:30.500")
        self.assertEqual(seconds_to_timecode(5445.25), "01:30:45.250")
    
    def test_seconds_to_timecode_without_hours(self):
        """Тест конвертации секунд в MM:SS.mmm."""
        self.assertEqual(seconds_to_timecode(0.0, include_hours=False), "00:00.000")
        self.assertEqual(seconds_to_timecode(90.5, include_hours=False), "01:30.500")
        self.assertEqual(seconds_to_timecode(330.25, include_hours=False), "05:30.250")
    
    def test_seconds_to_frames(self):
        """Тест конвертации секунд в кадры."""
        self.assertEqual(seconds_to_frames(1.0, 30.0), 30)
        self.assertEqual(seconds_to_frames(90.5, 25.0), 2262)
    
    def test_frames_to_seconds(self):
        """Тест конвертации кадров в секунды."""
        self.assertAlmostEqual(frames_to_seconds(30, 30.0), 1.0)
        self.assertAlmostEqual(frames_to_seconds(2262, 25.0), 90.48)
    
    def test_frames_to_timecode(self):
        """Тест конвертации кадров в timecode."""
        self.assertEqual(frames_to_timecode(30, 30.0), "00:00:01.000")
        self.assertEqual(frames_to_timecode(90, 30.0), "00:00:03.000")
    
    def test_timecode_to_frames(self):
        """Тест конвертации timecode в кадры."""
        self.assertEqual(timecode_to_frames("00:00:01.000", 30.0), 30)
        self.assertEqual(timecode_to_frames("00:00:03.000", 30.0), 90)


if __name__ == "__main__":
    unittest.main()

