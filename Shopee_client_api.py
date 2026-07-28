"""
shopee_api_client.py
-----------------------
เชื่อมต่อ Shopee Open Platform API v2 จริง (ไม่ใช่ mock แล้ว)
ครอบคลุม: การ sign request, การขอ/refresh access token, และการดึง performance โฆษณา

ก่อนใช้ไฟล์นี้ ต้องทำสิ่งเหล่านี้นอกโค้ดก่อน:
1. สมัคร https://open.shopee.com สร้าง App -> ได้ partner_id, partner_key
2. ติดต่อ Shopee Partner Support ขอเปิดสิทธิ์ "Ads API" ให้ App (ไม่ได้มาอัตโนมัติ)
3. ทำ OAuth Authorization ให้ร้านของคุณ Authorize App -> ได้ shop_id, code
4. เอา code ไปแลก access_token + refresh_token ครั้งแรก (ใช้ฟังก์ชัน get_access_token ด้านล่าง)

หมายเหตุสำคัญเรื่องความถูกต้อง: ชื่อ field ในผลลัพธ์ (response) อาจเปลี่ยนแปลงได้ตาม
เวอร์ชัน API เพราะ Shopee อัปเดต Ads API บ่อย แนะนำให้เทียบกับเอกสารจริงที่
https://open.shopee.com/documents?module=105&type=1 (ต้อง login ด้วย partner account ถึงดูได้)
คู่กับโค้ดนี้เสมอ ก่อนใช้กับเงินจริง
"""

import time
import hashlib
import hmac
import json
import requests

# ==========================================
# ตั้งค่าการเชื่อมต่อ
# ==========================================
PARTNER_ID = None          # int, ได้จาก Shopee Open Platform ตอนสร้าง App
PARTNER_KEY = None         # str, เก็บเป็นความลับ ห้ามหลุด
SHOP_ID = None             # int, ได้ตอน Authorize ร้าน
ACCESS_TOKEN = None        # str, ได้ตอนแลก code หรือหลัง refresh

# Host: ใช้ตัว Live จริง หรือ Test สำหรับ sandbox ทดสอบก่อน
HOST_LIVE = "https://partner.shopeemobile.com"
HOST_TEST = "https://partner.test-stable.shopeemobile.com"
HOST = HOST_LIVE  # เปลี่ยนเป็น HOST_TEST ตอนทดสอบใน sandbox ก่อนใช้จริง


def _sign(path, partner_id, partner_key, timestamp, access_token="", shop_id=""):
    """
    Shopee v2 ใช้ HMAC-SHA256 sign request
    base_string รูปแบบ: partner_id + api_path + timestamp [+ access_token + shop_id ถ้ามี]
    """
    base_string = f"{partner_id}{path}{timestamp}{access_token}{shop_id}"
    sign = hmac.new(
        partner_key.encode("utf-8"),
        base_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return sign


def _call_api(path, params=None, body=None, method="GET", need_shop_id=True):
    """
    ฟังก์ชันกลางเรียก Shopee API พร้อม sign อัตโนมัติ
    """
    if not PARTNER_ID or not PARTNER_KEY:
        raise ValueError("ต้องตั้งค่า PARTNER_ID และ PARTNER_KEY ก่อนเรียก API")

    timestamp = int(time.time())
    sign = _sign(
        path, PARTNER_ID, PARTNER_KEY, timestamp,
        access_token=ACCESS_TOKEN or "",
        shop_id=SHOP_ID or "" if need_shop_id else "",
    )

    query = {
        "partner_id": PARTNER_ID,
        "timestamp": timestamp,
        "sign": sign,
    }
    if need_shop_id and SHOP_ID:
        query["shop_id"] = SHOP_ID
    if ACCESS_TOKEN:
        query["access_token"] = ACCESS_TOKEN
    if params:
        query.update(params)

    url = f"{HOST}{path}"

    if method == "GET":
        resp = requests.get(url, params=query, timeout=30)
    else:
        resp = requests.post(url, params=query, json=body or {}, timeout=30)

    resp.raise_for_status()
    data = resp.json()

    if data.get("error"):
        raise RuntimeError(f"Shopee API error: {data.get('error')} - {data.get('message')}")

    return data


# ==========================================
# 1. Authorization / Token (ทำครั้งแรกครั้งเดียว)
# ==========================================
def get_authorization_url(redirect_url):
    """
    สร้าง URL ให้เปิดในเบราว์เซอร์เพื่อ Authorize ร้าน (ทำครั้งแรกครั้งเดียว)
    หลัง Authorize เสร็จ Shopee จะ redirect กลับมาพร้อม ?code=xxx&shop_id=xxx ใน URL
    """
    path = "/api/v2/shop/auth_partner"
    timestamp = int(time.time())
    sign = _sign(path, PARTNER_ID, PARTNER_KEY, timestamp)
    return (
        f"{HOST}{path}?partner_id={PARTNER_ID}&timestamp={timestamp}"
        f"&sign={sign}&redirect={redirect_url}"
    )


def get_access_token(code, shop_id):
    """
    เอา code ที่ได้จากการ Authorize มาแลก access_token + refresh_token ครั้งแรก
    เก็บผลลัพธ์ (access_token, refresh_token, shop_id) ไว้ใช้ต่อ อย่าทำซ้ำทุกครั้ง
    """
    path = "/api/v2/auth/token/get"
    timestamp = int(time.time())
    sign = _sign(path, PARTNER_ID, PARTNER_KEY, timestamp)

    url = f"{HOST}{path}"
    query = {"partner_id": PARTNER_ID, "timestamp": timestamp, "sign": sign}
    body = {"code": code, "shop_id": int(shop_id), "partner_id": PARTNER_ID}

    resp = requests.post(url, params=query, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()  # {"access_token":..., "refresh_token":..., "expire_in":..., ...}


def refresh_access_token(refresh_token, shop_id):
    """
    access_token มีอายุ (ปกติ 4 ชม.) ต้อง refresh เป็นระยะด้วย refresh_token
    (refresh_token เองก็มีอายุ ~30 วัน ต้องเก็บ shop_id คู่กันไว้เสมอ)
    """
    path = "/api/v2/auth/access_token/get"
    timestamp = int(time.time())
    sign = _sign(path, PARTNER_ID, PARTNER_KEY, timestamp)

    url = f"{HOST}{path}"
    query = {"partner_id": PARTNER_ID, "timestamp": timestamp, "sign": sign}
    body = {
        "refresh_token": refresh_token,
        "shop_id": int(shop_id),
        "partner_id": PARTNER_ID,
    }

    resp = requests.post(url, params=query, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ==========================================
# 2. Performance โฆษณา (ต้องมีสิทธิ์ Ads API ที่ Shopee อนุมัติแล้ว)
# ==========================================
def get_shop_overall_daily_performance(start_date, end_date):
    """
    ดึง performance รวมทั้งร้าน (เทียบเท่า Image 2 ในแชท) รายวัน
    start_date/end_date รูปแบบ YYYYMMDD
    """
    path = "/api/v2/ads/get_all_cpc_ads_daily_performance"
    params = {"start_date": start_date, "end_date": end_date}
    return _call_api(path, params=params, method="GET")


def get_campaign_id_list(ad_type="all", offset=0, limit=50):
    """ดึงรายชื่อ campaign_id ทั้งหมด (ใช้หา id ก่อนดึง performance รายสินค้า) """
    path = "/api/v2/ads/get_product_level_campaign_id_list"
    params = {"ad_type": ad_type, "offset": offset, "limit": limit}
    return _call_api(path, params=params, method="GET")


def get_product_campaign_daily_performance(campaign_id_list, start_date, end_date):
    """
    ดึง performance รายวันของแคมเปญสินค้ารายการเดียว (เทียบเท่า Image 1 ในแชท)
    campaign_id_list: list ของ int, start_date/end_date รูปแบบ YYYYMMDD
    """
    path = "/api/v2/ads/get_product_campaign_daily_performance"
    params = {
        "campaign_id_list": ",".join(str(c) for c in campaign_id_list),
        "start_date": start_date,
        "end_date": end_date,
    }
    return _call_api(path, params=params, method="GET")


def get_total_ads_balance():
    """เช็คเครดิตโฆษณาคงเหลือของร้าน"""
    path = "/api/v2/ads/get_total_balance"
    return _call_api(path, method="GET")


def get_campaign_setting_info(campaign_id_list, info_type_list=None):
    """
    ดึงรายละเอียดการตั้งค่าแคมเปญ (รวม budget ปัจจุบัน) ของ campaign_id ที่ระบุ
    info_type_list ตัวอย่าง: [1] สำหรับ common info (ต้องเทียบเอกสารจริงอีกที)
    """
    path = "/api/v2/ads/get_product_level_campaign_setting_info"
    params = {
        "campaign_id_list": ",".join(str(c) for c in campaign_id_list),
        "info_type_list": ",".join(str(i) for i in (info_type_list or [1])),
    }
    return _call_api(path, params=params, method="GET")


def edit_manual_product_ads(campaign_id, reference_id, budget=None, state=None):
    """
    สั่งแก้ไขแคมเปญ Manual Product Ads จริง (ปรับ budget และ/หรือเปลี่ยนสถานะ)
    - budget: งบใหม่ (บาท, float) หรือ None ถ้าไม่ต้องการเปลี่ยน
    - state: "ongoing" (เปิด) หรือ "paused" (พัก) หรือ None ถ้าไม่ต้องการเปลี่ยนสถานะ
    - reference_id: string unique กันสั่งซ้ำโดยไม่ตั้งใจ (Shopee ใช้กันเหนียว)

    ⚠️ ต้องทดสอบกับ Sandbox (HOST_TEST) ก่อนใช้กับแคมเปญเงินจริงเสมอ
    ⚠️ ชื่อ field/ค่า state ต้องเทียบกับเอกสาร Shopee ปัจจุบันอีกที เผื่อเปลี่ยนแปลง
    """
    path = "/api/v2/ads/edit_manual_product_ads"
    body = {"campaign_id": int(campaign_id), "reference_id": reference_id}
    if budget is not None:
        body["budget"] = round(float(budget), 2)
    if state is not None:
        body["state"] = state

    return _call_api(path, body=body, method="POST")