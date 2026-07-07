import subprocess
import os
import re

from utils.logger import logger

class AIAnalysisEngine:
    # ...
    def generate_analytics(self, prompt, text_array):
        logger.debug(f"กำลังเรียกใช้โมเดลวิเคราะห์ข้อมูล...")
        
class VideoEngine:
    @staticmethod
    def extract_unique_video_id(url: str) -> str:
        if "tiktok.com" in url:
            match = re.search(r'/video/(\d+)', url)
            if match: return f"tiktok_{match.group(1)}"
            return f"tiktok_hash_{abs(hash(url))}"
        match = re.search(r'(youtu\.be\/|v\/|u\/\w\/|embed\/|watch\?v=|\&v=)([^#\&\?]*)', url)
        if match and len(match.group(2)) == 11:
            return f"youtube_{match.group(2)}"
        return f"media_hash_{abs(hash(url))}"

    @staticmethod
    def convert_seconds_to_label(total_seconds: int) -> str:
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        if hours > 0: return f"[{hours:02d}:{minutes:02d}:{seconds:02d}]"
        return f"[{minutes:02d}:{seconds:02d}]"

    @staticmethod
    def analyze_silence_timestamps(audio_path: str, total_duration: int) -> list:
        # ย้าย Logic ของ ffmpeg silencedetect มาไว้ที่นี่
        pass