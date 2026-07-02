import os
import json
import requests

# ---- تنظیمات از Secrets گیت‌هاب خونده میشه ----
HEISENBERG_TOKEN = os.environ["HEISENBERG_TOKEN"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
WALLET = "0x688051ca7cd43270d8f26b48ecdc9beb2d23cf03"

STATE_FILE = "state.json"

API_URL = "https://narrative.agent.heisenberg.so/api/v2/semantic/retrieve/parameterized"

# agent_id 556 = Polymarket Trades (تاریخچه معاملات بر اساس wallet)
TRADES_AGENT_ID = 556


def fetch_trades():
    payload = {
        "agent_id": TRADES_AGENT_ID,
        "params": {
            "proxy_wallet": WALLET,
        },
        "pagination": {"limit": 25, "offset": 0},
        "formatter_config": {"format_type": "raw"},
    }
    headers = {
        "Authorization": f"Bearer {HEISENBERG_TOKEN}",
        "Content-Type": "application/json",
    }
    resp = requests.post(API_URL, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    print("RAW API RESPONSE:", json.dumps(data, ensure_ascii=False)[:3000])

    # نتایج داخل data.results هستن
    if isinstance(data, dict):
        inner = data.get("data")
        if isinstance(inner, dict) and isinstance(inner.get("results"), list):
            return inner["results"]
        if isinstance(data.get("results"), list):
            return data["results"]
    if isinstance(data, list):
        return data
    return []


def load_seen_ids():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return set(data)
        except Exception:
            pass
    return set()


def save_seen_ids(ids):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(list(ids), f, ensure_ascii=False, indent=2)


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text})


def trade_id(trade):
    if trade.get("id"):
        return str(trade["id"])
    if trade.get("transaction_hash"):
        return str(trade["transaction_hash"])
    return "|".join(
        str(trade.get(k, ""))
        for k in ("slug", "outcome", "side", "size", "price", "timestamp")
    )


def format_trade(trade):
    side = (trade.get("side") or "").upper()
    market = trade.get("slug") or "بازار نامشخص"
    outcome = trade.get("outcome") or ""
    size = trade.get("size")
    price = trade.get("price")
    timestamp = trade.get("timestamp") or ""

    if side == "BUY":
        verb = "🟢 باز کرد (خرید)"
    elif side == "SELL":
        verb = "🔴 بست (فروخت)"
    else:
        verb = f"معامله ({side or '?'})"

    lines = [verb]
    lines.append(f"بازار: {market}")
    if outcome:
        lines.append(f"سمت: {outcome}")
    if size is not None:
        lines.append(f"مبلغ: ${size:,.2f}" if isinstance(size, (int, float)) else f"مبلغ: ${size}")
    if price is not None:
        lines.append(f"قیمت: ${price:.4f}" if isinstance(price, (int, float)) else f"قیمت: ${price}")
    if timestamp:
        lines.append(f"زمان: {timestamp}")
    return "\n".join(lines)


def main():
    trades = fetch_trades()
    seen_ids = load_seen_ids()
    is_first_run = len(seen_ids) == 0

    new_trades = [t for t in trades if trade_id(t) not in seen_ids]

    if is_first_run:
        # اولین اجرا: فقط وضعیت رو ذخیره می‌کنیم، برای همه معاملات قدیمی نوتیف نمی‌فرستیم
        send_telegram(
            f"🟢 مانیتورینگ شروع شد\nWallet: {WALLET[:6]}...{WALLET[-4:]}\n"
            f"{len(trades)} معامله اخیر پیدا شد و به‌عنوان تاریخچه ذخیره شد.\n"
            f"از این به بعد فقط معاملات جدید بهت اطلاع داده میشه."
        )
    elif new_trades:
        # جدیدترین معامله معمولاً اول لیسته؛ به ترتیب زمانی (قدیم به جدید) می‌فرستیم
        for trade in reversed(new_trades):
            send_telegram(format_trade(trade))
        print(f"Sent {len(new_trades)} new trade notifications.")
    else:
        print("No new trades.")

    all_ids = seen_ids | {trade_id(t) for t in trades}
    save_seen_ids(all_ids)


if __name__ == "__main__":
    main()
