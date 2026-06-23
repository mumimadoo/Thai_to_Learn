import os
import re
import json
import time
import shutil
import subprocess
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from google import genai
from pydantic import BaseModel, Field
from typing import List, Optional

app = FastAPI()

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(CURRENT_DIR, "static")
TEMPLATES_DIR = os.path.join(CURRENT_DIR, "templates")
CACHE_DIR = r"E:\Project_write\WeFool\cache"

if not os.path.exists(STATIC_DIR): os.makedirs(STATIC_DIR)
if not os.path.exists(CACHE_DIR): os.makedirs(CACHE_DIR)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/templates", StaticFiles(directory=TEMPLATES_DIR), name="templates")

GEMINI_API_KEY = "AQ.Ab8RN6KuBL7upvxmFlJlUxrlR_LHVrU3s-dsxLVNb9xzXPC0GA"

JOBS_DATA = {}

class KeywordCount(BaseModel):
    keyword: str = Field(description="คำสำคัญแก่นหลักของเนื้อหา (ห้ามเอาคำสร้อยขยะ)")
    count: int = Field(description="จำนวนครั้งที่พบคำนี้")

class SentimentInterval(BaseModel):
    time_range: str = Field(description="ช่วงเวลา เช่น 0-2 นาที, 2-5 นาที")
    sentiment: str = Field(description="อีโมจิและคำระบุอารมณ์ เช่น '😊 Positive'")

class VideoChapter(BaseModel):
    start_time_seconds: int = Field(description="วินาทีเริ่มต้นที่เป็นตัวเลขจำนวนเต็มสำหรับใช้กระโดดวาร์ป เช่น 15")
    time_range_label: str = Field(description="ป้ายแสดงช่วงเวลาให้มนุษย์อ่าน เช่น [00:15]")
    chapter_title: str = Field(description="สรุปประเด็นใจความสำคัญในช่วงเวลานั้น")

class VideoAnalysis(BaseModel):
    transcription: List[str] = Field(description="ถอดความคำต่อคำ รูปแบบ '[MM:SS] ข้อความพูด' (สรุปประโยคให้สั้นกระชับต่อแถว ห้ามพ่นคำขยะยืดยาวป้องกัน JSON ขาด)")
    summary: List[str] = Field(description="สรุปเนื้อหายุทธศาสตร์ภาษาไทย 3 ข้อหลัก")
    sentence_count: int = Field(description="จำนวนประโยคทั้งหมด")
    topic_count: int = Field(description="จำนวนประเด็นหลัก")
    keyword_trending: List[KeywordCount] = Field(description="คำยอดฮิตแก่นหลัก 3-5 อันดับแรก")
    sentiment_analysis: List[SentimentInterval] = Field(description="วิเคราะห์อารมณ์ตามช่วงเวลา")
    dominant_sentiment_summary: str = Field(description="บทวิเคราะห์ภาพรวมอารมณ์รวม")
    recommended_keywords: List[str] = Field(description="คีย์เวิร์ดเพื่อนำไปค้นหาคลิปแนะนำ 1 คำ")
    video_chapters: List[VideoChapter] = Field(description="แบ่งกลุ่มช่วงเวลาของเนื้อหาในคลิปแยกเป็นบท ๆ")

@app.get("/", response_class=HTMLResponse)
async def index():
    template_path = os.path.join(TEMPLATES_DIR, "index.html")
    with open(template_path, "r", encoding="utf-8") as f: return f.read()

def extract_unique_video_id(url: str) -> str:
    if "tiktok.com" in url:
        match = re.search(r'/video/(\d+)', url)
        if match: return f"tiktok_{match.group(1)}"
        return f"tiktok_hash_{abs(hash(url))}"
    match = re.search(r'(youtu\.be\/|v\/|u\/\w\/|embed\/|watch\?v=|\&v=)([^#\&\?]*)', url)
    if match and len(match.group(2)) == 11:
        return f"youtube_{match.group(2)}"
    return f"media_hash_{abs(hash(url))}"

def get_real_youtube_search_results(keyword: str) -> List[dict]:
    try:
        cmd = ["./yt-dlp.exe", f"ytsearch4:{keyword}", "--dump-json", "--flat-playlist"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding="utf-8", errors="ignore")
        cards = []
        for line in result.stdout.splitlines():
            if not line.strip(): continue
            video_data = json.loads(line)
            v_id = video_data.get("id")
            if v_id and len(v_id) == 11:
                cards.append({
                    "title": video_data.get("title", "คลิปที่เกี่ยวข้อง"),
                    "url": f"https://www.youtube.com/watch?v={v_id}",
                    "thumbnail": f"https://img.youtube.com/vi/{v_id}/mqdefault.jpg"
                })
        return cards[:4]
    except: return []

def convert_seconds_to_label(total_seconds: int) -> str:
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if hours > 0:
        return f"[{hours:02d}:{minutes:02d}:{seconds:02d}]"
    return f"[{minutes:02d}:{seconds:02d}]"

# 🛠️ ฟังก์ชันนวัตกรรมอัจฉริยะ: ค้นหาความเงียบเพื่อหาจุดตัด Chunk ที่ไม่ผ่ากลางประโยคคำพูด
def analyze_silence_timestamps(audio_path: str, total_duration: int) -> List[tuple]:
    try:
        # สแกนหาช่วงที่เงียบเกิน 0.4 วินาที และเสียงเบากว่า -30dB
        cmd = ["./ffmpeg.exe", "-i", audio_path, "-af", "silencedetect=noise=-30dB:d=0.4", "-f", "null", "-"]
        result = subprocess.run(cmd, capture_output=True, text=True, errors="ignore")
        
        # แกะพิกัดความเงียบจาก Log ของ FFmpeg
        silence_ends = []
        for line in result.stderr.splitlines():
            if "silence_end" in line:
                match = re.search(r"silence_end:\s*([\d.]+)", line)
                if match:
                    silence_ends.append(float(match.group(1)))
                    
        # สร้าตารางรอยต่อตามจริงผสมกฎ Forced Split ไม่เกิน 3 นาที (180 วินาที)
        chunks_ranges = []
        start_time = 0.0
        max_chunk_len = 180.0 # ล็อกเพดานไม่ให้แต่ละกล่องยาวทะลักล้นจอเกิน 3 นาที
        
        while start_time < total_duration:
            target_end = start_time + max_chunk_len
            if target_end >= total_duration:
                chunks_ranges.append((int(start_time), int(total_duration)))
                break
                
            # ค้นหาจุดเว้นวรรคหายใจที่เงียบและใกล้ลิมิต 3 นาทีที่สุด
            best_cut = None
            for s_end in silence_ends:
                if start_time < s_end <= target_end:
                    best_cut = s_end
            
            if best_cut and (best_cut - start_time) > 10: # ป้องกันสับชิ้นเล็กเกินไป (ต้องยาวอย่างน้อย 10 วิ)
                actual_cut = int(best_cut)
            else:
                actual_cut = int(target_end) # เคสพูดน้ำไหลไฟดับ บังคับตัดที่ 3 นาทีทันที
                
            chunks_ranges.append((int(start_time), actual_cut))
            start_time = actual_cut
            
        return chunks_ranges
    except:
        # กรณีระเบิดหรือขัดข้อง ให้ถอยกลับไปใช้ลอจิกพื้นฐานสับทุก 3 นาทีธรรมดาเพื่อไม่ให้งานล่ม
        ranges = []
        for s in range(0, total_duration, 180):
            ranges.append((s, min(s + 180, total_duration)))
        return ranges

def async_video_worker(job_id: str, mode: str, youtube_url: Optional[str], file_bytes: Optional[bytes], file_name: Optional[str]):
    global JOBS_DATA
    JOBS_DATA[job_id]["progress"] = 10
    is_tiktok_url = youtube_url and "tiktok.com" in youtube_url
    timestamp_nonce = job_id
    
    local_audio_path = os.path.join(STATIC_DIR, f"exec_audio_{timestamp_nonce}.mp3")
    local_video_path = os.path.join(STATIC_DIR, f"exec_video_{timestamp_nonce}.mp4")
    created_chunks_files = [] 

    final_model_marker = "gemini-3.5-flash"

    try:
        if mode == "youtube":
            JOBS_DATA[job_id]["progress"] = 20
            video_format_option = "best" if is_tiktok_url else "bv*[height<=480][ext=mp4]+ba[ext=m4a]/b[height<=480][ext=mp4]/best"
            raw_output_template = os.path.join(STATIC_DIR, f"exec_raw_{timestamp_nonce}.%(ext)s")

            subprocess.run(["./yt-dlp.exe", "--cookies-from-browser", "edge", "-f", video_format_option, "--ffmpeg-location", "./", "-o", raw_output_template, youtube_url], capture_output=True)
            
            raw_tmp_path = None
            for f_name in os.listdir(STATIC_DIR):
                if f_name.startswith(f"exec_raw_{timestamp_nonce}"):
                    raw_tmp_path = os.path.join(STATIC_DIR, f_name)
                    break
            
            if not raw_tmp_path:
                subprocess.run(["./yt-dlp.exe", "-f", video_format_option, "--ffmpeg-location", "./", "-o", raw_output_template, youtube_url], capture_output=True)
                for f_name in os.listdir(STATIC_DIR):
                    if f_name.startswith(f"exec_raw_{timestamp_nonce}"):
                        raw_tmp_path = os.path.join(STATIC_DIR, f_name)
                        break

            if not raw_tmp_path or not os.path.exists(raw_tmp_path):
                JOBS_DATA[job_id] = {"status": "failed", "progress": 0, "error": "ดาวน์โหลดมีเดียล้มเหลว"}
                return

            JOBS_DATA[job_id]["progress"] = 35
            subprocess.run(["./ffmpeg.exe", "-y", "-i", raw_tmp_path, "-vcodec", "libx264", "-acodec", "aac", "-pix_fmt", "yuv420p", "-preset", "ultrafast", local_video_path], capture_output=True)
            subprocess.run(["./ffmpeg.exe", "-y", "-i", local_video_path, "-vn", "-acodec", "libmp3lame", "-q:a", "4", "-af", "aresample=async=1", local_audio_path], capture_output=True)
            
            if not os.path.exists(local_audio_path) or os.path.getsize(local_audio_path) == 0:
                subprocess.run(["./ffmpeg.exe", "-y", "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100", "-t", "10", "-acodec", "libmp3lame", local_audio_path], capture_output=True)

            try: os.remove(raw_tmp_path)
            except: pass
            upload_target = local_audio_path
        else:
            JOBS_DATA[job_id]["progress"] = 25
            if not file_bytes:
                JOBS_DATA[job_id] = {"status": "failed", "progress": 0, "error": "ไม่พบไฟล์มีเดียต้นฉบับ"}
                return
            with open(local_video_path, "wb") as b: b.write(file_bytes)
            subprocess.run(["./ffmpeg.exe", "-y", "-i", local_video_path, "-vn", "-acodec", "libmp3lame", "-q:a", "4", local_audio_path], capture_output=True)
            if not os.path.exists(local_audio_path) or os.path.getsize(local_audio_path) == 0:
                subprocess.run(["./ffmpeg.exe", "-y", "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100", "-t", "10", "-acodec", "libmp3lame", local_audio_path], capture_output=True)
            upload_target = local_audio_path

        JOBS_DATA[job_id]["progress"] = 45
        probe_cmd = ["./ffprobe.exe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", upload_target]
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, errors="ignore")
        try:
            total_duration_seconds = int(float(probe_result.stdout.strip()))
        except:
            total_duration_seconds = 600

        # 🔥 เรียกใช้งานระะบบวิเคราะห์คลื่นเสียงเพื่อสับตามจุดเว้นหายใจจริง (Silence-Based Partitioning)
        chunks_ranges = analyze_silence_timestamps(upload_target, total_duration_seconds)
        chunks_count = len(chunks_ranges)

        combined_transcription = []
        combined_timeline = []
        combined_summary = []
        combined_keywords_raw = {}
        combined_sentiment_table = []
        combined_video_chapters = []
        dominant_sentiments_pool = []
        
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        # 🎯 Super Prompt ร่างสุดยอดสมบูรณ์แบบ (v3): ล็อกบทบาท ดักคลิป TikTok คุมความยาวกล่องข้อความหน้าเว็บไม่ให้ทะลักล้น
        space_prompt = (
            "========================================================================\n"
            "CRITICAL DIRECTIVE: YOU MUST STRICTLY FOLLOW ALL FOUR RULES BELOW WITH ZERO EXCEPTIONS.\n"
            "========================================================================\n\n"
            
            "RULE 1: ROLE-BASED CONTROL (THE EXPERT)\n"
            "- You are an elite, forensic-grade audio transcription engine and media analysis system.\n"
            "- Your absolute mission is to convert the audio chunk into Thai text with 100% literal accuracy.\n\n"
            
            "RULE 2: CONTEXT FEEDING (TIKTOK/SHORTS REALITY)\n"
            "- This audio contains fast-paced speech, informal language, rapid slang, and intense jump cuts (TikTok style).\n"
            "- Expect sentences to be spoken quickly. You must actively listen through background noise to capture the speech.\n\n"
            
            "RULE 3: NEGATIVE CONSTRAINTS & TIMELINE FORMATTING (SHORT & SCAN_READABLE)\n"
            "- Transcribe EVERY single syllable and word. Absolutely ZERO summarization or omission is allowed.\n"
            "- CRITICAL FOR TIMELINE VIEW: Format each line precisely as: '[MM:SS] Text content'.\n"
            "- To prevent text from overflowing the UI boxes, EACH individual line MUST be short and concise (maximum 1-2 sentences per timestamp).\n"
            "- If the speech within a specific timestamp is long, you MUST break it down into multiple continuous lines with advancing timestamps.\n\n"
            
            "RULE 4: JSON STRUCTURE SECURITY (NO PARSING FAILURES)\n"
            "- You MUST output a strictly valid, well-formed JSON object matching the 'VideoAnalysis' schema exactly.\n"
            "- Ensure all inner text values are cleanly escaped. There must be NO unescaped quotes or trailing commas.\n"
            "- Deliver the absolute truth of the audio without cutting off mid-JSON."
        )

        for index, (start_pos, end_pos) in enumerate(chunks_ranges):
            JOBS_DATA[job_id]["progress"] = int(50 + (index / chunks_count) * 40)
            chunk_duration = end_pos - start_pos
            
            chunk_file_path = os.path.join(STATIC_DIR, f"chunk_{job_id}_{index}.mp3")
            subprocess.run([
                "./ffmpeg.exe", "-y", "-ss", str(start_pos), "-t", str(chunk_duration),
                "-i", upload_target, "-acodec", "copy", chunk_file_path
            ], capture_output=True)

            if not os.path.exists(chunk_file_path) or os.path.getsize(chunk_file_path) == 0:
                continue
                
            created_chunks_files.append(chunk_file_path)

            audio_cloud = client.files.upload(file=chunk_file_path, config={"mime_type": "audio/mp3"})
            while audio_cloud.state.name == "PROCESSING":
                time.sleep(2)
                audio_cloud = client.files.get(name=audio_cloud.name)

           
            response = None
            
            
            for attempt in range(5):
                try:
                    response = client.models.generate_content(
                        model="gemini-3.5-flash", contents=[audio_cloud, space_prompt],
                        config={'response_mime_type': 'application/json', 'response_schema': VideoAnalysis, 'temperature': 0.0}
                    )
                    final_model_marker = "gemini-3.5-flash [สถาปัตยกรรม Smart-Silence]"
                    break
                except Exception as e1:
                    print(f"⚠️ gemini-3.5-flash พยายามครั้งที่ {attempt+1} ขัดข้อง: {str(e1)}")
                    if attempt < 4: time.sleep(2)
            
            # --- ชั้นที่ 2: หากด่านแรกไม่รอด ขยับมาดวลกับ gemini-2.5-flash อีก 5 รอบ ---
            if response is None:
                print("🚨 gemini-3.5-flash ล้มเหลวครบ 5 รอบ -> ดรอปมาใช้ชั้นรองสายตรง")
                for attempt in range(5):
                    try:
                        response = client.models.generate_content(
                            model="gemini-2.5-flash", contents=[audio_cloud, space_prompt],
                            config={'response_mime_type': 'application/json', 'response_schema': VideoAnalysis, 'temperature': 0.0}
                        )
                        final_model_marker = "gemini-2.5-flash [โหมดกู้ชีพชั้นที่ 1]"
                        break
                    except Exception as e2:
                        print(f"⚠️ gemini-2.5-flash พยายามครั้งที่ {attempt+1} ขัดข้อง: {str(e2)}")
                        if attempt < 4: time.sleep(4)
            
            # --- ชั้นที่ 3: ปราการสุดท้าย ตื้อเอาชีวิตรอดกับ gemini-2.5-flash-lite อีก 5 รอบ ---
            if response is None:
                print("🚨 gemini-2.5-flash ล้มเหลวครบ 5 รอบ -> ถอยร่นมาพึ่งพาหน่วยกู้ชีพด่านสุดท้าย")
                for attempt in range(5):
                    try:
                        response = client.models.generate_content(
                            model="gemini-2.5-flash-lite", contents=[audio_cloud, space_prompt],
                            config={'response_mime_type': 'application/json', 'response_schema': VideoAnalysis, 'temperature': 0.0}
                        )
                        final_model_marker = "gemini-2.5-flash-lite [โหมดกู้ชีพด่านสุดท้าย]"
                        break
                    except Exception as e3:
                        print(f"⚠️ gemini-2.5-flash-lite พยายามครั้งที่ {attempt+1} ขัดข้อง: {str(e3)}")
                        if attempt < 4: time.sleep(2)

            if response is None:
                raise Exception("เซิร์ฟเวอร์ Google ไม่ตอบสนองถาวรหลังพยายามกู้คืนระบบคิว Smart-Silence 15 ครั้ง")

            res_data = json.loads(response.text)

            # ดึงข้อมูลและคำนวณพิกัดเวลาแบบสัมบูรณ์ให้สอดคล้องกับตัววิดีโอ
            raw_trans_list = res_data.get("transcription", [])
            for line in raw_trans_list:
                match = re.search(r'(\[\d{2}:\d{2}\])(.*)', line)
                if match:
                    ts_str = match.group(1).strip('[]')
                    parts = ts_str.split(':')
                    chunk_secs = int(parts[0]) * 60 + int(parts[1])
                    absolute_seconds = start_pos + chunk_secs
                    label_absolute = convert_seconds_to_label(absolute_seconds)
                    clean_text = match.group(2).strip()
                    
                    combined_transcription.append(f"{label_absolute} {clean_text}")
                    combined_timeline.append({"time": absolute_seconds, "text": clean_text, "label": label_absolute})

            if res_data.get("summary"):
                combined_summary.extend(res_data.get("summary", []))

            for k_item in res_data.get("keyword_trending", []):
                kw = k_item.get("keyword") if isinstance(k_item, dict) else getattr(k_item, "keyword", "")
                cnt = k_item.get("count", 0) if isinstance(k_item, dict) else getattr(k_item, "count", 0)
                if kw: combined_keywords_raw[kw] = combined_keywords_raw.get(kw, 0) + cnt

            for s_item in res_data.get("sentiment_analysis", []):
                t_range = s_item.get("time_range") if isinstance(s_item, dict) else getattr(s_item, "time_range", "")
                sent = s_item.get("sentiment") if isinstance(s_item, dict) else getattr(s_item, "sentiment", "")
                if t_range and sent:
                    combined_sentiment_table.append({"time_range": f"พาร์ทที่ {index+1} ({t_range})", "sentiment": sent})

            if res_data.get("dominant_sentiment_summary"):
                dominant_sentiments_pool.append(res_data.get("dominant_sentiment_summary"))

            for ch_item in res_data.get("video_chapters", []):
                ch_secs = ch_item.get("start_time_seconds") if isinstance(ch_item, dict) else getattr(ch_item, "start_time_seconds", 0)
                ch_title = ch_item.get("chapter_title") if isinstance(ch_item, dict) else getattr(ch_item, "chapter_title", "")
                
                absolute_ch_secs = start_pos + ch_secs
                combined_video_chapters.append({
                    "start_time_seconds": absolute_ch_secs,
                    "time_range_label": convert_seconds_to_label(absolute_ch_secs),
                    "chapter_title": f"[ตอนย่อยที่ {index+1}] {ch_title}"
                })

            try: client.files.delete(name=audio_cloud.name)
            except: pass

        for f_to_delete in created_chunks_files:
            try: os.remove(f_to_delete)
            except: pass

        sorted_kws = sorted(combined_keywords_raw.items(), key=lambda x: x[1], reverse=True)[:5]
        final_keywords_chart = [{"keyword": k, "count": c} for k, c in sorted_kws]
        search_keyword = sorted_kws[0][0] if sorted_kws else "เทคโนโลยี"
        
        real_recommendations = get_real_youtube_search_results(search_keyword)
        actual_minutes = max(int(total_duration_seconds / 60), 1)
        computed_word_count = sum(len(x["text"]) for x in combined_timeline) // 2

        final_package = {
            "transcript": combined_transcription, "timeline": combined_timeline, "summary": combined_summary[:3] if combined_summary else ["สกัดข้อสรุปวิดีโอเรียบร้อย"],
            "model_used": final_model_marker, "audio_url": f"/static/exec_audio_{timestamp_nonce}.mp3", "video_url": f"/static/exec_video_{timestamp_nonce}.mp4",
            "real_youtube_url": youtube_url if mode == "youtube" else "", "is_youtube": (mode == "youtube" and not is_tiktok_url),
            "recommendations": real_recommendations,
            "telemetry": {"duration": f"{actual_minutes} นาที", "words": f"{computed_word_count:,} คำ", "sentences": len(combined_timeline), "wpm": int(computed_word_count/actual_minutes) if actual_minutes > 0 else 100, "topics": max(len(combined_video_chapters), 4)},
            "keywords_chart": final_keywords_chart, "sentiment_table": combined_sentiment_table, "dominant_sentiment": dominant_sentiments_pool[0] if dominant_sentiments_pool else "เป็นกลางสอดคล้องกันดี", "video_chapters": combined_video_chapters
        }

        if mode == "youtube" and youtube_url:
            with open(os.path.join(CACHE_DIR, f"cache_{extract_unique_video_id(youtube_url)}.json"), "w", encoding="utf-8") as f:
                json.dump(final_package, f, ensure_ascii=False, indent=4)

        JOBS_DATA[job_id] = {"status": "completed", "progress": 100, "result": final_package}

    except Exception as e:
        for f_to_delete in created_chunks_files:
            try: os.remove(f_to_delete)
            except: pass
        JOBS_DATA[job_id] = {"status": "failed", "progress": 0, "error": f"ระบบคิวขัดข้องหลังรันระบบ Smart-Silence: {str(e)}"}

@app.post("/process")
async def process_media(
    bg_tasks: BackgroundTasks, mode: str = Form(...),
    youtube_url: Optional[str] = Form(None), file: Optional[UploadFile] = File(None)
):
    if mode == "youtube" and youtube_url:
        video_identity_id = extract_unique_video_id(youtube_url)
        cache_file_name = f"cache_{video_identity_id}.json"
        cache_full_path = os.path.join(CACHE_DIR, cache_file_name)
        if os.path.exists(cache_full_path):
            with open(cache_full_path, "r", encoding="utf-8") as f: return JSONResponse(content=json.load(f))

    job_id = str(int(time.time()))
    JOBS_DATA[job_id] = {"status": "processing", "progress": 5, "result": None}
    
    file_bytes = None
    file_name = None
    if mode == "file" and file:
        file_bytes = await file.read()
        file_name = file.filename

    bg_tasks.add_task(async_video_worker, job_id, mode, youtube_url, file_bytes, file_name)
    return {"job_id": job_id, "queued": True}

@app.get("/job_status/{job_id}")
async def get_job_status(job_id: str):
    if job_id not in JOBS_DATA: return JSONResponse({"status": "not_found", "progress": 0}, status_code=404)
    return JOBS_DATA[job_id]

@app.post("/translate_timeline")
async def translate_timeline(target_lang: str = Form(...), transcript_text: str = Form(...)):
    client = genai.Client(api_key=GEMINI_API_KEY)
    text_array = [line.strip() for line in transcript_text.split("\n") if line.strip()]
    
    prompt = f"Translate this array of text into '{target_lang}'. Return strictly a raw JSON array of strings."
    
    response = None
    for attempt in range(5):
        try:
            response = client.models.generate_content(
                model="gemini-3.5-flash", contents=[prompt, json.dumps(text_array, ensure_ascii=False)], config={'response_mime_type': 'application/json', 'temperature': 0.0}
            )
            return {"translated_lines": json.loads(response.text)}
        except Exception as e1:
            print(f"⚠️ แปลภาษาด้วย 3.5-flash รอบที่ {attempt+1} ขัดข้อง: {str(e1)}")
            if attempt < 4: time.sleep(2)
            
    if response is None:
        for attempt in range(5):
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash", contents=[prompt, json.dumps(text_array, ensure_ascii=False)], config={'response_mime_type': 'application/json', 'temperature': 0.0}
                )
                return {"translated_lines": json.loads(response.text)}
            except Exception as e2:
                print(f"⚠️ แปลภาษาด้วย 2.5-flash รอบที่ {attempt+1} ขัดข้อง: {str(e2)}")
                if attempt < 4: time.sleep(2)
                
    if response is None:
        for attempt in range(5):
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash-lite", contents=[prompt, json.dumps(text_array, ensure_ascii=False)], config={'response_mime_type': 'application/json', 'temperature': 0.0}
                )
                return {"translated_lines": json.loads(response.text)}
            except Exception as e3:
                print(f"⚠️ แปลภาษาด้วย 2.5-flash-lite รอบที่ {attempt+1} ขัดข้อง: {str(e3)}")
                if attempt < 4: time.sleep(2)

    return {"translated_lines": text_array}
