import subprocess
import os
import re
import json

from utils.logger import logger

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
    def analyze_silence_timestamps(audio_path: str) -> list:
        """ตรวจหาช่วงเงียบในไฟล์เสียงด้วย ffmpeg และคืนค่าเป็น List ของ {start, end}"""
        silence_list = []
        # ใช้ silencedetect=n=-30dB:d=0.5
        cmd = [
            "ffmpeg", "-i", audio_path, 
            "-af", "silencedetect=n=-30dB:d=0.5", 
            "-f", "null", "-"
        ]
        
        try:
            # silencedetect ส่งผลลัพธ์ผ่าน stderr
            result = subprocess.run(cmd, capture_output=True, text=True)
            output = result.stderr
            
            # สกัด start และ end times
            starts = re.findall(r'silence_start: ([\d\.]+)', output)
            ends = re.findall(r'silence_end: ([\d\.]+)', output)
            
            for s, e in zip(starts, ends):
                silence_list.append({"start": float(s), "end": float(e)})
            
            logger.info(f"✅ พบช่วงเงียบ {len(silence_list)} ช่วงใน {audio_path}")
            return silence_list
        except Exception as e:
            logger.error(f"❌ วิเคราะห์ช่วงเงียบล้มเหลว: {e}")
            return []
