"""
test_gemini_only.py
----------------------
ทดสอบเฉพาะส่วน AI (Gemini) ตัดสินใจ โดยไม่ต้องมี Meta API เลย
ใช้ข้อมูล mock หลายสถานการณ์ ดูว่า Gemini ตอบตรงตามกฎที่ตั้งไว้ไหม

ต้องตั้งค่าแค่:
    export GEMINI_API_KEY="your_real_key"

รัน:
    python test_gemini_only.py
"""

import sys
import os

# แก้ปัญหา Windows console เข้ารหัสไม่รองรับ emoji/unicode บางตัว (UnicodeEncodeError)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# import ฟังก์ชันตัดสินใจจากไฟล์หลัก โดยไม่ยุ่งกับส่วน Meta เลย
from FBClaude import ask_ai_decision

# เคสทดสอบ: ครอบคลุมทุกกฎที่ตั้งไว้ (PAUSE / REDUCE / SCALE / KEEP)
TEST_CASES = [
    {
        "name": "สต็อกหมด -> ควรได้ PAUSE",
        "data": {"spend": 1000, "revenue": 4000, "roas": 4.0, "stock": 0},
    },
    {
        "name": "ROAS ต่ำ (ขาดทุน) -> ควรได้ REDUCE",
        "data": {"spend": 1200, "revenue": 1800, "roas": 1.5, "stock": 15},
    },
    {
        "name": "ROAS สูงมาก + สต็อกพอ -> ควรได้ SCALE",
        "data": {"spend": 1000, "revenue": 5000, "roas": 5.0, "stock": 50},
    },
    {
        "name": "ROAS กลางๆ ปกติ -> ควรได้ KEEP",
        "data": {"spend": 1000, "revenue": 2800, "roas": 2.8, "stock": 20},
    },
]


def main():
    if not os.environ.get("GEMINI_API_KEY"):
        print(" ยังไม่ได้ตั้งค่า GEMINI_API_KEY กรุณา export ก่อนรัน")
        return

    print("เริ่มทดสอบ Gemini decision logic (ไม่แตะ Meta API)\n")

    for case in TEST_CASES:
        print(f"--- เคส: {case['name']} ---")
        print(f"   ข้อมูล: {case['data']}")
        try:
            result = ask_ai_decision(case["data"])
            print(f"    AI ตอบ: action={result.get('action')} | reason={result.get('reason')}")
        except Exception as e:
            print(f"    เกิดข้อผิดพลาด: {e}")
        print()


if __name__ == "__main__":
    main()
