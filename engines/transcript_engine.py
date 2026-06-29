import os
import re
import json
import time
import subprocess
from google import genai

class TranscriptEngine:
    def __init__(self, model_size: str = "default"):
        api_key = os.getenv("GEMINI_API_KEY")
        self.client = genai.Client(api_key=api_key)
        
        self.model_pool = [
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-3.5-flash",
            "gemini-3-flash",
            "gemini-3.1-flash-lite"
        ]

    def get_audio_duration(self, audio_path: str) -> float:
        """คำนวณความยาวไฟล์เสียงทั้งหมดเป็นวินาทีอย่างแม่นยำสูงสุด"""
        cmd = f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{audio_path}"'
        try:
            result = subprocess.check_output(cmd, shell=True).decode('utf-8').strip()
            if result:
                return float(result)
        except Exception as e:
            print(f"⚠️ ffprobe ขัดข้อง กำลังใช้ระบบสแกนสำรอง: {str(e)}")
            
        # ป้องกันวิดีโอยาวโดนตัดจบที่ 10 นาที ขยายค่าสำรองเผื่อไว้สูงสุด 10 ชั่วโมง (36000 วินาที)
        return 36000.0

    def format_to_strategic_label(self, total_seconds: float) -> str:
        """⚡ [ฟังก์ชันใหม่]: แปลงวินาทีสะสมจริงให้เป็นป้ายกำกับระบบชั่วโมง [HH:MM:SS] หรือ [MM:SS]"""
        total_seconds = max(0.0, total_seconds)
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        
        if hours > 0:
            return f"[{hours:02d}:{minutes:02d}:{seconds:02d}]"
        return f"[{minutes:02d}:{seconds:02d}]"

    def transcribe_audio(self, audio_path: str) -> list:
        """
        สถาปัตยกรรม Dynamic Timestamping Engine:
        หั่นก้อนพอดีคำ ป้องกัน AI หลอนเขียนเอง และให้ AI ระบุพิกัดเวลาจริงตามคลิป
        """
        cache_dir = os.path.dirname(audio_path)
        unique_stamp = int(time.time())
        total_duration = self.get_audio_duration(audio_path)
        print(f"⏱️ ตรวจพบสัญญาณเสียงความยาวรวม: {total_duration} วินาที")
        
        chunk_length = 60.0  # ขยับมาที่ 1 นาทีเพื่อให้ได้ใจความสมบูรณ์ ลดอาการมโนของ AI
        timeline_data = []
        current_start = 0.0
        index = 1

        while current_start < total_duration:
            current_end = current_start + chunk_length
            if current_end > total_duration:
                current_end = total_duration
                
            duration_to_cut = current_end - current_start
            if duration_to_cut <= 1.0:
                break
                
            chunk_file = os.path.join(cache_dir, f"time_chunk_{unique_stamp}_{index:03d}.mp3")
            
            # สกัดก้อนเสียงแยกตามเวลาจริง
            cmd_cut = f'ffmpeg -y -ss {current_start} -i "{audio_path}" -t {duration_to_cut} -c copy "{chunk_file}"'
            try:
                subprocess.run(cmd_cut, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                print(f"❌ ffmpeg ไม่สามารถตัดก้อนเสียงที่ {index} ได้: {str(e)}")
                break
            
            # ตรวจสอบว่าไฟล์ถูกสร้างจริงและมีขนาดก่อนอัปโหลด
            if not os.path.exists(chunk_file) or os.path.getsize(chunk_file) < 100:
                break
                
            try:
                uploaded_chunk = self.client.files.upload(file=chunk_file)
            except Exception as e:
                print(f"❌ อัปโหลดไฟล์ก้อนที่ {index} ไปยัง Google API ล้มเหลว: {str(e)}")
                current_start += chunk_length
                index += 1
                continue
            
            # 🎯 คงโครงสร้างคีย์หลัก ("time", "label", "text") ไว้ตามเดิม แต่เพิ่มเงื่อนไขกำชับให้บวกและจัดฟอร์แมตเวลาให้ถูกต้อง
            prompt = (
                f"คุณคือผู้เชี่ยวชาญด้านการถอดความเสียงภาษาไทย หน้าที่ของคุณคือฟังไฟล์เสียงสั้นความยาวไม่เกิน 60 วินาทีนี้อย่างละเอียด "
                f"จงแกะคำพูดคำต่อคำออกมาให้ถูกต้อง และแยกข้อความออกเป็นประโยคสั้นๆ กระชับ "
                f"พร้อมระบุพิกัดเวลากำบัตฟิลด์ 'time' เป็นตัวเลขทศวินาทีรวมหลังจากบวกค่าเวลาเริ่มต้นของก้อนนี้เข้าไปแล้ว "
                f"⚠️ ค่าเวลาเริ่มต้นที่คุณต้องนำไปบวกเพิ่มในทุกประโยคคือ: {current_start} วินาที\n\n"
                f"ตอบกลับเป็นรูปแบบ JSON Array เท่านั้น ห้ามมีข้อความอื่นหรือแท็ก Markdown ปน โครงสร้างดังนี้:\n"
                f"[{{\"time\": วินาทีรวมหลังจากบวกค่าเริ่มต้นแล้ว, \"label\": \"[นาที:วินาที] หรือ [ชั่วโมง:นาที:วินาที]\", \"text\": \"คำพูดที่ได้ยินจริง\"}}]"
            )
            
            chunk_json_text = ""
            for model_name in self.model_pool:
                try:
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=[uploaded_chunk, prompt],
                        config={"response_mime_type": "application/json"} # ล็อกข้อความตอบกลับเป็น JSON
                    )
                    chunk_json_text = response.text.strip()
                    if chunk_json_text:
                        break
                except:
                    continue
            
            # แปลงผลลัพธ์ JSON รวมเข้าสู่ไทม์ไลน์หลัก
            if chunk_json_text:
                try:
                    cleaned_json = chunk_json_text
                    if cleaned_json.startswith("```json"):
                        cleaned_json = cleaned_json[7:]
                    if cleaned_json.endswith("```"):
                        cleaned_json = cleaned_json[:-3]
                    cleaned_json = cleaned_json.strip()

                    chunk_data = json.loads(cleaned_json)
                    if isinstance(chunk_data, list):
                        for item in chunk_data:
                            if "time" in item:
                                # 🎯 [ระบบคัดกรองระเบียบเวลาหลังบ้าน]: นำค่าเวลาสะสมจริงมาเข้าฟังก์ชันเพื่อล็อกป้ายกำกับแก้ปัญหา AI ใส่ฟอร์แมตมั่ว
                                absolute_seconds = float(item["time"])
                                strategic_label = self.format_to_strategic_label(absolute_seconds)
                                
                                item["label"] = strategic_label
                                item["time"] = round(absolute_seconds, 2)
                                
                                print(f"✅ ดึงพิกัดจริง {item.get('label', '')} -> {item.get('text', '')}")
                                timeline_data.append(item)
                except Exception as e:
                    print(f"⚠️ แปลงผล JSON ของก้อนที่ {index} ไม่สำเร็จเนื่องจากฟอร์แมตคลาดเคลื่อน: {str(e)}")

            try:
                self.client.files.delete(name=uploaded_chunk.name)
                os.remove(chunk_file)
            except:
                pass
            
            current_start += chunk_length
            index += 1

        # เรียงลำดับข้อมูลตามพิกัดเวลาจริงก่อนส่งขึ้นแสดงผลบนหน้าจอ
        timeline_data = sorted(timeline_data, key=lambda x: x["time"])
        return timeline_data