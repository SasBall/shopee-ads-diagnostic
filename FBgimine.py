import os
import requests
import json
from google import genai

# ==========================================
# 1. โหลด Environment Variables / API Keys
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
LINE_NOTIFY_TOKEN = os.environ.get("LINE_NOTIFY_TOKEN")

client = genai.Client(api_key=GEMINI_API_KEY)


def fetch_daily_metrics():
    """
    ดึงข้อมูล Performance ย้อนหลังประจำวัน
    (ในระบบจริงจะเชื่อม API Meta & Shopee แต่โครงสร้าง Data จะเป็นแบบนี้)
    """
    # ตัวอย่างข้อมูล Real-time ประจำวันตามที่คุณกำหนดไว้
    metrics = {
        "spend": 1500.0,  # ค่าโฆษณา (บาท)
        "impressions": 25000,  # การมองเห็น
        "clicks": 650,  # จำนวนคลิก
        "ctr": 2.60,  # Click-Through Rate (%)
        "cpc": 2.30,  # Cost per Click (บาท)
        "conversions": 18,  # ออเดอร์
        "revenue": 5400.0,  # ยอดขาย (บาท)
        "roas": 3.60,  # Return on Ad Spend (เท่า)
        "frequency": 2.8,  # ความถี่การเห็นโฆษณาซ้ำ
        "stock_remaining": 5  # สต็อกคงเหลือ (ชิ้น)
    }
    return metrics


def generate_ai_recommendation(metrics):
    """
    ให้ AI ช่วยวิเคราะห์ตัวเลข แล้วสรุป "คำแนะนำ" ให้มนุษย์เป็นคนตัดสินใจอนุมัติ
    """
    prompt = f"""
    คุณคือผู้เชี่ยวชาญการยิงโฆษณา Meta & Shopee Ads
    ช่วยวิเคราะห์ข้อมูลโฆษณาประจำวัน ดังนี้:
    - ค่าโฆษณา (Spend): {metrics['spend']} บาท
    - CTR: {metrics['ctr']}% | CPC: {metrics['cpc']} บาท
    - ยอดขาย (Revenue): {metrics['revenue']} บาท | ROAS: {metrics['roas']} เท่า
    - Frequency (การเห็นซ้ำ): {metrics['frequency']}
    - สต็อกสินค้าคงเหลือ: {metrics['stock_remaining']} ชิ้น

    กฎการให้คำแนะนำ:
    1. ถ้าสต็อก <= 0 หรือ ROAS < 2.0 -> แนะนำ "ควรหยุดหรือพักแคมเปญ"
    2. ถ้า Frequency > 3.0 และ CTR < 1.0% -> แนะนำ "ระวังคนเบื่อ ควรเปลี่ยนรูป/คลิปใหม่"
    3. ถ้า ROAS > 3.5 และสต็อกยังมี -> แนะนำ "ประสิทธิภาพดี เสนอให้พิจารณาเพิ่มงบ 15-20%"
    4. สรุป Insights สั้นๆ สำหรับการโต้ตอบลูกค้า หรือปรับ offer หน้างาน

    ช่วยสรุปคำแนะนำในรูปแบบข้อความสั้นๆ ไม่เกิน 4-5 บรรทัด สำหรับส่งเข้า LINE Notify
    """

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt
    )
    return response.text.strip()


def send_line_notify(message, token):
    """
    ส่งรายงานและคำแนะนำเข้า LINE
    """
    if not token:
        print("⚠️ ไม่มี LINE_NOTIFY_TOKEN (พิมพ์รายงานออกทางหน้าจอแทน)")
        print(message)
        return

    url = 'https://notify-api.line.me/api/notify'
    headers = {'Authorization': f'Bearer {token}'}
    payload = {'message': message}

    requests.post(url, headers=headers, data=payload)
    print("📲 ส่งรายงานสรุปเข้า LINE Notify เรียบร้อยแล้ว!")


def main():
    print("📊 กำลังประมวลผลรายงานโฆษณาประจำวัน...")

    # 1. ดึง Data
    data = fetch_daily_metrics()

    # 2. ให้ AI ช่วยวิเคราะห์
    ai_recommendation = generate_ai_recommendation(data)

    # 3. จัดฟอร์แมตรายงานส่งเข้า LINE Notify ให้คนอ่านและอนุมัติ
    report_message = f"""
📊 **รายงานผลโฆษณาประจำวัน (Daily Ads Report)**

💰 **สรุปตัวเลขหลัก:**
• ค่าโฆษณา (Spend): {data['spend']:,.2f} บาท
• ยอดขาย (Revenue): {data['revenue']:,.2f} บาท
• ROAS: {data['roas']} เท่า
• CTR: {data['ctr']}% | CPC: {data['cpc']} บาท
• Frequency: {data['frequency']}
• สต็อกคงเหลือ: {data['stock_remaining']} ชิ้น

💡 **คำแนะนำจากระบบ (รอคุณอนุมัติ):**
{ai_recommendation}

---
*(หมายเหตุ: ระบบไม่ได้ปรับงบหรือปิด Ads อัตโนมัติ โปรดตรวจสอบและอนุมัติการเปลี่ยนแปลงใน Ads Manager)*
"""

    # 4. ส่งรายงาน
    send_line_notify(report_message, LINE_NOTIFY_TOKEN)


if __name__ == "__main__":
    main()