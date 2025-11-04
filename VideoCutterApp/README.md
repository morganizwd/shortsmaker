# VideoCutterApp

Приложение для обрезки и обработки видео файлов с графическим интерфейсом.

## Возможности

- Обрезка видео по временным меткам
- Предпросмотр видео через VLC
- Настройка профилей кодирования (fast, balanced, high_quality)
- Отображение прогресса обработки
- Логирование операций

## Требования

- Python 3.8+
- FFmpeg (должен быть в PATH или в директории `ffmpeg/`)
- VLC (для предпросмотра)

## Установка

1. Установите зависимости:
```bash
pip install -r requirements.txt
```

2. Установите FFmpeg:
   - Скачайте FFmpeg с [официального сайта](https://ffmpeg.org/download.html)
   - Поместите `ffmpeg.exe` и `ffprobe.exe` в директорию `ffmpeg/` или добавьте в PATH

3. Установите VLC:
   - Скачайте VLC с [официального сайта](https://www.videolan.org/vlc/)
   - Установите на систему

## Запуск

```bash
python -m app.main
```

или

```bash
python app/main.py
```

## Структура проекта

```
VideoCutterApp/
├─ app/
│  ├─ __init__.py
│  ├─ main.py                # Точка входа (GUI запуск)
│  ├─ config.py              # Пути, настройки, профили кодирования
│  ├─ ffmpeg_worker.py       # Запуск ffmpeg, парсинг прогресса, обёртки команд
│  ├─ ffprobe_utils.py       # Получение метаданных (длительность, fps, треки)
│  ├─ models.py              # DTO: Job, FilterChain, Overlay, SubtitleSpec
│  ├─ ui_main.py             # Код окна: кнопки, поля, плеер, прогресс
│  ├─ player_vlc.py          # Воспроизведение через VLC (предпросмотр)
│  ├─ resources/             # Иконки, изображения баннеров, шрифты
│  │   └─ app.ico
│  └─ utils/
│      ├─ paths.py           # Поиск ffmpeg/ffprobe рядом с exe или в PATH
│      ├─ timecode.py        # Конвертации 00:00:00.000 ↔ секунды/кадры
│      └─ logger.py          # Логирование в файл
├─ tests/
│  ├─ test_timecode.py
│  └─ test_ffprobe_utils.py
├─ build/
│  └─ (появится после сборки)
├─ ffmpeg/                   # (опционально) локальная копия ffmpeg.exe/ffprobe.exe
│  ├─ ffmpeg.exe
│  └─ ffprobe.exe
├─ requirements.txt
├─ .gitignore
└─ README.md
```

## Использование

1. Выберите входной видео файл
2. Установите время начала и окончания обрезки
3. Выберите выходной файл
4. Выберите профиль кодирования
5. Нажмите "Обработать"

## Профили кодирования

- **fast**: Быстрая обработка, умеренное качество
- **balanced**: Баланс между скоростью и качеством (по умолчанию)
- **high_quality**: Высокое качество, медленная обработка

## Тестирование

```bash
python -m pytest tests/
```

или

```bash
python -m unittest discover tests
```

## Лицензия

MIT

