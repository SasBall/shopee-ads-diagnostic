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
    คุณคือผู้เชี่ยวชาญระดับสูงในการยิง Shopee Ads โปรดวิเคราะห์ข้อมูล Performance จากรายงาน CSV เพื่อค้นหาปัญหาและเสนอวิธีแก้ไขเพิ่มยอดขาย:

    [ข้อมูลสถิติจากไฟล์ CSV Shopee Ads]
    {json.dumps(data_dict, ensure_ascii=False, indent=2)}

    โจทย์และโครงสร้างรายงานที่ต้องสรุป (สำหรับส่งเข้า LINE):
    1. 📊 สรุปภาพรวมโฆษณา (Impressions, Clicks, CTR, ยอดขาย, ค่าโฆษณา)
    2. 🔍 วิเคราะห์สาเหตุของปัญหา (สินค้ารายตัวที่มีปัญหา, CTR ต่ำ, Bid Price ต่ำ)
    3. 🛠️ วิธีการแก้ไขและแนวทางเพิ่มยอดขายแบบเป็นข้อๆ (ใช้ภาษาที่เข้าใจง่าย อันไหนตัวย่อหรือคำศัพท์อังกฤษช่วยแปลเป็นไทยด้วย)

    ตอบเป็นภาษาไทย รูปแบบสวยงาม อ่านง่ายใน LINE
    """

    try:
        response = client.models.generate_content(
            model='models/gemini-1.5-flash',
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
