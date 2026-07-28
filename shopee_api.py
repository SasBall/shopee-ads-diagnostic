import os
import time
import hmac
import hashlib
import requests

PARTNER_ID = int(os.environ.get("SHOPEE_PARTNER_ID", 0))
PARTNER_KEY = os.environ.get("SHOPEE_PARTNER_KEY", "")
SHOP_ID = int(os.environ.get("SHOPEE_SHOP_ID", 0))
ACCESS_TOKEN = os.environ.get("SHOPEE_ACCESS_TOKEN", "")
HOST = "https://partner.shopeemobile.com"


def generate_sign(path, timestamp):
    base_string = f"{PARTNER_ID}{path}{timestamp}{ACCESS_TOKEN}{SHOP_ID}"
    return hmac.new(
        PARTNER_KEY.encode('utf-8'),
        base_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()


def get_shopee_ads_data():
    """ ดึงข้อมูล Performance โฆษณารายชิ้นจาก Shopee """
    path = "/api/v2/pas/get_performance"
    timestamp = int(time.time())

    # กรณีไม่มี Keys ให้ใช้ Mock Data สำหรับทดสอบระบบ
    if not PARTNER_ID or not PARTNER_KEY:
        return [
            {"item_id": 101, "item_name": "สินค้า A (Impression=0)", "impressions": 0, "spend": 0.0, "revenue": 0.0,
             "bid_price": 1.0},
            {"item_id": 102, "item_name": "สินค้า B (ROAS ต่ำ)", "impressions": 1200, "spend": 300.0, "revenue": 450.0,
             "bid_price": 2.5},
            {"item_id": 103, "item_name": "สินค้า C (ROAS ดีมาก)", "impressions": 4500, "spend": 500.0,
             "revenue": 5000.0, "bid_price": 1.8}
        ]

    sign = generate_sign(path, timestamp)
    params = {
        "partner_id": PARTNER_ID,
        "timestamp": timestamp,
        "access_token": ACCESS_TOKEN,
        "shop_id": SHOP_ID,
        "sign": sign,
        "period": "today"
    }

    try:
        res = requests.get(f"{HOST}{path}", params=params, timeout=15).json()
        return res.get("response", []) if res.get("error") == "" else []
    except Exception as e:
        print(f"⚠️ Shopee API Fetch Error: {e}")
        return []