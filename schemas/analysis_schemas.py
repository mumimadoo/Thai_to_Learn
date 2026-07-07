from pydantic import BaseModel, Field
from typing import List

class KeywordCount(BaseModel):
    keyword: str = Field(description="คำสำคัญแก่นหลักของเนื้อหา")
    count: int = Field(description="จำนวนครั้งที่พบคำนี้")

class SentimentInterval(BaseModel):
    time_range: str = Field(description="ช่วงเวลา เช่น 0-2 นาที")
    emotion: str = Field(description="อารมณ์หลัก")
    key_trigger: str = Field(description="ตัวกระตุ้น")
    purpose: str = Field(description="จุดประสงค์")

class SubChapter(BaseModel):
    start_time_seconds: int
    time_range_label: str
    sub_title: str

class VideoChapter(BaseModel):
    start_time_seconds: int
    time_range_label: str
    chapter_title: str
    sub_chapters: List[SubChapter]

class PureTranscription(BaseModel):
    transcription: List[str]

class AnalyticsMetrics(BaseModel):
    summary: List[str]
    keyword_trending: List[KeywordCount]
    sentiment_analysis: List[SentimentInterval]
    dominant_sentiment_summary: str
    recommended_keywords: List[str]
    video_chapters: List[VideoChapter]