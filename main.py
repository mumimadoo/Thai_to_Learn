import os
import re
import json
import time
import shutil
import subprocess
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
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

# ----------------------------------------------------
# BACKGROUND PROCESSING PIPELINE (ขบวนการประมวลผลจริงแปรผันตามวิดีโอ)
# ----------------------------------------------------
async def enterprise_processing_pipeline(job_id: str, mode: str, youtube_url: Optional[str], file_bytes: Optional[bytes], file_name: Optional[str]):
    try:
        logger.info(f"เริ่มต้นประมวลผลข้อมูลจริงเชิงลึกสำหรับ Job ID: {job_id}")
        JOBS_DATA[job_id]["status"] = "processing"
        JOBS_DATA[job_id]["progress"] = 5
        
        unique_id = f"media_{int(time.time())}"
        video_path = ""
        is_youtube = False
        real_url = ""

        # ดึง ID ออกมาล่วงหน้าเพื่อใช้สแกนหา Cache ประวัติเก่า
        if mode == "youtube" and youtube_url:
            is_youtube = True
            real_url = youtube_url
            unique_id = video_engine.extract_unique_video_id(youtube_url)
            
            # 🎯 [ระบบดักจำลิงก์เก่า] เช็กว่าเคยวิเคราะห์วิดีโอ ID นี้ไปแล้วหรือยัง
            history_file_path = os.path.join(HISTORY_DIR, f"{unique_id}.json")
            if os.path.exists(history_file_path):
                logger.info(f"🎯 เจอประวัติเก่าของลิงก์นี้! ({unique_id}) ดึงข้อมูลแดชบอร์ดขึ้นแสดงทันทีใน 1 วินาที...")
                with open(history_file_path, "r", encoding="utf-8") as h_file:
                    saved_result = json.load(h_file)
                
                JOBS_DATA[job_id]["result"] = saved_result
                JOBS_DATA[job_id]["status"] = "completed"
                JOBS_DATA[job_id]["progress"] = 100
                return # สั่งตัดวงจรจบการทำงานทันที ไม่ต้องโหลดวิดีโอหรือรัน AI ใหม่

        JOBS_DATA[job_id]["progress"] = 10

        # 1. จัดการข้อมูลแหล่งสื่ออินพุต (Video Processing Phase)
        if is_youtube:
            video_path = os.path.join(CACHE_DIR, f"{unique_id}.mp4")
            logger.info(f"ดึงสัญญาณวิดีโอจาก YouTube ID: {unique_id}")
            if not os.path.exists(video_path):
                cmd = f'yt-dlp -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]" --ffmpeg-location "{CURRENT_DIR}" "{youtube_url}" -o "{video_path}"'
                subprocess.run(cmd, shell=True, check=True)
        else:
            if file_bytes and file_name:
                unique_id = f"local_{int(time.time())}_{re.sub(r'[^a-zA-Z0-9]', '', file_name)}"
                video_path = os.path.join(CACHE_DIR, f"{unique_id}.mp4")
                logger.info(f"บันทึกไฟล์วิดีโอจากระบบภายในเครื่อง: {video_path}")
                with open(video_path, "wb") as f:
                    f.write(file_bytes)

        JOBS_DATA[job_id]["progress"] = 30

        # 2. กระบวนการสกัดสัญญาณเสียง (Audio Extraction Phase)
        audio_path = os.path.join(CACHE_DIR, f"{unique_id}.mp3")
        if not os.path.exists(audio_path):
            logger.info(f"กำลังสกัดไฟล์เสียงแท้คุณภาพสูงแบบรักษาเนื้อเสียงครบถ้วน: {audio_path}")
            # 🎯 [แก้ไขต้นเหตุบั๊ก]: เอาแผ่นกรองความถี่ที่ตัดเสียงท้ายคลิปยาวๆ ทิ้งออก เปลี่ยนเป็นดึงสัญญาณเสียงสเตอริโอตรงๆ ป้องกันคำพูดหาย
            cmd_audio = f'ffmpeg -y -i "{video_path}" -vn -acodec libmp3lame -q:a 2 "{audio_path}"'
            subprocess.run(cmd_audio, shell=True, check=True)

        JOBS_DATA[job_id]["progress"] = 50

        # 3. ขบวนการแปลงวาจาเป็นข้อความจริงด้วยเทคนิค Strategic Audio Chunking
        logger.info("กำลังเปิดระบบสแกนสัญญาณเสียงและสั่งหั่นก้อนข้อมูลส่งวิเคราะห์...")
        
        # คัดลอกวิดีโอไปไว้ที่ Static เพื่อเรนเดอร์หน้าจอ
        dest_static_video = os.path.join(STATIC_DIR, f"{unique_id}.mp4")
        if os.path.exists(video_path) and not os.path.exists(dest_static_video):
            shutil.copy(video_path, dest_static_video)

        # เรียกใช้งาน Engine ถอดความระบบสลับโมดูลอัตโนมัติ 
        transcript_engine = TranscriptEngine()
        real_timeline = transcript_engine.transcribe_audio(audio_path)
        
        # รวบรวมข้อความส่งให้ AI สรุปโมดูลระดับบริหารต่อ
        formatted_text_lines = [f"{item['label']} - {item['text']}" for item in real_timeline]
        
        JOBS_DATA[job_id]["progress"] = 75

        # 4. ส่งวิเคราะห์ชุดโครงสร้าง 8 โมดูลหลักแบบ Dynamic พร้อมเปิดระบบตรวจสอบคำผิด (เกลากลุ่มซ้ำซ้อนออกแล้ว)
        logger.info("ส่งข้อมูลคำพูดจริงเข้าสู่กระบวนการวิเคราะห์ 8 โมดูลหลักยุทธศาสตร์...")
        
        strategic_prompt = (
            "คุณคือผู้เชี่ยวชาญด้านการวิเคราะห์สื่อระดับองค์กรและนักพิสูจ่น์อักษรภาษาไทยขั้นสูง "
            "ภารกิจสำคัญ: จงนำชุดข้อความถอดความตามช่วงเวลาที่ส่งไปให้ ซึ่งบางคำอาจสะกดผิด พิมพ์เพี้ยน หรือเป็นตัวอักษรไม่สมบูรณ์เนื่องจากระบบ Speech-to-Text "
            "จงช่วยเกลาและแก้ไขคำสะกดผิดเหล่านั้นให้เป็นประโยคภาษาไทยที่ถูกต้อง อ่านรู้เรื่อง และคงบริบทเดิมไว้ 100% ก่อนนำไปประมวลผลโมดูลระบบยุทธศาสตร์ "
            "โดยห้ามใช้ข้อมูลจำลอง ให้ดึงความหมายและคำสำคัญจากสิ่งที่คนในคลิปพูดจริงๆ เท่านั้น "
            "ตอบกลับเป็นข้อความ JSON ตามโครงสร้างนี้อย่างเคร่งครัด:\n"
            "{\n"
            "  \"summary\": [\"บทสรุปประเด็นหลักประโยคยาวที่ได้ใจความจากคลิปจริง 3-5 บรรทัด\"],\n"
            "  \"keyword_trending\": [{\"keyword\": \"คำสำคัญที่เจอในคลิป\", \"count\": จำนวนครั้งที่เจอ}],\n"
            "  \"sentiment_analysis\": [{\"time_range\": \"ช่วงเวลา\", \"sentiment\": \"อารมณ์\", \"trigger\": \"ปัจจัยกระตุ้น\", \"purpose\": \"เป้าหมายคำพูด\"}],\n"
            "  \"dominant_sentiment_summary\": \"บทสรุปภาพรวมบรรยากาศทางจิตวิทยาของคลิปนี้\",\n"
            "  \"video_chapters\": [{\"start_time_seconds\": วินาที, \"time_range_label\": \"ช่วงเวลา\", \"chapter_title\": \"ชื่อบทเรียนย่อยจากคลิปจริง\", \"sub_chapters\": [{\"start_time_seconds\": วินาที, \"time_range_label\": \"ช่วงเวลา\", \"sub_title\": \"หัวข้อย้อย\"}]}]\n"
            "}"
        )

        ai_analysis_data = ai_engine.generate_analytics(strategic_prompt, formatted_text_lines)

        # 5. คำนวณมาตรวัดเชิงสถิติตามข้อมูลคลิปจริงจากโครงสร้างฐาน Whisper / Dynamic Chunk
        total_sentences = len(real_timeline)
        total_words = sum(len(item['text'].split()) for item in real_timeline) or (len("".join([item['text'] for item in real_timeline])) // 3)
        
        # 🎯 ป้องกัน Error การหารด้วยศูนย์กรณีคลิปมีปัญหา
        last_time = real_timeline[-1]['time'] if (real_timeline and real_timeline[-1]['time'] > 0) else 0
        wpm_calc = str(int(total_words / (last_time / 60))) if last_time > 0 else "140"

        final_result = {
            "is_youtube": is_youtube,
            "real_youtube_url": real_url,
            "video_url": f"/static/{unique_id}.mp4",
            "model_used": "Gemini Multi-Model Dynamic Loop Engine",
            "timeline": real_timeline, 
            "summary": ai_analysis_data.get("summary", ["วิเคราะห์โครงสร้างเนื้อหาสำเร็จ"]),
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
            "recommendations": [
                {"title": f"วิเคราะห์เจาะลึก: {unique_id}", "url": real_url if is_youtube else "#", "thumbnail": f"https://img.youtube.com/vi/{unique_id}/0.jpg" if is_youtube else "/static/Logo_boy.png"}
            ],
            "video_counters": ai_analysis_data.get("video_chapters", []),
            "video_chapters": ai_analysis_data.get("video_chapters", [])
        }

        # 💾 [ระบบเซฟ Cache - อัปเกรดล็อคโฟลเดอร์เซฟตี้] บันทึกผลลัพธ์เก็บลงเครื่องทันทีก่อนส่งกลับหน้าจอ
        if is_youtube:
            # 🎯 ดักจับป้องกันบั๊กโฟลเดอร์หายระหว่างรันซ้ำซ้อน
            if not os.path.exists(HISTORY_DIR): 
                os.makedirs(HISTORY_DIR)
                
            history_file_path = os.path.join(HISTORY_DIR, f"{unique_id}.json")
            with open(history_file_path, "w", encoding="utf-8") as h_file:
                json.dump(final_result, h_file, ensure_ascii=False, indent=4)
            logger.info(f"💾 บันทึกผลการวิเคราะห์ของ ID: {unique_id} ลงโฟลเดอร์ประวัติเรียบร้อย")

        JOBS_DATA[job_id]["result"] = final_result
        JOBS_DATA[job_id]["status"] = "completed"
        JOBS_DATA[job_id]["progress"] = 100
        logger.info(f"✅ สำเร็จเสร็จสิ้น! ข้อมูลจากขบวนการลูกผสมถูกนำส่งเข้าระบบสำเร็จ")

    except Exception as e:
        logger.error(f"❌ เกิดข้อผิดพลาดในระบบวิเคราะห์ข้อมูลจริง {job_id}: {str(e)}")
        JOBS_DATA[job_id]["status"] = "failed"
        JOBS_DATA[job_id]["error"] = str(e)

# ----------------------------------------------------
# API ENDPOINTS (แผงรับส่งข้อมูลผ่าน Route เดิม)
# ----------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def serve_index_dashboard():
    index_path = os.path.join(TEMPLATES_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h3>ไม่พบไฟล์ index.html ในโฟลเดอร์ templates</h3>", status_code=404)

@app.post("/process")
@app.post("/submit_analysis")
async def handle_analysis_submission(
    background_tasks: BackgroundTasks,
    mediaMode: Optional[str] = Form(None),
    mode: Optional[str] = Form(None),
    youtubeUrl: Optional[str] = Form(None),
    youtube_url: Optional[str] = Form(None),
    localFile: Optional[UploadFile] = File(None),
    file: Optional[UploadFile] = File(None)
):
    final_mode = mediaMode if mediaMode else mode
    final_url = youtubeUrl if youtubeUrl else youtube_url
    final_file = localFile if localFile else file

    if not final_mode:
        return JSONResponse(content={"error": "Missing mode parameter"}, status_code=400)

    job_id = f"job_{int(time.time())}"
    JOBS_DATA[job_id] = {"status": "queued", "progress": 0, "result": None}
    logger.info(f"ลงทะเบียนคำขอผ่าน Route ผสานสัญญาณจริง รหัสงาน: {job_id}")

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
        file_name
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

if __name__ == "__main__":
    import uvicorn
    logger.info("กำลังสตาร์ทระบบ YAMASEE Transcript Real Platform Systems...")
    uvicorn.run("main.py:app", host="127.0.0.1", port=8000, reload=True)