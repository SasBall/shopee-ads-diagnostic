"""
shopee_ads_monitor.py
------------------------
ระบบติดตามผล Shopee Ads ตาม 2 เงื่อนไข รันวันละ 1 ครั้ง (ตั้งเวลาด้วย Windows Task Scheduler):
  1) การควบคุม ROAS (Rule-based threshold)
  2) การติดตามผล + วิเคราะห์สาเหตุด้วย AI (Gemini)

วิเคราะห์ครบทุกระดับในรอบเดียว:
  - ทุกรายการสินค้า (loop วินิจฉัยทีละ campaign_id)
  - ยอดรวมทั้งร้าน (shop_overall)
แล้วสรุปส่งเข้า LINE ทีเดียวจบ

ถ้ายังไม่ได้ตั้งค่า Shopee API credentials ครบ จะใช้ข้อมูล mock ตามภาพตัวอย่างที่เคยส่งมา
(1 รายการ mock ที่ delivery = 0 + ยอดรวมร้านที่ ROAS ดี) เพื่อให้ทดสอบ logic ได้ก่อน
"""

import sys
import os
import datetime
import requests
from google import genai

# แก้ปัญหา Windows console เข้ารหัสไม่รองรับ unicode บางตัว
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import Shopee_client_api as shopee

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

# ---------- ตั้งค่า Shopee credentials จาก .env ----------
shopee.PARTNER_ID = int(os.environ.get("SHOPEE_PARTNER_ID", 0)) or None
shopee.PARTNER_KEY = os.environ.get("SHOPEE_PARTNER_KEY")
shopee.SHOP_ID = int(os.environ.get("SHOPEE_SHOP_ID", 0)) or None
shopee.ACCESS_TOKEN = os.environ.get("SHOPEE_ACCESS_TOKEN")

USE_REAL_SHOPEE_API = all([shopee.PARTNER_ID, shopee.PARTNER_KEY, shopee.SHOP_ID, shopee.ACCESS_TOKEN])

# ---------- เงื่อนไข ROAS ที่ต้องคุม ----------
TARGET_ROAS = 3.0                 # ROAS เป้าหมายขั้นต่ำที่ถือว่าคุ้ม (ปรับตาม margin สินค้าจริง)
SCALE_ROAS_MULTIPLIER = 2.0        # ROAS เกินเท่านี้ของเป้า -> แนะนำเพิ่มงบ
PAUSE_ROAS_MULTIPLIER = 0.5        # ROAS ต่ำกว่าเท่านี้ของเป้า -> หยุดเลย (ขาดทุนหนัก)
MIN_IMPRESSIONS_FOR_HEALTHY = 100  # ต่ำกว่านี้ถือว่า "ไม่ได้แสดงผล" ต้องเช็คสถานะแคมเปญก่อนเช็ค ROAS
LOOKBACK_DAYS = 1                  # วิเคราะห์ข้อมูลกี่วันย้อนหลังในแต่ละรอบ (1 = เมื่อวาน)

# ---------- Safety settings สำหรับสั่งงานอัตโนมัติ ----------
REDUCE_PCT = 0.20                  # ลดงบ 20% ตอน BELOW_TARGET
SCALE_PCT = 0.20                   # เพิ่มงบ 20% ตอน EXCELLENT
MAX_BUDGET_CHANGE_PER_RUN = 0.30   # กันเหนียว: ห้ามเปลี่ยนงบเกิน 30% ต่อรอบไม่ว่า AI/rule จะแนะนำเท่าไหร่
MIN_DAILY_BUDGET_THB = 50          # งบขั้นต่ำที่ยอมให้เหลือ (บาท)

# DRY_RUN=true (ค่าเริ่มต้น) -> คำนวณและแสดงผลว่าจะทำอะไร แต่ไม่ยิง Shopee API จริง
# DRY_RUN=false -> ยิงจริง เปลี่ยนงบ/pause จริง ใช้ตอนมั่นใจแล้วเท่านั้น
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"


# ==========================================
# 1. ดึงรายชื่อ campaign_id ทุกรายการสินค้าในร้าน
# ==========================================
def get_all_campaign_ids():
    """คืน list ของ campaign_id ทุกตัวที่มีในร้าน (mock คืน id ปลอมตัวเดียวถ้ายังไม่ต่อ API จริง)"""
    if not USE_REAL_SHOPEE_API:
        return ["MOCK_ITEM_1"]

    all_ids = []
    offset, limit = 0, 50
    while True:
        raw = shopee.get_campaign_id_list(ad_type="all", offset=offset, limit=limit)
        campaign_list = raw.get("response", {}).get("campaign_list", [])
        if not campaign_list:
            break
        all_ids.extend([c["campaign_id"] for c in campaign_list])
        if not raw.get("response", {}).get("more", False):
            break
        offset += limit
    return all_ids


# ==========================================
# 2. ดึง performance รายสินค้า 1 รายการ + รวมทั้งร้าน
# ==========================================
def get_current_budget(campaign_id):
    """ดึง budget ปัจจุบันของแคมเปญ ถ้าไม่มี API จริง คืนค่า mock คงที่"""
    if not USE_REAL_SHOPEE_API:
        return 100.0  # mock งบเริ่มต้นสำหรับทดสอบ

    raw = shopee.get_campaign_setting_info([campaign_id])
    # หมายเหตุ: โครงสร้าง response ต้องเทียบกับเอกสารจริงอีกที เผื่อ field เปลี่ยน
    info_list = raw.get("response", {}).get("campaign_setting_info_list", [])
    if not info_list:
        return None
    return float(info_list[0].get("common_info", {}).get("budget", 0))


def fetch_single_item_data(campaign_id, start_date, end_date):
    """ดึง performance ของ 1 campaign_id ถ้าไม่มี API จริง จะคืน mock ตาม Image 1"""
    if not USE_REAL_SHOPEE_API:
        return {
            "campaign_id": campaign_id, "period": f"{start_date} - {end_date}",
            "impressions": 0, "clicks": 0, "ctr_pct": 0.0,
            "orders": 0, "items_sold": 0, "revenue": 0.0, "spend": 0.0,
            "current_budget": get_current_budget(campaign_id),
        }

    raw = shopee.get_product_campaign_daily_performance([campaign_id], start_date, end_date)
    # หมายเหตุ: ชื่อ field ต้องเทียบกับเอกสาร Shopee ปัจจุบันอีกที เผื่อเปลี่ยนแปลง
    entries = raw.get("response", {}).get("entry_list", [])
    totals = {"impressions": 0, "clicks": 0, "orders": 0, "items_sold": 0, "revenue": 0.0, "spend": 0.0}
    for e in entries:
        totals["impressions"] += e.get("impression", 0)
        totals["clicks"] += e.get("clicks", 0)
        totals["orders"] += e.get("order", 0)
        totals["items_sold"] += e.get("item_sold", 0)
        totals["revenue"] += float(e.get("broad_gmv", 0))
        totals["spend"] += float(e.get("expense", 0))
    ctr = round(totals["clicks"] / totals["impressions"] * 100, 2) if totals["impressions"] else 0.0

    return {
        "campaign_id": campaign_id, "period": f"{start_date} - {end_date}",
        "impressions": totals["impressions"], "clicks": totals["clicks"], "ctr_pct": ctr,
        "orders": totals["orders"], "items_sold": totals["items_sold"],
        "revenue": totals["revenue"], "spend": totals["spend"],
        "current_budget": get_current_budget(campaign_id),
    }


def fetch_shop_overall_data(start_date, end_date):
    """ดึง performance รวมทั้งร้าน ถ้าไม่มี API จริง จะคืน mock ตาม Image 2"""
    if not USE_REAL_SHOPEE_API:
        return {
            "period": "01/02 - 08/02",
            "impressions": 88100, "clicks": 2700, "ctr_pct": 3.08,
            "orders": 154, "items_sold": 171, "revenue": 49900.0, "spend": 5000.0,
        }

    raw = shopee.get_shop_overall_daily_performance(start_date, end_date)
    entries = raw.get("response", {}).get("entry_list", [])
    totals = {"impressions": 0, "clicks": 0, "orders": 0, "items_sold": 0, "revenue": 0.0, "spend": 0.0}
    for e in entries:
        totals["impressions"] += e.get("impression", 0)
        totals["clicks"] += e.get("clicks", 0)
        totals["orders"] += e.get("order", 0)
        totals["items_sold"] += e.get("item_sold", 0)
        totals["revenue"] += float(e.get("gmv", 0))
        totals["spend"] += float(e.get("expense", 0))
    ctr = round(totals["clicks"] / totals["impressions"] * 100, 2) if totals["impressions"] else 0.0

    return {
        "period": f"{start_date} - {end_date}",
        "impressions": totals["impressions"], "clicks": totals["clicks"], "ctr_pct": ctr,
        "orders": totals["orders"], "items_sold": totals["items_sold"],
        "revenue": totals["revenue"], "spend": totals["spend"],
    }


# ==========================================
# 3. วินิจฉัยตามเงื่อนไข ROAS (rule-based)
# ==========================================
def calculate_roas(data):
    if data["spend"] <= 0:
        return None
    return round(data["revenue"] / data["spend"], 2)


def diagnose(data):
    roas = calculate_roas(data)

    if data["spend"] == 0 and data["impressions"] == 0:
        return {
            "status": "NOT_DELIVERING",
            "decision": "CHECK_CAMPAIGN_SETUP",
            "reason": (
                f"ไม่มี impression และไม่มีการใช้งบเลยในช่วง {data['period']} "
                "แคมเปญไม่ได้แสดงผลจริง ต้องเช็คสถานะแคมเปญ/สต็อกสินค้า/bid/schedule ก่อน"
            ),
            "roas": roas,
        }

    if data["impressions"] < MIN_IMPRESSIONS_FOR_HEALTHY:
        return {
            "status": "LOW_DELIVERY",
            "decision": "INCREASE_BID_OR_BUDGET",
            "reason": f"Impression ต่ำมาก ({data['impressions']}) ควรเพิ่ม bid หรือเปลี่ยนรูปแบบโฆษณา",
            "roas": roas,
        }

    if roas is None:
        return {"status": "NO_SPEND", "decision": "HOLD", "reason": "ยังไม่มีการใช้งบ ข้อมูลไม่พอวิเคราะห์", "roas": roas}

    if roas < TARGET_ROAS * PAUSE_ROAS_MULTIPLIER:
        return {
            "status": "CRITICAL",
            "decision": "PAUSE",
            "reason": f"ROAS ({roas}) ต่ำกว่า {PAUSE_ROAS_MULTIPLIER*100:.0f}% ของเป้า ({TARGET_ROAS}) ขาดทุนหนัก ควรหยุดทันที",
            "roas": roas,
        }

    if roas < TARGET_ROAS:
        return {
            "status": "BELOW_TARGET",
            "decision": "REDUCE_OR_OPTIMIZE",
            "reason": f"ROAS ({roas}) ต่ำกว่าเป้า ({TARGET_ROAS}) ควรลดงบหรือปรับ targeting/ครีเอทีฟ",
            "roas": roas,
        }

    if roas > TARGET_ROAS * SCALE_ROAS_MULTIPLIER:
        return {
            "status": "EXCELLENT",
            "decision": "SCALE_UP",
            "reason": f"ROAS ({roas}) ดีกว่าเป้าถึง {SCALE_ROAS_MULTIPLIER}x ควรเพิ่มงบเพื่อ scale ยอดขาย",
            "roas": roas,
        }

    return {
        "status": "HEALTHY", "decision": "HOLD",
        "reason": f"ROAS ({roas}) อยู่ในเกณฑ์ดี คงงบไว้", "roas": roas,
    }


# ==========================================
# 3.5 สั่งงานจริง (pause / ลดงบ / เพิ่มงบ) ตามผลวินิจฉัย พร้อม safety cap + DRY_RUN
# ==========================================
def apply_shopee_action(campaign_id, decision, current_budget):
    """
    return: (new_budget, executed: bool, note: str)
    - CHECK_CAMPAIGN_SETUP / INCREASE_BID_OR_BUDGET / HOLD / NO_SPEND -> ไม่แตะ budget อัตโนมัติ
      (เพราะเป็นปัญหาเรื่อง setup ไม่ใช่ ROAS ให้คนไปเช็คเองก่อน ป้องกันสั่งงานผิดจุด)
    - PAUSE -> เปลี่ยน state เป็น paused
    - REDUCE_OR_OPTIMIZE -> ลดงบ (มี cap ไม่เกิน MAX_BUDGET_CHANGE_PER_RUN)
    - SCALE_UP -> เพิ่มงบ (มี cap เดียวกัน)
    """
    if current_budget is None:
        return current_budget, False, "ไม่พบ budget ปัจจุบัน ข้ามการสั่งงานอัตโนมัติ (เช็ค API response)"

    if decision in ("HOLD", "NO_SPEND", "CHECK_CAMPAIGN_SETUP", "INCREASE_BID_OR_BUDGET"):
        return current_budget, False, "ไม่แตะ budget อัตโนมัติ (ไม่ใช่ปัญหาระดับ ROAS)"

    reference_id = f"auto-{campaign_id}-{int(datetime.datetime.now().timestamp())}"

    if decision == "PAUSE":
        if DRY_RUN:
            return current_budget, False, "[DRY RUN] จะสั่งหยุดแคมเปญ แต่ยังไม่ได้ยิงจริง"
        shopee.edit_manual_product_ads(campaign_id, reference_id, state="paused")
        return current_budget, True, "สั่งหยุดแคมเปญเรียบร้อย"

    if decision == "REDUCE_OR_OPTIMIZE":
        pct = min(REDUCE_PCT, MAX_BUDGET_CHANGE_PER_RUN)
        new_budget = max(current_budget * (1 - pct), MIN_DAILY_BUDGET_THB)
    elif decision == "SCALE_UP":
        pct = min(SCALE_PCT, MAX_BUDGET_CHANGE_PER_RUN)
        new_budget = current_budget * (1 + pct)
    else:
        return current_budget, False, f"ไม่รู้จัก decision นี้: {decision}"

    if DRY_RUN:
        return new_budget, False, f"[DRY RUN] จะปรับงบจาก {current_budget:.0f} -> {new_budget:.0f} บาท แต่ยังไม่ได้ยิงจริง"

    shopee.edit_manual_product_ads(campaign_id, reference_id, budget=new_budget)
    return new_budget, True, f"ปรับงบจาก {current_budget:.0f} -> {new_budget:.0f} บาท เรียบร้อย"


# ==========================================
# 4. ให้ Gemini วิเคราะห์เชิงลึกเฉพาะรายการที่ "มีปัญหา" + ภาพรวมร้าน
#    (ส่งเฉพาะรายการที่ผิดปกติ ไม่ส่งทุกรายการ กันเปลืองโควตา Gemini ทุกวัน)
# ==========================================
def ask_gemini_analysis(overall, overall_diag, problem_items):
    if problem_items:
        items_text = "\n".join(
            f"- Campaign {it['campaign_id']}: ROAS={it['diag']['roas']} | "
            f"สถานะ={it['diag']['status']} | เหตุผล={it['diag']['reason']}"
            for it in problem_items
        )
    else:
        items_text = "- ไม่มีรายการที่มีปัญหาวันนี้ ทุกรายการอยู่ในเกณฑ์ดี"

    prompt = f"""
    คุณคือผู้เชี่ยวชาญการยิงโฆษณา Shopee Ads กำลังสรุปผลประจำวันให้เจ้าของร้าน

    ภาพรวมทั้งร้าน ช่วง {overall['period']}:
    - การมองเห็น: {overall['impressions']} | คลิก: {overall['clicks']} | CTR: {overall['ctr_pct']}%
    - คำสั่งซื้อ: {overall['orders']} | ยอดขาย: {overall['revenue']} บาท | ค่าโฆษณา: {overall['spend']} บาท
    - ผลวินิจฉัย: {overall_diag['status']} -> {overall_diag['decision']} ({overall_diag['reason']})

    รายการสินค้าที่ระบบตรวจพบว่ามีปัญหาวันนี้:
    {items_text}

    กรุณาสรุปเป็นภาษาไทย กระชับ ไม่เกิน 8 บรรทัด สำหรับส่งเข้า LINE ทุกเช้า:
    1. สรุปภาพรวมสั้นๆว่าร้านวันนี้เป็นอย่างไร
    2. ถ้ามีรายการที่มีปัญหา บอกว่าอะไรน่าจะเป็นสาเหตุหลักและควรทำอะไรก่อน
    3. ถ้าภาพรวมดี ให้แนะนำว่าควร scale เพิ่มตรงไหน
    """

    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    return response.text.strip()


# ==========================================
# 5. ส่งสรุปเข้า LINE (Messaging API)
# ==========================================
def send_line_message(message):
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    target = os.environ.get("LINE_TARGET_ID")
    if not token or not target:
        print("[WARNING] ไม่มี LINE_CHANNEL_ACCESS_TOKEN/LINE_TARGET_ID (พิมพ์แทน)")
        print(message)
        return
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"to": target, "messages": [{"type": "text", "text": message}]}
    resp = requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=payload, timeout=15)
    if resp.status_code == 200:
        print("[LINE] ส่งสรุปเข้า LINE เรียบร้อย")
    else:
        print(f"[ERROR] ส่ง LINE ไม่สำเร็จ ({resp.status_code}): {resp.text}")


# ==========================================
# 6. Main: รันครบ 1 รอบ (เรียกจาก Task Scheduler วันละครั้ง)
# ==========================================
def run_once():
    if not GEMINI_API_KEY:
        print("[ERROR] ยังไม่ได้ตั้งค่า GEMINI_API_KEY")
        return

    today = datetime.date.today()
    start_date = (today - datetime.timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d")
    end_date = today.strftime("%Y%m%d")

    print(f"[{datetime.datetime.now().isoformat()}] เริ่มรอบวิเคราะห์ประจำวัน ({start_date} - {end_date})")
    mode_label = "[DRY RUN] โหมดทดสอบ ไม่แตะงบจริง" if DRY_RUN else "[LIVE] รันจริง จะเปลี่ยนงบจริง"
    print(f"[MODE] {'ข้อมูลจริงจาก Shopee API' if USE_REAL_SHOPEE_API else 'ข้อมูล mock (ยังไม่ตั้งค่า Shopee API credentials)'}")
    print(f"[MODE] {mode_label}\n")

    campaign_ids = get_all_campaign_ids()
    print(f"[FETCH] พบ {len(campaign_ids)} แคมเปญสินค้าในร้าน")

    problem_items = []
    action_log = []
    healthy_count = 0

    for cid in campaign_ids:
        item_data = fetch_single_item_data(cid, start_date, end_date)
        item_diag = diagnose(item_data)
        print(f"   - {cid}: ROAS={item_diag['roas']} | {item_diag['status']} -> {item_diag['decision']}")

        if item_diag["status"] not in ("HEALTHY", "EXCELLENT"):
            problem_items.append({"campaign_id": cid, "data": item_data, "diag": item_diag})

            new_budget, executed, note = apply_shopee_action(
                cid, item_diag["decision"], item_data.get("current_budget")
            )
            print(f"     -> {note}")
            action_log.append({"campaign_id": cid, "decision": item_diag["decision"], "note": note})
        else:
            healthy_count += 1

    overall = fetch_shop_overall_data(start_date, end_date)
    overall_diag = diagnose(overall)

    print(f"\n--- ภาพรวมทั้งร้าน ({overall['period']}) ---")
    print(f"   ROAS: {overall_diag['roas']} | {overall_diag['status']} -> {overall_diag['decision']}")
    print(f"   เหตุผล: {overall_diag['reason']}")
    print(f"\nสรุป: รายการปกติ {healthy_count} รายการ | รายการมีปัญหา {len(problem_items)} รายการ")

    print("\n[AI] กำลังให้ Gemini วิเคราะห์เชิงลึก...\n")
    analysis = ask_gemini_analysis(overall, overall_diag, problem_items)

    report = (
        f"[Shopee Ads] สรุปประจำวัน {today.strftime('%d/%m/%Y')}\n"
        f"โหมด: {'DRY RUN (ไม่แตะงบจริง)' if DRY_RUN else 'LIVE (สั่งงานจริง)'}\n"
        f"รายการทั้งหมด: {len(campaign_ids)} | ปกติ: {healthy_count} | มีปัญหา: {len(problem_items)}\n"
        f"ROAS รวมร้าน: {overall_diag['roas']}\n\n"
        f"{analysis}"
    )

    if action_log:
        actions_text = "\n".join(f"- {a['campaign_id']}: {a['decision']} -> {a['note']}" for a in action_log)
        report += f"\n\n--- การสั่งงานอัตโนมัติ ---\n{actions_text}"

    print("=== รายงานที่จะส่ง ===")
    print(report)
    send_line_message(report)


if __name__ == "__main__":
    run_once()