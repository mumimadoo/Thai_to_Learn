from engines.video_engine import VideoEngine

def test_extract_video_id():
    engine = VideoEngine()
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    video_id = engine.extract_unique_video_id(url)
    assert "youtube_" in video_id
    print("✅ Test ผ่าน: ดึง Video ID ถูกต้อง!")

# รันด้วยคำสั่ง: pytest tests/test_video_engine.py