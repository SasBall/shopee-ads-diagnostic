import os
import json
from datetime import datetime
from shopee_api import get_shopee_ads_data


def run_roas_guard():
    ads_items = get_shopee_ads_data()
    logs = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for item in ads_items:
        spend = item.get("spend", 0)
        revenue = item.get("revenue", 0)
        impressions = item.get("impressions", 0)
        bid_price = item.get("bid_price", 1.0)
        item_id = item.get("item_id")
        item_name = item.get("item_name", f"Item-{item_id}")

        roas = (revenue / spend) if spend > 0 else 0

        # Rule 1: Impression = 0 -> ปรับ Bid ขึ้น
        if impressions == 0:
            new_bid = round(bid_price + 0.2, 2)
            action = f"⚠️ [{item_name}] Impression เป็น 0 -> ปรับ Bid ขึ้นจาก {bid_price} เป็น {new_bid} บาท"
            logs.append({"time": timestamp, "item_id": item_id, "action": action, "type": "BID_UP"})

        # Rule 2: Spend มากกว่า 100 แต่ ROAS < 3.0 -> ปรับ Bid ลง
        elif spend >= 100 and roas < 3.0:
            new_bid = max(round(bid_price - 0.2, 2), 0.5)
            action = f"🔻 [{item_name}] ROAS ต่ำ ({roas:.2f}) -> ปรับ Bid ลงจาก {bid_price} เป็น {new_bid} บาท"
            logs.append({"time": timestamp, "item_id": item_id, "action": action, "type": "BID_DOWN"})

        # Rule 3: ROAS > 8.0 -> ปรับ Bid ขึ้นสเกลยอด
        elif roas >= 8.0 and spend > 0:
            new_bid = round(bid_price + 0.1, 2)
            action = f"🟢 [{item_name}] ROAS ดีมาก ({roas:.2f}) -> ปรับ Bid ขึ้นจาก {bid_price} เป็น {new_bid} บาท"
            logs.append({"time": timestamp, "item_id": item_id, "action": action, "type": "BID_BOOST"})

    # บันทึก Log ลงไฟล์ JSON รายวัน
    os.makedirs("logs", exist_ok=True)
    log_filename = f"logs/actions_{datetime.now().strftime('%Y-%m-%d')}.json"

    try:
        with open(log_filename, 'r', encoding='utf-8') as f:
            existing_logs = json.load(f)
    except FileNotFoundError:
        existing_logs = []

    existing_logs.extend(logs)

    with open(log_filename, 'w', encoding='utf-8') as f:
        json.dump(existing_logs, f, ensure_ascii=False, indent=2)

    print(f"✅ บันทึก Log การควบคุม ROAS เรียบร้อยแล้ว ({len(logs)} actions)")


if __name__ == "__main__":
    run_roas_guard()