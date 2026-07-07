import os
import subprocess

class AudioEngine:
    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir

    def extract_audio(self, video_path: str, output_name: str) -> str:
        """แปลงไฟล์วิดีโอเป็นเสียง .mp3 หรือ .wav เพื่อเตรียมส่งเข้า Speech Engine"""
        audio_path = os.path.join(self.cache_dir, f"{output_name}.mp3")
        # Logic การใช้ ffmpeg เพื่อดึงเสียง (ย้ายมาจาก main.py)
        # command = f'ffmpeg -i "{video_path}" -vn -acodec libmp3lame -q:a 2 "{audio_path}"'
        return audio_path

    def split_audio_into_chunks(self, audio_path: str, chunk_length_ms: int = 30000) -> list:
        """ตัดไฟล์เสียงเป็นส่วนย่อยๆ (Chunking) เพื่อให้ประมวลผลทีละส่วน ลดการใช้ RAM"""
        chunks = []
        # Logic การวนลูปตัดไฟล์
        return chunks