import os
import requests
import json
from google import genai

# 1. โหลด API Keys
GEMINI_API_KEY = os.environ.get("A")
META_ACCESS_TOKEN = os.environ.get("META_ACCESS_TOKEN")
META_ADSET_ID = os.environ.get("META_ADSET_ID")
LINE_NOTIFY_TOKEN = os.environ.get("LINE_NOTIFY_TOKEN")

# เรียกใช้ Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)


def ask_ai_decision(ad_data):
    """
    ส่งข้อมูล Ads และยอดขาย ให้ AI (Gemini) ช่วยตัดสินใจ
    """
    prompt = f"""
    คุณคือผู้เชี่ยวชาญการยิงโฆษณา Facebook และ Shopee 
    จงวิเคราะห์ข้อมูลประสิทธิภาพโฆษณานี้:
    - ค่าโฆษณาที่ใช้ไป (Spend): {ad_data['spend']} บาท
    - ยอดขายบน Shopee (Revenue): {ad_data['revenue']} บาท
    - ROAS ปัจจุบัน: {ad_data['roas']} เท่า
    - จำนวนสต็อกที่เหลือ: {ad_data['stock']} ชิ้น

    กฎการตัดสินใจ:
    1. ถ้าสต็อก <= 0 ตอบกลับaction: PAUSE
    2. ถ้า ROAS < 2.0 (ขาดทุน/ไม่คุ้ม) ตอบกลับ action: REDUCE
    3. ถ้า ROAS > 4.0 (กำไรดีมาก) ตอบกลับ action: SCALE
    4. นอกเหนือจากนี้ ตอบกลับ action: KEEP

    ตอบกลับเป็น JSON รูปแบบนี้เท่านั้น ห้ามมีคำอื่น:
    {{
        "action": "PAUSE หรือ REDUCE หรือ SCALE หรือ KEEP",
        "reason": "เหตุผลสั้นๆ ไม่เกิน 1 ประโยค"
    }}
    """

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt
    )

    # ทำความสะอาด Response และแปลงเป็น JSON
    clean_json = response.text.replace("```json", "").replace("```", "").strip()
    return json.loads(clean_json)


def main():
    # 2. จำลองข้อมูล Real-time ที่ดึงมาจาก Shopee & Meta
    current_ad_data = {
        "spend": 1200,
        "revenue": 1800,  # ROAS = 1.5 (ขาดทุน)
        "roas": 1.5,
        "stock": 15
    }

    print("🤖 กำลังส่งข้อมูลให้ AI วิเคราะห์...")
    ai_result = ask_ai_decision(current_ad_data)

    action = ai_result.get("action")
    reason = ai_result.get("reason")

    print(f"💡 AI ตัดสินใจ: {action}")
    print(f"📝 เหตุผล: {reason}")

    # 3. สั่งงานตามที่ AI ตัดสินใจ
    if action == "PAUSE":
        # สั่งปิด Ads ผ่าน Meta API
        print("⏸️ กำลังสั่งปิด Ads ตามที่ AI แนะนำ...")
    elif action == "REDUCE":
        # สั่งลดงบโฆษณาลง 20%
        print("📉 กำลังสั่งลดงบ Ads ตามที่ AI แนะนำ...")
    elif action == "SCALE":
        # สั่งเพิ่มงบโฆษณา 20%
        print("🚀 กำลังสั่งเพิ่มงบ Ads เพื่อสเกลยอดขาย...")

    # 4. แจ้งเตือนผลเข้า LINE
    msg = f"\n🤖 **AI Ads Decision**\nคำสั่ง: {action}\nเหตุผล: {reason}"
    # send_line_notify(msg, LINE_NOTIFY_TOKEN)


if __name__ == "__main__":
    main()