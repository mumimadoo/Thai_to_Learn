import subprocess
from engines.video_engine import VideoEngine

def test_extract_video_id():
    engine = VideoEngine()
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    video_id = engine.extract_unique_video_id(url)
    assert "youtube_" in video_id
    print("✅ Test ผ่าน: ดึง Video ID ถูกต้อง!")

def test_ytdlp_node_runtime():
    # Test that yt-dlp is executable and supports node runtime
    cmd = 'yt-dlp --js-runtimes node --version'
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    assert res.returncode == 0
    assert len(res.stdout.strip()) > 0
    print("✅ Test ผ่าน: yt-dlp และ node runtime รองรับปกติ!")

# รันด้วยคำสั่ง: pytest tests/test_video_engine.py