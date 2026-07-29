import os
import json
import io
import pandas as pd
import requests
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from dotenv import load_dotenv

load_dotenv()
# เพิ่มบรรทัดนี้ใต้ load_dotenv() ใน app.py


GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_TARGET_ID = os.environ.get("LINE_TARGET_ID")


app = FastAPI()

# 🟢 เพิ่ม CORS Middleware อนุญาตให้ GitHub Pages เรียกใช้งาน API ได้
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # หรือระบุเฉพาะ ["https://sasball.github.io"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
) 

def analyze_ads_data_with_gemini(data_dict):
    """ ส่งข้อมูล CSV ที่แปลงเป็น Dict แล้วให้ Gemini 3.6 Flash วิเคราะห์ """
    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""
    คุณคือ Senior Performance Marketing Specialist และ Shopee Ads Expert
    มีประสบการณ์บริหารงบโฆษณามากกว่า 15 ปี และเชี่ยวชาญการเพิ่ม ROAS และกำไร
    
    หน้าที่ของคุณคือวิเคราะห์ข้อมูลจากรายงาน Shopee Ads แล้วให้คำแนะนำที่สามารถนำไปใช้งานจริง
    เป้าหมายสูงสุดคือ
    
    - เพิ่มกำไร
    - ลดต้นทุนโฆษณา
    - เพิ่ม ROAS
    - ไม่ให้ใช้เงินโฆษณาเกินความจำเป็น
    - หาจุดที่เสียเงินโดยเปล่าประโยชน์
    - แนะนำวิธีเพิ่มยอดขายอย่างเป็นระบบ
    
    ข้อมูลจากไฟล์ CSV
    
    {json.dumps(data_dict, ensure_ascii=False, indent=2)}
    
    ==========================
    สิ่งที่ต้องวิเคราะห์
    ==========================
    
    1. สรุปภาพรวมบัญชีโฆษณา
    
    - จำนวนสินค้า
    - Impressions
    - Clicks
    - CTR
    - Orders
    - Conversion Rate
    - ค่าโฆษณารวม
    - ยอดขายรวม
    - ROAS รวม
    - CPC
    - CPM
    
    อธิบายเป็นภาษาคนทั่วไปเข้าใจง่าย
    
    ---------------------------------------
    
    2. วิเคราะห์สินค้าแต่ละตัว
    
    สำหรับสินค้าทุกตัวให้วิเคราะห์
    
    - CTR ดีหรือไม่
    - CPC สูงหรือต่ำ
    - Conversion ดีหรือไม่
    - ROAS ดีหรือไม่
    - ยอดขายคุ้มค่าโฆษณาหรือไม่
    - ใช้งบมากเกินไปหรือไม่
    - ควรยิงต่อหรือหยุด
    - ควรเพิ่ม Bid หรือไม่
    - ควรลด Bid หรือไม่
    - ควรเพิ่มงบหรือไม่
    - ควรลดงบหรือไม่
    
    อธิบายเหตุผลทุกข้อ
    
    ---------------------------------------
    
    3. ค้นหาปัญหา
    
    ระบุสินค้าที่มีปัญหา เช่น
    
    - CTR ต่ำ
    - ไม่มีคลิก
    - CPC สูง
    - ROAS ต่ำ
    - ใช้งบแต่ไม่ขาย
    - Bid ต่ำเกินไป
    - Bid สูงเกินไป
    - คำค้นหาไม่เหมาะสม
    - รูปสินค้าไม่น่าสนใจ
    - ชื่อสินค้าไม่ดึงดูด
    - ราคาไม่สามารถแข่งขันได้
    
    พร้อมอธิบายสาเหตุ
    
    ---------------------------------------
    
    4. วิธีแก้ไข
    
    เสนอวิธีแก้แบบละเอียด
    
    ตัวอย่างเช่น
    
    - เปลี่ยนรูปหน้าปก
    - เปลี่ยนชื่อสินค้า
    - เพิ่ม Keyword
    - ลบ Keyword
    - เพิ่ม Bid
    - ลด Bid
    - เพิ่มงบ
    - ลดงบ
    - หยุดโฆษณา
    - ยิงเฉพาะสินค้าที่กำไรดี
    - เปิด Discovery Ads
    - เปิด Search Ads
    - แยก Campaign ใหม่
    
    อธิบายทีละข้อ
    
    ---------------------------------------
    
    5. วิเคราะห์ ROAS
    
    คำนวณ
    
    ROAS = ยอดขาย ÷ ค่าโฆษณา
    
    สำหรับสินค้าทุกตัว
    
    พร้อมบอกว่า
    
    - ROAS ปัจจุบัน
    - ROAS ดีหรือไม่
    - ROAS ควรเป็นเท่าไร
    - ถ้าจะทำกำไรควรตั้งเป้าหมาย ROAS เท่าไร
    - ถ้า ROAS ต่ำกว่าควรทำอะไร
    - ถ้า ROAS สูงกว่าควรเพิ่มงบหรือไม่
    
    ---------------------------------------
    
    6. วิเคราะห์การใช้งบ
    
    บอกว่าสินค้าไหน
    
    - ควรเพิ่มงบกี่ %
    - ควรลดงบกี่ %
    - ควรหยุดโฆษณา
    - ควรเพิ่ม Bid กี่ %
    - ควรลด Bid กี่ %
    
    พร้อมเหตุผล
    
    ---------------------------------------
    
    7. จัดอันดับสินค้า
    
    แบ่งเป็น
    
    ⭐⭐⭐⭐⭐ ควรเร่งยิง
    
    ⭐⭐⭐⭐ ควรยิงต่อ
    
    ⭐⭐⭐ เฝ้าดู
    
    ⭐⭐ ควรปรับปรุง
    
    ⭐ ควรหยุด
    
    พร้อมเหตุผล
    
    ---------------------------------------
    
    8. สรุปสำหรับเจ้าของร้าน
    
    สรุปเป็นภาษาง่าย ๆ
    
    - วันนี้ควรทำอะไร
    - พรุ่งนี้ควรทำอะไร
    - สินค้าไหนทำเงินที่สุด
    - สินค้าไหนกำลังขาดทุน
    - สินค้าไหนควรหยุดยิง
    - ถ้ามีงบเพิ่มควรลงทุนกับสินค้าไหน
    
    ---------------------------------------
    
    ข้อกำหนด
    
    - ใช้ภาษาไทยทั้งหมด
    - อธิบายคำศัพท์อังกฤษทุกคำ เช่น CTR, CPC, CPM, ROAS
    - ใช้ Bullet Point
    - เรียงลำดับความสำคัญ
    - อย่าตอบแบบกว้าง ๆ
    - ใช้ตัวเลขจริงจากข้อมูล CSV
    - ถ้าข้อมูลไม่พอให้แจ้งว่าข้อมูลไม่เพียงพอ ห้ามเดา
    - สรุปให้อ่านง่าย เพื่อส่งต่อเข้า LINE ได้ทันที
    """

    try:
        response = client.models.generate_content(
            model='models/gemini-3.6-flash',
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        return f"⚠️ Gemini Error: {e}"


def send_line_message(message):
    """ ส่งรายงานวิเคราะห์เข้า LINE OA """
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_TARGET_ID:
        return False

    url = 'https://api.line.me/v2/bot/message/push'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {LINE_CHANNEL_ACCESS_TOKEN}'
    }
    payload = {
        'to': LINE_TARGET_ID,
        'messages': [{'type': 'text', 'text': f"📊 [Shopee Ads Diagnostic Report]\n\n{message}"}]
    }
    res = requests.post(url, headers=headers, json=payload, timeout=15)
    return res.status_code == 200


@app.get("/", response_class=HTMLResponse)
async def read_index():
    """ โหลดหน้าเว็บ HTML """
    with open("Index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.post("/api/upload-csv")
async def upload_csv(file: UploadFile = File(...)):
    """ Endpoint สำหรับรับไฟล์ CSV จาก Shopee มาประมวลผลอย่างแม่นยำ """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="กรุณาอัปโหลดไฟล์นามสกุล .csv เท่านั้น")

    try:
        contents = await file.read()

        # 1. อ่านไฟล์โดยข้าม Header ร้านค้า 7 บรรทัดแรกของ Shopee
        df = pd.read_csv(io.BytesIO(contents), skiprows=7)

        # 2. กรองเฉพาะแถวที่มีข้อมูลรายการสินค้าจริง
        df = df.dropna(subset=['ชื่อโฆษณา / ชื่อสินค้า']) if 'ชื่อโฆษณา / ชื่อสินค้า' in df.columns else df

        if df.empty:
            return {
                "status": "warning",
                "message": "ไฟล์ CSV นี้ไม่มีข้อมูลการยิงโฆษณาในช่วงเวลาดังกล่าว",
                "ai_report": "⚠️ ไม่พบข้อมูลโฆษณาในไฟล์ที่อัปโหลด (อาจเป็นช่วงเวลาที่ไม่ได้เปิดโฆษณา)",
                "line_sent": False
            }

        # 3. Clean ข้อมูลตัวเลข (ลบเครื่องหมาย , และ % เพื่อให้ Gemini คำนวณง่ายขึ้น)
        numeric_cols = ['การมองเห็น', 'จำนวนคลิก', 'การสั่งซื้อ', 'สินค้าที่ขายแล้ว', 'ยอดขาย', 'ค่าโฆษณา',
                        'ยอดขาย/รายจ่าย (ROAS)']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(',', '').str.replace('%', '')
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        # 4. คำนวณภาพรวมสรุป (Summary) ด้วย Python เพื่อความแม่นยำ 100%
        summary_stats = {
            "จำนวนสินค้าทั้งหมด": len(df),
            "การมองเห็นรวม (Impressions)": int(df['การมองเห็น'].sum()) if 'การมองเห็น' in df.columns else 0,
            "จำนวนคลิกรวม (Clicks)": int(df['จำนวนคลิก'].sum()) if 'จำนวนคลิก' in df.columns else 0,
            "ค่าโฆษณารวม (Expense)": float(df['ค่าโฆษณา'].sum()) if 'ค่าโฆษณา' in df.columns else 0.0,
            "ยอดขายรวม (Sales)": float(df['ยอดขาย'].sum()) if 'ยอดขาย' in df.columns else 0.0,
        }

        # คำนวณ CTR รวม และ ROAS รวม
        if summary_stats["การมองเห็นรวม (Impressions)"] > 0:
            summary_stats["CTR รวม (%)"] = round(
                (summary_stats["จำนวนคลิกรวม (Clicks)"] / summary_stats["การมองเห็นรวม (Impressions)"]) * 100, 2)
        if summary_stats["ค่าโฆษณารวม (Expense)"] > 0:
            summary_stats["ROAS รวม"] = round(
                summary_stats["ยอดขายรวม (Sales)"] / summary_stats["ค่าโฆษณารวม (Expense)"], 2)

        # 5. แปลงข้อมูลส่งให้ Gemini วิเคราะห์
        payload_data = {
            "ภาพรวมทั้งร้าน": summary_stats,
            "รายการสินค้ารายตัว": df.to_dict(orient='records')
        }

        ai_report = analyze_ads_data_with_gemini(payload_data)

        # 6. ส่งเข้า LINE OA
        line_sent = send_line_message(ai_report)

        return {
            "status": "success",
            "message": "ประมวลผลข้อมูลเรียบร้อยแล้ว",
            "summary": summary_stats,
            "ai_report": ai_report,
            "line_sent": line_sent
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาดในการอ่านไฟล์: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
