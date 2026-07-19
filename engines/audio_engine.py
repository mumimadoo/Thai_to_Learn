import os
import subprocess
from utils.logger import logger

class AudioEngine:
    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir

    def extract_audio(self, video_path: str, output_name: str) -> str:
        """แปลงไฟล์วิดีโอเป็นเสียง .mp3 ด้วย ffmpeg จริง"""
        audio_path = os.path.join(self.cache_dir, f"{output_name}.mp3")
        
        # ใช้ list argument แทน shell=True เพื่อความปลอดภัย
        cmd = [
            "ffmpeg", "-y", "-i", video_path, 
            "-vn", "-acodec", "libmp3lame", "-q:a", "2", 
            audio_path
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            logger.info(f"✅ สกัดเสียงสำเร็จ: {audio_path}")
            return audio_path
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ สกัดเสียงล้มเหลว: {e.stderr.decode()}")
            raise e

    def split_audio_into_chunks(self, audio_path: str, chunk_length: float = 60.0) -> list:
        # Implementation for chunking if needed, though currently it is in TranscriptEngine
        pass
