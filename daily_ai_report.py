import os
import json
import requests
from google import genai
from dotenv import load_dotenv  # 1. Import ตัวอ่าน .env
from shopee_api import get_shopee_ads_data  # ดึงข้อมูลจาก Shopee API

load_dotenv() # 2. โหลดค่าจากไฟล์ .env เข้ามาในระบบ

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
LINE_NOTIFY_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")

def analyze_performance_and_get_solutions(ads_data):
    """
    ส่งข้อมูล Performance ทั้งภาพรวมและรายชิ้น ให้ Gemini วิเคราะห์สาเหตุและวิธีแก้
    """
    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""
    คุณคือผู้เชี่ยวชาญระดับสูงในการยิง Shopee Ads โปรดวิเคราะห์ข้อมูล Performance ประจำวันเพื่อค้นหาปัญหาและเสนอวิธีแก้ไขเพิ่มยอดขาย:

    [ข้อมูลสถิติจาก Shopee Ads API]
    {json.dumps(ads_data, ensure_ascii=False, indent=2)}

    โจทย์และโครงสร้างรายงานที่ต้องสรุป (สำหรับส่งเข้า LINE Notify):

    1. 📊 **สรุปภาพรวมโฆษณา (Overall Status):**
       - สรุปตัวเลขสำคัญ (Impressions, Clicks, CTR, ยอดขาย, ค่าโฆษณา)
       - ประเมินว่าภาพรวมร้านค้าอยู่ในเกณฑ์ไหน

    2. 🔍 **วิเคราะห์สาเหตุของปัญหา (Root Cause Analysis):**
       - ระบุสินค้ารายตัวที่มีปัญหา (เช่น สินค้าที่ Impression = 0 หรือ CTR ต่ำมากๆ)
       - อธิบายสาเหตุที่เป็นไปได้เชิงลึก (เช่น Bid Price ต่ำเกินไป, Keyword แคบ, เงินในระบบหมด, หรือสินค้าโดนระงับ)

    3. 🛠️ **วิธีการแก้ไขและแนวทางเพิ่มยอดขาย (Actionable Solutions):**
       - เสนอวิธีแก้ปัญหาแบบเป็นข้อๆ กระชับ และทำตามได้ทันที
       - แนะนำการปรับ Bid, การเลือก Keyword หรือการปรับรูป/ชื่อสินค้าเพื่อดันยอดขาย

    ตอบเป็นภาษาไทย รูปแบบสวยงาม อ่านง่าย อ่านใน LINE แล้วเข้าใจทันที
    """

    try:
        # ใช้ 'models/gemini-3.6-flash' เพื่อป้องกัน error 400
        response = client.models.generate_content(
            model='models/gemini-3.6-flash',
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        print(f"⚠️ Gemini API Error: {e}")
        return f"⚠️ ไม่สามารถเจนรายงานวิเคราะห์จาก Gemini ได้: {e}"


def send_line_message(message):
    """ ส่งรายงานวิเคราะห์เข้า LINE OA ผ่าน Messaging API """
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    target_id = os.environ.get("LINE_TARGET_ID")

    if not token or not target_id:
        print("⚠️ ไม่พบ LINE Credentials ใน .env แสดงผลบนหน้าจอแทน:\n", message)
        return

    # Endpoint สำหรับ LINE Messaging API (ไม่ใช่ notify-api)
    url = 'https://api.line.me/v2/bot/message/push'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    payload = {
        'to': target_id,
        'messages': [
            {
                'type': 'text',
                'text': f"🧪 [Shopee Ads AI Diagnostic Test Report]\n\n{message}"
            }
        ]
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        if response.status_code == 200:
            print("📲 ส่งรายงานเข้า LINE OA เรียบร้อยแล้ว!")
        else:
            print(f"⚠️ LINE API ตอบกลับ Error (Status {response.status_code}): {response.text}")
    except Exception as e:
        print(f"⚠️ เกิดข้อผิดพลาดในการเชื่อมต่อ LINE: {e}")


def main():
    print("🔄 กำลังดึงข้อมูลสถิติโฆษณาจาก Shopee API...")
    ads_data = get_shopee_ads_data()

    # กรณีไม่มีข้อมูลจาก API หรือทดสอบ ให้ใช้ Mock Data อิงจากรูปภาพของคุณ
    if not ads_data:
        print("⚠️ ไม่พบข้อมูล API จริง -> ใช้ Mock Data ตามภาพถ่ายหน้าจอ...")
        ads_data = {
            "overall_stats": {
                "impressions": "88.1k",
                "clicks": "2.7k",
                "ctr": "3.08%",
                "orders": 154,
                "items_sold": 171,
                "revenue": "฿49.9k",
                "ads_spend": "฿5k"
            },
            "single_item_stats": [
                {
                    "item_name": "สินค้ารายการที่ 2 (พบปัญหา)",
                    "impressions": 0,
                    "clicks": 0,
                    "ctr": "0%",
                    "orders": 0,
                    "revenue": "฿0.00",
                    "ads_spend": "฿0.00"
                }
            ]
        }

    print("🤖 กำลังส่งข้อมูลให้ Gemini AI วิเคราะห์หาสาเหตุและวิธีแก้...")
    report = analyze_performance_and_get_solutions(ads_data)

    print("📲 กำลังส่งรายงานไปที่ LINE Notify...")
    send_line_message(report)


if __name__ == "__main__":
    main()