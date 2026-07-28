"""
ai_ads_autopilot.py
----------------------
AI (Gemini) วิเคราะห์ผลโฆษณา -> ตัดสินใจ PAUSE/REDUCE/SCALE/KEEP
-> สั่งงาน Meta Marketing API จริงเพื่อปรับงบ/หยุดโฆษณาอัตโนมัติ (ไม่ต้องรอคนกดอนุมัติ)
-> แจ้งเตือนผลเข้า LINE

⚠️ คำเตือนสำคัญ: สคริปต์นี้ปรับงบ/ปิดโฆษณา "อัตโนมัติทันที" โดยไม่มีคนอนุมัติก่อน
ถ้า Gemini ตอบผิดพลาด หรือข้อมูลนำเข้าผิด อาจทำให้งบเปลี่ยนแปลงโดยไม่ตั้งใจ
แนะนำให้ทดสอบกับ Ad Set งบน้อยๆ ก่อน หรือใส่ระบบ "safety cap" (มีในโค้ดนี้แล้ว
ดูตัวแปร MAX_BUDGET_CHANGE_PER_RUN) ป้องกันการเปลี่ยนงบพรวดเดียวมากเกินไป

⚠️ อย่าใส่ API Key ตรงๆในโค้ด และอย่าแปะ Key จริงในแชทหรือที่สาธารณะ
ให้ตั้งเป็น environment variable เท่านั้น เช่น:
    export GEMINI_API_KEY="your_real_key"
    export META_ACCESS_TOKEN="your_real_token"
"""

import sys
import os
import json
import requests
from google import genai

# แก้ปัญหา Windows console เข้ารหัสไม่รองรับ emoji/unicode บางตัว (UnicodeEncodeError)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# โหลดค่าจากไฟล์ .env อัตโนมัติถ้ามี (สะดวกมากบน Windows/PyCharm ไม่ต้อง set env ทุกครั้ง)
# ถ้ายังไม่ได้ติดตั้ง ให้รัน: pip install python-dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # ถ้าไม่มี python-dotenv ก็ข้ามไป ยังใช้ environment variable ปกติได้

# ==========================================
# 1. โหลด API Keys จาก Environment Variables เท่านั้น
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
META_ACCESS_TOKEN = os.environ.get("META_ACCESS_TOKEN")
META_ADSET_ID = os.environ.get("META_ADSET_ID")
META_API_VERSION = "v21.0"
META_BASE_URL = f"https://graph.facebook.com/{META_API_VERSION}"

# LINE Notify ปิดบริการแล้วตั้งแต่ เม.ย. 2025 ใช้ Messaging API แทน
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_TARGET_ID = os.environ.get("LINE_TARGET_ID")

# ---------- Safety Settings ----------
REDUCE_PCT = 0.20          # ลดงบ 20% ตอน REDUCE
SCALE_PCT = 0.20           # เพิ่มงบ 20% ตอน SCALE
MAX_BUDGET_CHANGE_PER_RUN = 0.30  # กันเหนียว: ห้ามเปลี่ยนงบเกิน 30% ต่อการรันครั้งเดียว ไม่ว่า AI จะแนะนำเท่าไหร่
MIN_DAILY_BUDGET_THB = 100        # งบขั้นต่ำที่ยอมให้เหลือ (บาท) กันงบเหลือ 0 หรือติดลบ

# ---------- โหมดทดลอง ----------
# DRY_RUN=true (ค่าเริ่มต้น) -> คำนวณและ "แสดงผล" ว่าจะทำอะไร แต่ไม่ยิง Meta API จริง ปลอดภัยตอนเทส
# DRY_RUN=false -> ยิง Meta API จริง เปลี่ยนงบ/pause จริง ใช้ตอนมั่นใจแล้วเท่านั้น
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"

client = genai.Client(api_key=GEMINI_API_KEY)


# ==========================================
# 2. ดึงข้อมูลจริงจาก Meta API
# ==========================================
def fetch_meta_adset_data(adset_id):
    """
    ดึงงบปัจจุบันและ spend ของ ad set จาก Meta Graph API
    revenue/stock ยังต้องต่อ Shopee API เพิ่ม (mock ไว้ก่อนตรงนี้)
    """
    # -- ดึง daily_budget ปัจจุบัน --
    info_url = f"{META_BASE_URL}/{adset_id}"
    info_params = {
        "fields": "daily_budget,name,effective_status",
        "access_token": META_ACCESS_TOKEN,
    }
    info_resp = requests.get(info_url, params=info_params, timeout=30)
    info_resp.raise_for_status()
    info = info_resp.json()
    current_budget = float(info.get("daily_budget", 0)) / 100  # Meta เก็บเป็นหน่วยสตางค์/cents

    # -- ดึง insight (spend) ของเมื่อวาน --
    insight_url = f"{META_BASE_URL}/{adset_id}/insights"
    insight_params = {
        "fields": "spend,actions,action_values",
        "date_preset": "yesterday",
        "access_token": META_ACCESS_TOKEN,
    }
    insight_resp = requests.get(insight_url, params=insight_params, timeout=30)
    insight_resp.raise_for_status()
    insight_data = insight_resp.json().get("data", [])
    spend = float(insight_data[0]["spend"]) if insight_data else 0.0

    # TODO: revenue ควรดึงจาก Shopee Open API จริง (ยอดขายจริงแม่นกว่า Meta conversion value)
    # ตอนนี้ mock ไว้เพื่อให้รันทดสอบได้ก่อน ต้องแทนที่ด้วยของจริง
    revenue = 1800.0
    stock = 15

    roas = round(revenue / spend, 2) if spend > 0 else 0.0

    return {
        "adset_id": adset_id,
        "adset_name": info.get("name", ""),
        "current_budget": current_budget,
        "spend": spend,
        "revenue": revenue,
        "roas": roas,
        "stock": stock,
    }


# ==========================================
# 3. ให้ AI (Gemini) ตัดสินใจ
# ==========================================
def ask_ai_decision(ad_data):
    prompt = f"""
    คุณคือผู้เชี่ยวชาญการยิงโฆษณา Facebook และ Shopee
    จงวิเคราะห์ข้อมูลประสิทธิภาพโฆษณานี้:
    - ค่าโฆษณาที่ใช้ไป (Spend): {ad_data['spend']} บาท
    - ยอดขายบน Shopee (Revenue): {ad_data['revenue']} บาท
    - ROAS ปัจจุบัน: {ad_data['roas']} เท่า
    - จำนวนสต็อกที่เหลือ: {ad_data['stock']} ชิ้น

    กฎการตัดสินใจ:
    1. ถ้าสต็อก <= 0 ตอบกลับ action: PAUSE
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
        model="gemini-3.6-flash",
        contents=prompt,
    )

    clean_json = response.text.replace("```json", "").replace("```", "").strip()

    try:
        result = json.loads(clean_json)
    except json.JSONDecodeError:
        # กันเหนียว: ถ้า AI ตอบไม่เป็น JSON ที่ parse ได้ ให้ถือว่า KEEP (ปลอดภัยไว้ก่อน ไม่แตะงบ)
        result = {"action": "KEEP", "reason": f"AI ตอบไม่เป็น JSON ที่ถูกต้อง: {response.text[:200]}"}

    if result.get("action") not in ("PAUSE", "REDUCE", "SCALE", "KEEP"):
        result = {"action": "KEEP", "reason": f"action ที่ AI ตอบไม่ถูกต้อง: {result.get('action')}"}

    return result


# ==========================================
# 4. สั่งงาน Meta API จริง ตามที่ AI ตัดสินใจ
# ==========================================
def apply_meta_action(adset_id, action, current_budget):
    """
    เรียก Meta API จริงเพื่อ pause หรือปรับ daily_budget
    return: (new_budget, executed: bool, note: str)
    """
    if action == "KEEP":
        return current_budget, False, "ไม่มีการเปลี่ยนแปลง"

    if action == "PAUSE":
        if DRY_RUN:
            return current_budget, False, "[DRY RUN] จะสั่งหยุดโฆษณา (status = PAUSED) แต่ยังไม่ได้ยิงจริง"
        url = f"{META_BASE_URL}/{adset_id}"
        payload = {"status": "PAUSED", "access_token": META_ACCESS_TOKEN}
        resp = requests.post(url, data=payload, timeout=30)
        resp.raise_for_status()
        return current_budget, True, "สั่งหยุดโฆษณาเรียบร้อย (status = PAUSED)"

    if action == "REDUCE":
        pct = min(REDUCE_PCT, MAX_BUDGET_CHANGE_PER_RUN)
        new_budget = max(current_budget * (1 - pct), MIN_DAILY_BUDGET_THB)
    elif action == "SCALE":
        pct = min(SCALE_PCT, MAX_BUDGET_CHANGE_PER_RUN)
        new_budget = current_budget * (1 + pct)
    else:
        return current_budget, False, "ไม่รู้จัก action นี้"

    if DRY_RUN:
        return new_budget, False, f"[DRY RUN] จะปรับงบจาก {current_budget:.0f} -> {new_budget:.0f} บาท แต่ยังไม่ได้ยิงจริง"

    new_budget_cents = int(round(new_budget * 100))
    url = f"{META_BASE_URL}/{adset_id}"
    payload = {"daily_budget": new_budget_cents, "access_token": META_ACCESS_TOKEN}
    resp = requests.post(url, data=payload, timeout=30)
    resp.raise_for_status()

    return new_budget, True, f"ปรับงบจาก {current_budget:.0f} -> {new_budget:.0f} บาท"


# ==========================================
# 5. แจ้งเตือนผลเข้า LINE (Messaging API)
# ==========================================
def send_line_message(message):
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_TARGET_ID:
        print("⚠️ ไม่มี LINE_CHANNEL_ACCESS_TOKEN/LINE_TARGET_ID (พิมพ์แทน)")
        print(message)
        return
    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"to": LINE_TARGET_ID, "messages": [{"type": "text", "text": message}]}
    resp = requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=payload, timeout=15)
    if resp.status_code == 200:
        print("📲 แจ้งเตือนเข้า LINE เรียบร้อย")
    else:
        print(f"❌ แจ้งเตือน LINE ไม่สำเร็จ ({resp.status_code}): {resp.text}")


# ==========================================
# 6. Main
# ==========================================
def main():
    if not META_ACCESS_TOKEN or not META_ADSET_ID:
        print("❌ ต้องตั้งค่า META_ACCESS_TOKEN และ META_ADSET_ID ก่อนรัน")
        return

    mode_label = "🧪 DRY RUN (โหมดทดสอบ ไม่แตะงบจริง)" if DRY_RUN else "🔴 LIVE (รันจริง จะเปลี่ยนงบจริง)"
    print(f"โหมดการรัน: {mode_label}\n")

    print("📡 กำลังดึงข้อมูลจริงจาก Meta API...")
    ad_data = fetch_meta_adset_data(META_ADSET_ID)
    print(f"   Ad Set: {ad_data['adset_name']} | งบปัจจุบัน: {ad_data['current_budget']:.0f} บาท | "
          f"Spend: {ad_data['spend']:.0f} | ROAS: {ad_data['roas']}")

    print("🤖 กำลังส่งข้อมูลให้ AI วิเคราะห์...")
    ai_result = ask_ai_decision(ad_data)
    action = ai_result.get("action")
    reason = ai_result.get("reason")
    print(f"💡 AI ตัดสินใจ: {action} | เหตุผล: {reason}")

    print("⚙️ กำลังสั่งงาน Meta API ตามคำแนะนำ...")
    try:
        new_budget, executed, note = apply_meta_action(
            META_ADSET_ID, action, ad_data["current_budget"]
        )
        status_line = f"✅ {note}" if executed else f"ℹ️ {note}"
    except requests.exceptions.RequestException as e:
        new_budget = ad_data["current_budget"]
        status_line = f"⚠️ สั่งงาน Meta API ไม่สำเร็จ: {e}"

    print(status_line)

    msg = (
        f"🤖 AI Ads Autopilot\n"
        f"Ad Set: {ad_data['adset_name']}\n"
        f"คำสั่ง: {action}\n"
        f"เหตุผล: {reason}\n"
        f"ผลการทำงาน: {status_line}"
    )
    send_line_message(msg)


if __name__ == "__main__":
    main()
