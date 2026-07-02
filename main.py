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

    # پاسخ ممکنه مستقیم لیست باشه یا داخل یه کلید مثل "results" بیاد
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("results", "data", "trades"):
            if key in data and isinstance(data[key], list):
                return data[key]
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
    # سعی می‌کنیم یه شناسه یکتا برای هر معامله بسازیم، حتی اگه API فیلد id نده
    for key in ("id", "trade_id", "tx_hash", "transaction_hash"):
        if trade.get(key):
            return str(trade[key])
    return "|".join(
        str(trade.get(k, ""))
        for k in ("market", "outcome", "side", "value", "price", "trade_time", "timestamp")
    )


def format_trade(trade):
    side = (trade.get("side") or trade.get("action") or "").upper()
    market = (
        trade.get("market")
        or trade.get("market_title")
        or trade.get("title")
        or "بازار نامشخص"
    )
    outcome = trade.get("outcome") or trade.get("outcome_name") or ""
    value = trade.get("value") or trade.get("amount") or trade.get("size")
    price = trade.get("price")
    trade_time = trade.get("trade_time") or trade.get("timestamp") or ""

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
    if value is not None:
        lines.append(f"مبلغ: ${value}")
    if price is not None:
        lines.append(f"قیمت: ${price}")
    if trade_time:
        lines.append(f"زمان: {trade_time}")
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
