from google import genai
import json
import time

from utils.logger import logger

class AIAnalysisEngine:
    def __init__(self, api_key: str, preferred_model: str = None):
        self.client = genai.Client(api_key=api_key)
        self.models = ["gemini-3.5-flash", "gemini-2.5-flash", "gemini-3-flash", "gemini-2.5-flash-lite"]
        #,"gemini-3.1-flash-lite"
        if preferred_model:
            if preferred_model in self.models:
                self.models.remove(preferred_model)
            self.models.insert(0, preferred_model)

    def generate_analytics(self, prompt: str, text_array: list):
        """จัดการ Logic การเรียก API หลายโมเดลแบบวนลูป เพื่อแก้ปัญหาโควตา"""
        for model_name in self.models:
            for attempt in range(5):
                try:
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=[prompt, json.dumps(text_array, ensure_ascii=False)],
                        config={'response_mime_type': 'application/json', 'temperature': 0.0}
                    )
                    return json.loads(response.text)
                except Exception as e:
                    if attempt < 4:
                        time.sleep(1.5)
        return None
