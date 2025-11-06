from pathlib import Path

path = Path("VideoCutterApp/app/player_vlc.py")
data = path.read_bytes()
marker = b'    def _cleanup_preview_file'
idx = data.find(marker)
if idx == -1:
    raise SystemExit('cleanup helper not found')
# find the next method definition after helpers
search_pos = idx + 1
while True:
    pos = data.find(b'    def ', search_pos)
    if pos == -1:
        raise SystemExit('no following method found')
    if pos != idx:
        insert_pos = pos
        break
    search_pos = pos + 1
new_block = """    def set_color_correction(
        self,
        brightness: float = 0.0,
        contrast: float = 1.0,
        saturation: float = 1.0,
        sharpness: float = 0.0,
        shadows: float = 0.0,
        temperature: float = 0.0,
        tint: float = 0.0
    ):
        \"\"\"Применяет настройки цветокоррекции к предпросмотру.\"\"\"
        if not self.player or not self.current_file:
            return

        self.brightness = brightness
        self.contrast = contrast
        self.saturation = saturation
        self.sharpness = sharpness
        self.shadows = shadows
        self.temperature = temperature
        self.tint = tint

        if abs(shadows) >= 0.01:
            self.gamma = max(0.01, min(10.0, 1.0 + shadows * 0.5))
        else:
            self.gamma = 1.0

        needs_ffmpeg_preview = self._color_preview_requires_ffmpeg(sharpness, shadows)

        if needs_ffmpeg_preview:
            self.use_ffmpeg_preview = True
            self._pending_color_params = {
                'brightness': brightness,
                'contrast': contrast,
                'saturation': saturation,
                'sharpness': sharpness,
                'shadows': shadows,
                'temperature': temperature,
                'tint': tint,
                'aspect_ratio': self.aspect_ratio or \"16:9\"
            }
            self._preview_update_timer.stop()
            self._preview_update_timer.start(self._ffmpeg_preview_delay_ms)
            return

        if self.use_ffmpeg_preview:
            self.use_ffmpeg_preview = False
            self._preview_update_timer.stop()
            self._pending_color_params = None
            self._active_preview_request_id = None
            self._cleanup_preview_file()
            self._disable_vlc_color_adjustments()

        self._apply_vlc_color_correction(
            brightness, contrast, saturation, sharpness, shadows, temperature, tint
        )

"""
new_data = data[:insert_pos] + new_block.encode('utf-8') + data[insert_pos:]
path.write_bytes(new_data)
