import os
import io
import re
import json
import time
import shutil
import subprocess
import hashlib
import difflib
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

# 📦 แกนประมวลผลยุทธศาสตร์หลักตามสถาปัตยกรรม Modular
from schemas.analysis_schemas import AnalyticsMetrics
from engines.video_engine import VideoEngine
from engines.audio_engine import AudioEngine
from engines.transcript_engine import TranscriptEngine
from engines.ai_analysis_engine import AIAnalysisEngine
from utils.logger import get_logger
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
logger = get_logger()

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(CURRENT_DIR, "static")
TEMPLATES_DIR = os.path.join(CURRENT_DIR, "templates")

CACHE_DIR = os.getenv("CACHE_DIR", r"E:\Project_write\WeFool\cache")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 🎯 คลังจัดเก็บสมุดรายชื่อประวัติ สำหรับล็อกลิงก์เดิมไม่ให้วิ่งรันซ้ำ
HISTORY_DIR = os.path.join(CURRENT_DIR, "analysis_history")

if not os.path.exists(STATIC_DIR): os.makedirs(STATIC_DIR)
if not os.path.exists(CACHE_DIR): os.makedirs(CACHE_DIR)
if not os.path.exists(HISTORY_DIR): os.makedirs(HISTORY_DIR)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/templates", StaticFiles(directory=TEMPLATES_DIR), name="templates")

# ระบบจัดเก็บสถานะคำขอประมวลผลยุทธศาสตร์ (Global Job Registry)
JOBS_DATA = {}

video_engine = VideoEngine()
audio_engine = AudioEngine(cache_dir=CACHE_DIR)
ai_engine = AIAnalysisEngine(api_key=GEMINI_API_KEY)

def fetch_related_videos(keywords: list, count: int = 6) -> list:
    """ดึงวิดีโอแนะนำจาก YouTube จำนวน 4-7 คลิป โดยใช้คีย์เวิร์ดเด่นจากการวิเคราะห์"""
    if not keywords:
        return []
    
    # ดึง top keywords 2 ตัวแรกมาสร้างข้อความค้นหา (Search Query)
    search_query = " ".join([re.sub(r'[^a-zA-Z0-9ก-๙\s]', '', k) for k in keywords[:2]])
    logger.info(f"🔍 เริ่มต้นค้นหาสื่อวิดีโออ้างอิงและแนะนำระดับยุทธศาสตร์จาก YouTube ด้วยคำค้นหา: {search_query}")
    try:
        # สั่ง yt-dlp ค้นหาผลลัพธ์ด่วน และแปลงเป็น JSON ใน 1 บรรทัด
        # ใช้ playlist-items 1-{count} เพื่อล็อกจำนวนที่ต้องการ (เช่น 4-7 วิดีโอ)
        cmd = f'yt-dlp --js-runtimes node --flat-playlist --dump-single-json --playlist-items 1-{count} "ytsearch{count}:{search_query}"'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding="utf-8")
        if result.returncode == 0:
            data = json.loads(result.stdout)
            entries = data.get("entries", [])
            recommendations = []
            for entry in entries:
                if not entry:
                    continue
                v_id = entry.get("id")
                v_title = entry.get("title", "วิดีโอแนะนำ")
                v_url = entry.get("url") or f"https://www.youtube.com/watch?v={v_id}"
                # ใช้พิกัดภาพปกมาตรฐานสูงสุดของ YouTube
                v_thumb = f"https://img.youtube.com/vi/{v_id}/0.jpg"
                recommendations.append({
                    "title": v_title,
                    "url": v_url,
                    "thumbnail": v_thumb
                })
            return recommendations
    except Exception as e:
        logger.error(f"❌ ระบบไม่สามารถค้นหาวิดีโอแนะนำจาก YouTube ได้: {e}")
    return []

# ----------------------------------------------------
# BACKGROUND PROCESSING PIPELINE (ขบวนการประมวลผลจริงแปรผันตามวิดีโอ)
# ----------------------------------------------------
async def enterprise_processing_pipeline(job_id: str, mode: str, youtube_url: Optional[str], file_bytes: Optional[bytes], file_name: Optional[str], selected_model: Optional[str] = None):
    pipeline_start_time = time.time()
    try:
        logger.info(f"เริ่มต้นประมวลผลข้อมูลจริงเชิงลึกสำหรับ Job ID: {job_id}")
        JOBS_DATA[job_id]["status"] = "processing"
        JOBS_DATA[job_id]["progress"] = 5
        
        unique_id = f"media_{int(time.time())}"
        video_path = ""
        is_youtube = False
        real_url = ""

        # 🎯 1. [ขั้นตอนสแกนคัดกรองลิงก์ออนไลน์เก่า]: YouTube / TikTok ด้วย Video ID บนเว็บ
        if mode == "youtube" and youtube_url:
            is_youtube = True
            real_url = youtube_url
            unique_id = video_engine.extract_unique_video_id(youtube_url)
            
            history_file_path = os.path.join(HISTORY_DIR, f"{unique_id}.json")
            if os.path.exists(history_file_path):
                logger.info(f"🎯 เจอประวัติเก่าของลิงก์นี้! ({unique_id}) ดึงข้อมูลแดชบอร์ดขึ้นแสดงทันทีใน 1 วินาที...")
                with open(history_file_path, "r", encoding="utf-8") as h_file:
                    saved_result = json.load(h_file)
                
                JOBS_DATA[job_id]["result"] = saved_result
                JOBS_DATA[job_id]["status"] = "completed"
                JOBS_DATA[job_id]["progress"] = 100
                return

        JOBS_DATA[job_id]["progress"] = 10

        # 2. จัดการข้อมูลแหล่งสื่ออินพุต (Video Processing Phase)
        if is_youtube:
            video_path = os.path.join(CACHE_DIR, f"{unique_id}.mp4")
            logger.info(f"ดึงสัญญาณวิดีโอผ่านแพลตฟอร์ม: {unique_id}")
            if not os.path.exists(video_path):
                youtube_url_lower = youtube_url.lower()
                
                # แยกท่อสากลไม่ให้เอ๋อใส่กัน
                if "tiktok.com" in youtube_url_lower:
                    logger.info("📱 ระบบตรวจสอบพบสัญญาณลิงก์ TikTok กำลังสลับไปใช้ท่อดาวน์โหลดสากลมาตรฐาน...")
                    cmd = f'yt-dlp --js-runtimes node -f "best[ext=mp4]" --ffmpeg-location "{CURRENT_DIR}" "{youtube_url}" -o "{video_path}"'
                else:
                    # 🎯 [ปลดล็อก 100% เลิกฟิกซ์ฟอร์แมต]: ปล่อยให้ระบบเลือกไฟล์ที่อิสระและผ่านด่านได้ง่ายที่สุด (เช่น webvtt / webm ที่ไม่ติด PO Token)
                    # จากนั้นใช้คำสั่ง --merge-output-format mp4 เพื่อให้ ffmpeg ประกอบร่างให้เป็น .mp4 สากลหน้าบ้านเอง
                    logger.info("📺 ระบบตรวจสอบพบสัญญาณลิงก์ YouTube กำลังเปิดใช้งานระบบท่อเปิดกว้างข้ามด่าน PO Token...")
                    cmd = (
                        f'yt-dlp --js-runtimes node -f "bestvideo+bestaudio/best" '
                        f'--merge-output-format mp4 '
                        f'--ffmpeg-location "{CURRENT_DIR}" '
                        f'"{youtube_url}" -o "{video_path}"'
                    )
                
                subprocess.run(cmd, shell=True, check=True)
        else:
            # 🎯 [วิธีที่ 1]: คำนวณค่า SHA-256 จากเนื้อหาไฟล์จริง (เปลี่ยนชื่อไฟล์ แฮชก็ยังเท่าเดิม)
            if file_bytes and file_name:
                file_hash = hashlib.sha256(file_bytes).hexdigest()
                unique_id = f"local_sha256_{file_hash[:16]}" # ใช้แฮช 16 หลักแรกเป็นไอดีถาวร
                
                # ตรวจสอบด่านแรก: ถ้าแฮชตรงกับประวัติเดิม ดึงข้อมูลเก่าขึ้นแสดงทันทีใน 1 วินาที (เร็วที่สุด)
                history_file_path = os.path.join(HISTORY_DIR, f"{unique_id}.json")
                if os.path.exists(history_file_path):
                    logger.info(f"🎯 [SHA-256 Match] เจอประวัติตรงกันจากสารบบไฟล์เนื้อหาเดิม! ({unique_id}) ดึงผลลัพธ์ขึ้นแสดงทันที...")
                    with open(history_file_path, "r", encoding="utf-8") as h_file:
                        saved_result = json.load(h_file)
                    
                    JOBS_DATA[job_id]["result"] = saved_result
                    JOBS_DATA[job_id]["status"] = "completed"
                    JOBS_DATA[job_id]["progress"] = 100
                    return 

                # หากด่านแรกไม่เจอ -> ระบบจะบันทึกไฟล์และสกัดเสียงตามปกติก่อน
                video_path = os.path.join(CACHE_DIR, f"{unique_id}.mp4")
                if not os.path.exists(video_path):
                    with open(video_path, "wb") as f:
                        f.write(file_bytes)

        JOBS_DATA[job_id]["progress"] = 30

        # 3. กระบวนการสกัดสัญญาณเสียง (Audio Extraction Phase)
        audio_path = os.path.join(CACHE_DIR, f"{unique_id}.mp3")
        if not os.path.exists(audio_path):
            logger.info(f"กำลังสกัดไฟล์เสียงแท้และป้องกันบั๊กสตรีมว่างของ TikTok: {audio_path}")
            
            cmd_audio = f'ffmpeg -y -i "{video_path}" -vn -acodec libmp3lame -q:a 2 "{audio_path}"'
            result = subprocess.run(cmd_audio, shell=True, capture_output=True)
            
            if result.returncode != 0:
                logger.warning("⚠️ ไม่พบท่อเสียงตรงๆ กำลังใช้คำสั่งกู้คืนช่องสัญญาณ...")
                cmd_fallback = f'ffmpeg -y -i "{video_path}" -f mp3 -vn -acodec libmp3lame -q:a 2 "{audio_path}"'
                fallback_result = subprocess.run(cmd_fallback, shell=True, capture_output=True)
                
                if fallback_result.returncode != 0:
                    logger.error("🚨 สัญญาณเสียงหายเด็ดขาด กำลังเปิดใช้งานระบบสร้างเลเยอร์เสียงจำลอง...")
                    cmd_silent = f'ffmpeg -y -i "{video_path}" -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 -c:v copy -c:a libmp3lame -q:a 2 -shortest -vn "{audio_path}"'
                    subprocess.run(cmd_silent, shell=True, check=True)

        JOBS_DATA[job_id]["progress"] = 50

        # 4. ขบวนการปรับสตรีมภาพวิดีโอให้ขึ้นจอ (Web-Ready Remux แก้จอดำ)
        logger.info("กำลังเปิดระบบสแกนสัญญาณเสียงและสั่งหั่นก้อนข้อมูลส่งวิเคราะห์...")
        
        dest_static_video = os.path.join(STATIC_DIR, f"{unique_id}.mp4")
        if os.path.exists(video_path) and not os.path.exists(dest_static_video):
            youtube_url_lower = (youtube_url or "").lower()
            
            # 🎯 ถ้าเป็นลิงก์ TikTok ให้ทำการแปลงภาพใหม่เป็น H.264 แบบติดสปีดแก้ปัญหาจอดำตามเดิม
            if "tiktok.com" in youtube_url_lower:
                logger.info("🎬 [TikTok Video Remux] บังคับแปลงรหัสภาพใหม่เป็น H.264 (libx264) สปีดเร่งด่วนเพื่อแก้ปัญหาจอดำ...")
                cmd_remux = (
                    f'ffmpeg -y -i "{video_path}" '
                    f'-c:v libx264 -preset ultrafast -pix_fmt yuv420p '
                    f'-c:a aac -b:a 128k -movflags +faststart "{dest_static_video}"'
                )
            # 📺 ถ้าเป็น YouTube หรือไฟล์อื่น ๆ (ซ่อมบั๊กเวลากับคำพูดไม่ตรงกัน)
            else:
                logger.info("🎬 [Standard Video Remux] จัดเรียงโครงสร้างวิดีโอพร้อมซิงค์แกนเวลาถาวร (Timebase Sync)...")
                # 🎯 [ปลดล็อกบั๊กเวลาเพี้ยน]: เพิ่มคำสั่ง -fflags +genpts ปลุกสร้างพิกัดเวลาใหม่ 
                # และพ่วง -async 1 / -vsync passthrough บังคับให้ท่อภาพและเสียงเกาะล็อกเวลาตรงกันเป๊ะ ไม่เหลื่อมหลุดแคช
                cmd_remux = (
                    f'ffmpeg -y -fflags +genpts -i "{video_path}" '
                    f'-c:v copy -c:a copy -async 1 -vsync passthrough '
                    f'-movflags +faststart "{dest_static_video}"'
                )
            
            remux_res = subprocess.run(cmd_remux, shell=True, capture_output=True)
            
            if remux_res.returncode != 0:
                logger.warning("⚠️ ไม่สามารถทำการ Remux ขั้นสูงได้ กำลังคัดลอกไฟล์แบบดิบ...")
                shutil.copy(video_path, dest_static_video)

        # สั่งให้ระบบถอดความคำพูดออกมาก่อนเพื่อนำค่าไปเทียบความคล้ายคลึง
        transcript_engine = TranscriptEngine(preferred_model=selected_model)
        real_timeline = transcript_engine.transcribe_audio(audio_path)
        formatted_text_lines = [f"{item['label']} - {item['text']}" for item in real_timeline]
        
        JOBS_DATA[job_id]["progress"] = 75

        # 🎯 [วิธีที่ 5 & 6]: เปรียบเทียบข้อความถอดความ (Transcript Similarity) เกิน 95% กับคลังข้อมูลเดิม
        current_full_text = "".join([item['text'] for item in real_timeline])
        duplicate_found_id = None
        
        for existing_file in os.listdir(HISTORY_DIR):
            if existing_file.endswith(".json") and existing_file.startswith("local_"):
                try:
                    with open(os.path.join(HISTORY_DIR, existing_file), "r", encoding="utf-8") as old_f:
                        old_data = json.load(old_f)
                        old_timeline = old_data.get("timeline", [])
                        old_full_text = "".join([item['text'] for item in old_timeline])
                        
                        # คำนวณหาค่าอัตราความคล้ายคลึงระหว่างข้อความเก่ากับข้อความใหม่
                        similarity_ratio = difflib.SequenceMatcher(None, current_full_text, old_full_text).ratio()
                        
                        if similarity_ratio >= 0.95:
                            duplicate_found_id = existing_file.replace(".json", "")
                            logger.info(f"💡 [Transcript Match] ตรวจพบข้อความเหมือนกัน {similarity_ratio*100:.2f}% กับไฟล์เก่าไอดี: {duplicate_found_id}")
                            break
                except Exception:
                    continue

        if duplicate_found_id:
            logger.info(f"🎯 ผูกฐานข้อมูลและดึงประวัติเก่าของไอดี {duplicate_found_id} ขึ้นแดชบอร์ดทันที...")
            with open(os.path.join(HISTORY_DIR, f"{duplicate_found_id}.json"), "r", encoding="utf-8") as h_file:
                saved_result = json.load(h_file)
            
            if os.path.exists(video_path): os.remove(video_path)
            if os.path.exists(audio_path): os.remove(audio_path)
            
            JOBS_DATA[job_id]["result"] = saved_result
            JOBS_DATA[job_id]["status"] = "completed"
            JOBS_DATA[job_id]["progress"] = 100
            return

        # ----------------------------------------------------
        # 5. ส่งวิเคราะห์ชุดโครงสร้าง 8 โมดูลหลักแบบ Dynamic
        # ----------------------------------------------------
        logger.info("ส่งข้อมูลคำพูดจริงเข้าสู่กระบวนการวิเคราะห์ 8 โมดูลหลักยุทธศาสตร์...")
        
        strategic_prompt = (
            "คุณคือผู้เชี่ยวชาญด้านการวิเคราะห์สื่อระดับองค์กร\n\n"

            "หน้าที่ของคุณคือวิเคราะห์ข้อมูลจากข้อความถอดเสียงเท่านั้น\n\n"

            "กฎสำคัญ:\n"
            "1. ห้ามลบข้อความต้นฉบับ\n"
            "2. ห้ามย่อข้อความต้นฉบับ\n"
            "3. ห้ามสรุปข้อความต้นฉบับก่อนวิเคราะห์\n"
            "4. ห้ามเปลี่ยนความหมายของคำพูด\n"
            "5. ห้ามเติมข้อมูลที่ไม่มีอยู่ในคลิป\n"
            "6. ใช้ข้อมูลจากข้อความถอดเสียงจริงเท่านั้น\n"
            "7. หากพบคำสะกดผิด ให้ใช้ความหมายเดิมในการวิเคราะห์ แต่ห้ามแก้ไขข้อความต้นฉบับ\n"
            "8. หากข้อมูลไม่ชัดเจน ให้ระบุว่าไม่แน่ใจ ห้ามเดา\n\n"

            "ภารกิจคือสร้างผลการวิเคราะห์จากข้อความเท่านั้น โดยข้อความต้นฉบับต้องถือเป็นข้อมูลอ้างอิงที่ห้ามเปลี่ยนแปลง\n\n"

            "ตอบกลับเฉพาะ JSON ตาม Schema ด้านล่าง\n"

            "{\n"
            "  \"summary\": [\"บทสรุปประเด็นหลักประโยคยาวที่ได้ใจความจากคลิปจริง 3-5 บรรทัด\"],\n"
            "  \"keyword_trending\": [{\"keyword\": \"คำสำคัญที่เจอในคลิป\", \"count\": จำนวนครั้งที่เจอ}],\n"
            "  \"sentiment_analysis\": [{\"time_range\": \"ช่วงเวลา\", \"sentiment\": \"อารมณ์\", \"trigger\": \"ปัจจัยกระตุ้น\", \"purpose\": \"เป้าหมายคำพูด\"}],\n"
            "  \"dominant_sentiment_summary\": \"บทสรุปภาพรวมบรรยากาศทางจิตวิทยาของคลิปนี้\",\n"
            "  \"video_chapters\": [{\"start_time_seconds\": วินาที, \"time_range_label\": \"ช่วงเวลา\", \"chapter_title\": \"ชื่อบทเรียนย่อยจากคลิปจริง\", \"sub_chapters\": [{\"start_time_seconds\": วินาที, \"time_range_label\": \"ช่วงเวลา\", \"sub_title\": \"หัวข้อย้อย\"}]}]\n"
            "}"
        )

        current_ai_engine = AIAnalysisEngine(api_key=GEMINI_API_KEY, preferred_model=selected_model)
        ai_analysis_data = current_ai_engine.generate_analytics(strategic_prompt, formatted_text_lines)

        if ai_analysis_data is None:
            logger.warning("⚠️ โครงข่าย AI ส่งค่าว่างกลับมา กำลังเปิดใช้งานระบบฐานข้อมูลสำรอง...")
            ai_analysis_data = {
                "summary": ["ระบบถอดความสำเร็จครบถ้วน แต่โมดูลย่อยวิเคราะห์เกินขีดจำกัดหน่วยความจำชั่วคราว"],
                "keyword_trending": [{"keyword": "วิดีโอ", "count": 10}],
                "sentiment_analysis": [{"time_range": "0:00 - End", "sentiment": "Analytical", "trigger": "ระบบจำลอง", "purpose": "คงสถานะแดชบอร์ด"}],
                "dominant_sentiment_summary": "อยู่ในระหว่างประเมินผลผ่านฐานข้อมูลสำรอง",
                "video_chapters": [{"start_time_seconds": 0, "time_range_label": "00:00", "chapter_title": "บทเรียนหลักจากคลิปวิดีโอต้นฉบับ", "sub_chapters": []}]
            }

        # 6. คำนวณมาตรวัดเชิงสถิติ
        total_sentences = len(real_timeline)
        total_words = sum(len(item['text'].split()) for item in real_timeline) or (len("".join([item['text'] for item in real_timeline])) // 3)
        
        last_time = real_timeline[-1]['time'] if (real_timeline and real_timeline[-1]['time'] > 0) else 0
        wpm_calc = str(int(total_words / (last_time / 60))) if last_time > 0 else "140"

        # 🎯 [แก้บั๊กพิกัดเวลาเพี้ยนถาวร]: บังคับดึงพิกัดเวลาจาก Speech-to-Text ซิงค์ลงระบบบทเรียน
        synced_chapters = []
        if ai_analysis_data and ai_analysis_data.get("video_chapters"):
            for idx, ai_ch in enumerate(ai_analysis_data["video_chapters"]):
                matched_time = 0
                matched_label = "00:00"
                
                ch_title = ai_ch.get("chapter_title", "")
                clean_ch_title = re.sub(r'[^a-zA-Z0-9ก-๙]', '', ch_title)
                
                best_ratio = 0
                # ค้นหาข้อความคู่ขนาน
                for tl in real_timeline:
                    clean_tl_text = re.sub(r'[^a-zA-Z0-9ก-๙]', '', tl["text"])
                    ratio = difflib.SequenceMatcher(None, clean_ch_title, clean_tl_text).ratio()
                    if ratio > best_ratio:
                        best_ratio = ratio
                        # 🎯 ดึงตำแหน่งเวลาจริงของประโยคสคริปต์ตั้งต้น (ซึ่งแกะจากวินาทีเริ่มพูดคำแรก) แทนการดึงพิกัดปลายประโยค
                        matched_time = tl["time"]
                        matched_label = tl["label"]
                
                # 🛠️ [กลไกดักจับความแม่นยำด่านสุดท้าย]: ถ้าเป็นบทเรียนช่องแรก บังคับเซ็ตแกนเวลาเริ่มพูดที่ 1 วินาที (00:01) เสมอ
                if idx == 0:
                    matched_time = real_timeline[0]["time"] if real_timeline else 1
                    # จัดฟอร์แมตฉลากข้อความให้โชว์ซิงค์เป็นเวลาเริ่มสตาร์ทคลิปทันที
                    matched_label = "00:01" if matched_time <= 1 else real_timeline[0]["label"]
                elif best_ratio < 0.2:
                    # ป้องกันการคลาดเคลื่อน ถอยกลับไปใช้พิกัดคำนวณถอยหลัง 5 วินาทีจากช่วง AI ส่งมา
                    ai_start = ai_ch.get("start_time_seconds", 0)
                    matched_time = max(1, ai_start - 6) if ai_start > 0 else 1
                    mins = int(matched_time // 60)
                    secs = int(matched_time % 60)
                    matched_label = f"{mins:02d}:{secs:02d}"

                # จัดการสารบัญย่อย (Sub Chapters) ให้ซิงค์พิกัดคำแรกตามไปด้วย
                synced_subs = []
                for s_idx, sub in enumerate(ai_ch.get("sub_chapters", [])):
                    sub_time = sub.get("start_time_seconds", 0)
                    sub_label = sub.get("time_range_label", "00:00")
                    sub_title = sub.get("sub_title", "")
                    clean_sub_title = re.sub(r'[^a-zA-Z0-9ก-๙]', '', sub_title)
                    
                    sub_best_ratio = 0
                    for tl in real_timeline:
                        clean_tl_text = re.sub(r'[^a-zA-Z0-9ก-๙]', '', tl["text"])
                        s_ratio = difflib.SequenceMatcher(None, clean_sub_title, clean_tl_text).ratio()
                        if s_ratio > sub_best_ratio:
                            sub_best_ratio = s_ratio
                            sub_time = tl["time"]
                            sub_label = tl["label"]
                    
                    # บังคับปัดเศษบทย่อยช่วงแรกให้เกาะติดกับเวลาหลัก ไม่ค้างเตลิดไปตอนสรุปจบ
                    if s_idx == 0 and idx == 0:
                        sub_time = matched_time
                        sub_label = matched_label
                    elif sub_best_ratio < 0.2 and sub_time > 0:
                        sub_time = max(1, sub_time - 5)
                        sub_label = f"{int(sub_time//60):02d}:{int(sub_time%60):02d}"
                            
                    synced_subs.append({
                        "start_time_seconds": sub_time,
                        "time_range_label": sub_label,
                        "sub_title": sub_title
                    })

                synced_chapters.append({
                    "start_time_seconds": matched_time,
                    "time_range_label": matched_label,
                    "chapter_title": ch_title,
                    "sub_chapters": synced_subs
                })
        else:
            synced_chapters = [{"start_time_seconds": 1, "time_range_label": "00:01", "chapter_title": "บทเรียนหลักจากคลิปวิดีโอต้นฉบับ", "sub_chapters": []}]

        real_url_lower = real_url.lower()
        is_output_youtube = is_youtube
        if "tiktok.com" in real_url_lower:
            is_output_youtube = False

        # 📊 คำนวณขนาดไฟล์ที่ประมวลผลจริง และเวลาที่ใช้ในการประมวลผลทั้งหมด
        file_size_label = "วิเคราะห์จากระบบคลาวด์"
        target_file_for_size = dest_static_video if os.path.exists(dest_static_video) else video_path
        if os.path.exists(target_file_for_size):
            size_bytes = os.path.getsize(target_file_for_size)
            size_mb = size_bytes / (1024 * 1024)
            file_size_label = f"{size_mb:.2f} MB"

        elapsed_seconds = time.time() - pipeline_start_time
        h = int(elapsed_seconds // 3600)
        m = int((elapsed_seconds % 3600) // 60)
        s = int(elapsed_seconds % 60)
        if h > 0:
            analysis_time_label = f"{h:02d}:{m:02d}:{s:02d}"
        else:
            analysis_time_label = f"{m:02d}:{s:02d}"

        # ดึงคำสำคัญและทำการสืบค้นวิดีโอแนะนำเชิงลึก (4-7 คลิป)
        trending_keywords = [item.get("keyword", "") for item in ai_analysis_data.get("keyword_trending", [])]
        recommended_cards = fetch_related_videos(trending_keywords, count=6)
        
        # หากไม่เจอ ให้ดีดกลับไปใช้ตัวต้นฉบับสำรองเป็น default
        if not recommended_cards:
            recommended_cards = [
                {"title": f"วิเคราะห์เจาะลึก: {unique_id}", "url": real_url if is_output_youtube else "#", "thumbnail": f"https://img.youtube.com/vi/{unique_id}/0.jpg" if is_output_youtube else "/static/Logo_boy.png"}
            ]

        final_result = {
            "is_youtube": is_output_youtube,
            "real_youtube_url": real_url,
            "video_url": f"/static/{unique_id}.mp4",
            "model_used": selected_model if selected_model else "Gemini Multi-Model Dynamic Loop Engine",
            "timeline": real_timeline, 
            "summary": ai_analysis_data.get("summary", ["วิเคราะห์โครงสร้างเนื้อหาสำเร็จ"]),
            "file_size_label": file_size_label,
            "analysis_time": analysis_time_label,
            "telemetry": {
                "duration": f"{real_timeline[-1]['label'] if real_timeline else '00:00'} นาที",
                "words": f"{total_words} คำ",
                "sentences": f"{total_sentences} ประโยค",
                "wpm": wpm_calc,
                "topics": ai_analysis_data.get("summary", [""])[0][:20] if ai_analysis_data.get("summary") else "General Analysis"
            },
            "keywords_chart": ai_analysis_data.get("keyword_trending", []),
            "sentiment_table": ai_analysis_data.get("sentiment_analysis", []),
            "dominant_sentiment": ai_analysis_data.get("dominant_sentiment_summary", "ประเมินภาพรวมความเรียบร้อยสำเร็จ"),
            "recommendations": recommended_cards,
            "video_counters": synced_chapters,
            "video_chapters": synced_chapters
        }

        # 💾 บันทึกผลลงคลังถาวร
        if not os.path.exists(HISTORY_DIR): 
            os.makedirs(HISTORY_DIR)
            
        history_file_path = os.path.join(HISTORY_DIR, f"{unique_id}.json")
        with open(history_file_path, "w", encoding="utf-8") as h_file:
            json.dump(final_result, h_file, ensure_ascii=False, indent=4)
            
        logger.info(f"💾 ระบบทำการบันทึกประวัติสำเร็จ รหัสอ้างอิง: {unique_id}")

        JOBS_DATA[job_id]["result"] = final_result
        JOBS_DATA[job_id]["status"] = "completed"
        JOBS_DATA[job_id]["progress"] = 100
        logger.info(f"✅ สำเร็จเสร็จสิ้น! นำส่งข้อมูลเข้าระบบสำเร็จ")

    except Exception as e:
        logger.error(f"❌ เกิดข้อผิดพลาดในระบบวิเคราะห์ข้อมูลจริง {job_id}: {str(e)}")
        JOBS_DATA[job_id]["status"] = "failed"
        JOBS_DATA[job_id]["error"] = str(e)

# ----------------------------------------------------
# API ENDPOINTS
# ----------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def serve_index_dashboard():
    index_path = os.path.join(TEMPLATES_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h3>ไม่พบไฟล์ index.html ในโฟลเดอร์ templates</h3>", status_code=404)

# 🎯 Route ดักตรวจประวัติเก่าด่วน และคำนวณราคาประเมิน Token
@app.post("/pre_check_cache")
async def handle_pre_check_cache(
    mode: str = Form(...),
    youtube_url: Optional[str] = Form(None),
    file_name: Optional[str] = Form(None),
    file_size_bytes: Optional[int] = Form(None)
):
    unique_id = ""
    if mode == "youtube" and youtube_url:
        unique_id = video_engine.extract_unique_video_id(youtube_url)
    elif mode in ["mp4", "file"] and file_name and file_size_bytes:
        clean_name = re.sub(r'[^a-zA-Z0-9]', '', file_name)
        for existing_file in os.listdir(HISTORY_DIR):
            if clean_name in existing_file:
                unique_id = existing_file.replace(".json", "")
                break
        if not unique_id:
            unique_id = f"local_sha256_preview_{clean_name}"

    history_file_path = os.path.join(HISTORY_DIR, f"{unique_id}.json")
    if os.path.exists(history_file_path):
        with open(history_file_path, "r", encoding="utf-8") as h_file:
            saved_result = json.load(h_file)
        return {"cache_exists": True, "result_data": saved_result}

    duration_seconds = 600
    duration_label = "ประมาณ 10:00 นาที"

    if mode == "youtube" and youtube_url:
        try:
            cmd = f'yt-dlp --js-runtimes node --get-duration "{youtube_url}"'
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            duration_str = proc.stdout.strip()
            if duration_str:
                duration_label = f"{duration_str} นาที"
                parts = list(map(int, duration_str.split(':')))
                if len(parts) == 2: duration_seconds = parts[0] * 60 + parts[1]
                elif len(parts) == 3: duration_seconds = parts[0] * 3600 + parts[1] * 60 + parts[2]
        except Exception:
            pass
    else:
        duration_label = "ประเมินตามขนาดไฟล์สื่ออัปโหลด"
        duration_seconds = 300 

    import math
    duration_minutes = math.ceil(duration_seconds / 60.0)
    if duration_minutes < 1:
        duration_minutes = 1

    input_tokens = duration_minutes * 1500
    output_tokens = duration_minutes * 300
    estimated_tokens = input_tokens + output_tokens

    # Default backend calculation is based on Gemini 2.5 Flash-Lite
    estimated_cost = round((input_tokens * 0.00000391) + (output_tokens * 0.00001562), 4)

    return {
        "cache_exists": False,  
        "duration_label": duration_label,
        "duration_seconds": duration_seconds,
        "estimated_tokens": estimated_tokens,
        "estimated_cost_baht": estimated_cost
    }

@app.post("/process")
@app.post("/submit_analysis")
async def handle_analysis_submission(
    background_tasks: BackgroundTasks,
    mediaMode: Optional[str] = Form(None),
    mode: Optional[str] = Form(None),
    youtubeUrl: Optional[str] = Form(None),
    youtube_url: Optional[str] = Form(None),
    localFile: Optional[UploadFile] = File(None),
    file: Optional[UploadFile] = File(None),
    model: Optional[str] = Form(None)
):
    final_mode = mediaMode if mediaMode else mode
    final_url = youtubeUrl if youtubeUrl else youtube_url
    final_file = localFile if localFile else file

    if not final_mode:
        return JSONResponse(content={"error": "Missing mode parameter"}, status_code=400)

    job_id = f"job_{int(time.time())}"
    JOBS_DATA[job_id] = {"status": "queued", "progress": 0, "result": None}
    logger.info(f"ลงทะเบียนคำขอผ่าน Route รหัสงาน: {job_id}")

    file_bytes = None
    file_name = None
    if final_mode in ["mp4", "file"] and final_file:
        file_bytes = await final_file.read()
        file_name = final_file.filename

    background_tasks.add_task(
        enterprise_processing_pipeline, 
        job_id, 
        final_mode, 
        final_url, 
        file_bytes, 
        file_name,
        model
    )
    
    return JSONResponse(content={"job_id": job_id, "queued": True})

@app.get("/job_status/{job_id}")
async def check_job_status(job_id: str):
    job = JOBS_DATA.get(job_id)
    if not job:
        return JSONResponse(content={"error": "ไม่พบข้อมูลรหัสงานนี้ในคิวระบบ"}, status_code=404)
    return JSONResponse(content=job)

@app.post("/translate_timeline")
async def handle_pivot_translation(target_lang: str = Form(...), transcript_text: str = Form(...)):
    prompt = f"แปลข้อความในลิสต์นี้เป็นภาษา {target_lang} โดยคงรักษาโครงสร้างเวลาเดิมไว้อย่างเคร่งครัด"
    text_array = transcript_text.split("\n")
    translation_result = ai_engine.generate_analytics(prompt, text_array)
    if translation_result:
        return JSONResponse(content={ "translated_lines": translation_result if isinstance(translation_result, list) else [] })
    return JSONResponse(content={"error": "ระบบแปลภาษาขัดข้อง"}, status_code=500)

# ----------------------------------------------------
# DOWNLOAD REPORT ENDPOINTS (โมดูลที่ 9: ดาวน์โหลดผลลัพธ์)
# ----------------------------------------------------
@app.get("/download/txt/{unique_id}")
async def download_txt_report(unique_id: str):
    history_file_path = os.path.join(HISTORY_DIR, f"{unique_id}.json")
    if not os.path.exists(history_file_path):
        return HTMLResponse(content="<h3>❌ ไม่พบข้อมูลประวัติการประมวลผลสำหรับรหัสอ้างอิงนี้</h3>", status_code=404)
        
    try:
        with open(history_file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        timeline = data.get("timeline", [])
        real_url = data.get("real_youtube_url", "Local File Upload")
        duration = data.get("telemetry", {}).get("duration", "ไม่ทราบความยาว")
        
        # ประกอบไฟล์ข้อความตามมาตรฐานของผู้ใช้
        txt_content = []
        txt_content.append("==========================================================")
        txt_content.append("           YAMASEE MULTIMEDIA PLATFORM REPORT")
        txt_content.append(f" แหล่งอ้างอิงมีเดีย: {real_url}")
        txt_content.append(f" ความยาววิดีโอ: {duration}")
        txt_content.append(f" วันที่ดาวน์โหลดเอกสาร: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        txt_content.append("==========================================================\n")
        
        for item in timeline:
            label = item.get("label", "[00:00]").replace("[", "").replace("]", "")
            # ฟอร์แมตเวลาให้เป็น [HH:MM:SS] หรือ [MM:SS] เสมอ
            txt_content.append(f"[{label}] {item.get('text', '')}")
            
        final_txt = "\n".join(txt_content)
        
        return Response(
            content=final_txt,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=yamasee_transcript_{unique_id}.txt"}
        )
    except Exception as e:
        logger.error(f"เกิดข้อผิดพลาดในการสร้างไฟล์ .txt: {e}")
        return JSONResponse(content={"error": f"ระบบประมวลผลข้อความขัดข้อง: {e}"}, status_code=500)


@app.get("/download/pdf/{unique_id}")
async def download_pdf_report(unique_id: str):
    history_file_path = os.path.join(HISTORY_DIR, f"{unique_id}.json")
    if not os.path.exists(history_file_path):
        return HTMLResponse(content="<h3>❌ ไม่พบข้อมูลประวัติการประมวลผลสำหรับรหัสอ้างอิงนี้</h3>", status_code=404)
        
    try:
        with open(history_file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        timeline = data.get("timeline", [])
        real_url = data.get("real_youtube_url", "Local File Upload")
        duration = data.get("telemetry", {}).get("duration", "ไม่ทราบความยาว")
        summary_sentences = data.get("summary", ["วิเคราะห์ข้อมูลสมบูรณ์"])
        
        # ค้นหาและลงทะเบียนฟอนต์ภาษาไทยของ Windows (Tahoma) เพื่อสยบบั๊กตัวอักษรสระไทยเพี้ยน
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        
        font_name = 'Helvetica'
        font_name_bold = 'Helvetica-Bold'
        
        try:
            pdfmetrics.registerFont(TTFont('Tahoma', 'C:\\Windows\\Fonts\\tahoma.ttf'))
            pdfmetrics.registerFont(TTFont('Tahoma-Bold', 'C:\\Windows\\Fonts\\tahomabd.ttf'))
            font_name = 'Tahoma'
            font_name_bold = 'Tahoma-Bold'
            logger.info("🎯 ลงทะเบียนฟอนต์ภาษาไทย Tahoma บน Windows สำเร็จเรียบร้อยสำหรับ PDF")
        except Exception as font_err:
            logger.warning(f"⚠️ ไม่สามารถดึงฟอนต์ Tahoma ได้ ระบบจะรันฟอนต์มาตรฐานแทน: {font_err}")
            
        # สร้างบัฟเฟอร์หน่วยความจำชั่วคราวเพื่อตอบกลับเป็นไบต์สตรีมทันที
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, 
            pagesize=A4, 
            rightMargin=36, leftMargin=36, 
            topMargin=36, bottomMargin=36
        )
        
        story = []
        styles = getSampleStyleSheet()
        
        # สร้าง Custom Styles สำหรับ Tahoma ภาษาไทย
        title_style = ParagraphStyle(
            'ThaiTitle',
            parent=styles['Heading1'],
            fontName=font_name_bold,
            fontSize=18,
            leading=22,
            textColor=colors.HexColor('#2563EB'),
            alignment=1, # กึ่งกลาง
            spaceAfter=15
        )
        
        section_style = ParagraphStyle(
            'ThaiSection',
            parent=styles['Heading2'],
            fontName=font_name_bold,
            fontSize=13,
            leading=16,
            textColor=colors.HexColor('#FF9A00'),
            spaceBefore=15,
            spaceAfter=10,
            borderPadding=4
        )
        
        body_style = ParagraphStyle(
            'ThaiBody',
            parent=styles['Normal'],
            fontName=font_name,
            fontSize=10,
            leading=15,
            textColor=colors.HexColor('#334155'),
            spaceAfter=6
        )
        
        meta_label_style = ParagraphStyle(
            'ThaiMetaLabel',
            fontName=font_name_bold,
            fontSize=9,
            leading=12,
            textColor=colors.HexColor('#475569')
        )
        
        meta_val_style = ParagraphStyle(
            'ThaiMetaVal',
            fontName=font_name,
            fontSize=9,
            leading=12,
            textColor=colors.HexColor('#0F172A')
        )
        
        # 1. หัวเรื่องหลักรายงานเชิงสถิติพรีเมียม
        story.append(Paragraph("YAMASEE TRANSCRIPT EXECUTIVE REPORT", title_style))
        story.append(Spacer(1, 10))
        
        # 2. ตารางตารางข้อมูลรายละเอียด (Metadata Table)
        meta_data = [
            [Paragraph("<b>แหล่งที่มาของสื่อ (Media Source):</b>", meta_label_style), Paragraph(real_url, meta_val_style)],
            [Paragraph("<b>ความยาวของคลิปวิดีโอ:</b>", meta_label_style), Paragraph(duration, meta_val_style)],
            [Paragraph("<b>รหัสอ้างอิงระบบ (Reference ID):</b>", meta_label_style), Paragraph(unique_id, meta_val_style)],
            [Paragraph("<b>วันที่สกัดข้อมูลยุทธศาสตร์:</b>", meta_label_style), Paragraph(time.strftime('%Y-%m-%d %H:%M:%S'), meta_val_style)]
        ]
        
        meta_table = Table(meta_data, colWidths=[150, 370])
        meta_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8FAFC')),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#E2E8F0')),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#F1F5F9')),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 12),
            ('RIGHTPADDING', (0,0), (-1,-1), 12),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        
        story.append(meta_table)
        story.append(Spacer(1, 15))
        
        # 3. บทสรุปยุทธศาสตร์ (Executive Summary)
        story.append(Paragraph("💡 บทสรุปวิเคราะห์เนื้อหายุทธศาสตร์ (Executive Summary)", section_style))
        summary_text = " ".join(summary_sentences)
        story.append(Paragraph(summary_text, body_style))
        story.append(Spacer(1, 15))
        
        # 4. ส่วนตารางหลัก (Transcription Timeline Table)
        story.append(Paragraph("📊 รายการตารางเวลาถอดความคำพูด (Detailed Transcription Timeline)", section_style))
        
        # กำหนดหน้าตาสไตล์ตารางรายงาน
        table_style = TableStyle([
            ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#1E293B')),
            ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#CBD5E1')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ])
        
        table_header_time_style = ParagraphStyle(
            'HeaderTime',
            fontName=font_name_bold,
            fontSize=10,
            leading=12,
            textColor=colors.white
        )
        
        table_header_text_style = ParagraphStyle(
            'HeaderText',
            fontName=font_name_bold,
            fontSize=10,
            leading=12,
            textColor=colors.white
        )
        
        table_body_time_style = ParagraphStyle(
            'BodyTime',
            fontName=font_name_bold,
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor('#2563EB')
        )
        
        table_body_text_style = ParagraphStyle(
            'BodyText',
            fontName=font_name,
            fontSize=9.5,
            leading=14,
            textColor=colors.HexColor('#1E293B')
        )
        
        table_rows = [
            [Paragraph("เวลา (Timestamp)", table_header_time_style), Paragraph("ข้อความถอดความคำพูด (Transcription Timeline)", table_header_text_style)]
        ]
        
        # วนลูปข้อมูล timeline เพื่อสร้างคอลัมน์ของตาราง
        for row in timeline:
            lbl = row.get("label", "00:00").replace("[", "").replace("]", "")
            txt = row.get("text", "")
            table_rows.append([
                Paragraph(lbl, table_body_time_style),
                Paragraph(txt, table_body_text_style)
            ])
            
        # สร้างวัตถอร์ตารางและกำหนดความกว้างคอลัมน์ (เวลา 90pt, ข้อความ 430pt)
        trans_table = Table(table_rows, colWidths=[90, 430], repeatRows=1)
        trans_table.setStyle(table_style)
        
        story.append(trans_table)
        
        # ประกอบโครงร่างลงเอกสาร PDF
        doc.build(story)
        
        # ส่งข้อมูลคืนเป็นไบต์ไฟล์กลับไปยังเบราว์เซอร์เพื่อให้ผู้ใช้บันทึก
        buffer.seek(0)
        return StreamingResponse(
            buffer, 
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=yamasee_report_{unique_id}.pdf"}
        )
    except Exception as e:
        logger.error(f"เกิดข้อผิดพลาดในการสร้างรายงาน PDF: {e}")
        return HTMLResponse(content=f"<h3>❌ ระบบไม่สามารถประมวลผลสร้างรายงาน PDF ได้: {e}</h3>", status_code=500)

if __name__ == "__main__":
    import uvicorn
    logger.info("กำลังสตาร์ทระบบ YAMASEE Transcript Real Platform Systems...")
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)