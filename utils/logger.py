from loguru import logger
import sys

# ตั้งค่าให้เก็บ Log ลงไฟล์และแสดงผลใน Console
logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add("logs/app.log", rotation="10 MB", level="DEBUG")

def get_logger():
    return logger