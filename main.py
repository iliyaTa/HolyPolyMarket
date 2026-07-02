import os
import json
import requests

# ---- تنظیمات از Secrets گیت‌هاب خونده میشه ----
HEISENBERG_TOKEN = os.environ["HEISENBERG_TOKEN"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
WALLET = "0x688051ca7cd43270d8f26b48ecdc9beb2d23cf03"

STATE_FILE = "state.json"
HISTORY_LIMIT = 10  # چند تا معامله آخر رو با /history نشون بده

API_URL = "https://narrative.agent.heisenberg.so/api/v2/semantic/retrieve/parameterized"
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# agent_id 556 = Polymarket Trades (تاریخچه معاملات بر اساس wallet)
TRADES_AGENT_ID = 556


# ---------------- Heisenberg API ----------------

def fetch_trades():
    payload = {
        "agent_id": TRADES_AGENT_ID,
        "params": {"proxy_wallet": WALLET},
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

    if isinstance(data, dict):
        inner = data.get("data")
        if isinstance(inner, dict) and isinstance(inner.get("results"), list):
            return inner["results"]
        if isinstance(data.get("results"), list):
            return data["results"]
    if isinstance(data, list):
        return data
    return []


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

    lines = [verb, f"بازار: {market}"]
    if outcome:
        lines.append(f"سمت: {outcome}")
    if size is not None:
        lines.append(f"مبلغ: ${size:,.2f}" if isinstance(size, (int, float)) else f"مبلغ: ${size}")
    if price is not None:
        lines.append(f"قیمت: ${price:.4f}" if isinstance(price, (int, float)) else f"قیمت: ${price}")
    if timestamp:
        lines.append(f"زمان: {timestamp}")
    return "\n".join(lines)


# ---------------- Telegram ----------------

def send_telegram(text):
    requests.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": text})


def get_telegram_updates(offset):
    params = {"timeout": 0}
    if offset is not None:
        params["offset"] = offset
    resp = requests.get(f"{TELEGRAM_API}/getUpdates", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("result", [])


def handle_commands(last_update_id, trades_history):
    """چک می‌کنه ببینه کاربر دستوری مثل /history فرستاده یا نه، جواب میده."""
    updates = get_telegram_updates(offset=(last_update_id + 1) if last_update_id else None)
    new_last_id = last_update_id
    for update in updates:
        new_last_id = update["update_id"]
        message = update.get("message") or update.get("channel_post")
        if not message:
            continue
        text = (message.get("text") or "").strip().lower()
        chat_id = message.get("chat", {}).get("id")

        if text.startswith("/start"):
            if not trades_history:
                reply = "👋 سلام! هنوز هیچ معامله‌ای ثبت نشده."
            else:
                recent = trades_history[:3]
                blocks = [format_trade(t) for t in recent]
                reply = "👋 سلام! ۳ پوزیشن آخر:\n\n" + "\n\n".join(blocks)
            requests.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": reply})

        elif text.startswith("/history"):
            if not trades_history:
                reply = "هنوز هیچ معامله‌ای ذخیره نشده."
            else:
                recent = trades_history[:HISTORY_LIMIT]
                blocks = [format_trade(t) for t in recent]
                reply = f"📜 آخرین {len(recent)} معامله:\n\n" + "\n\n".join(blocks)
            requests.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": reply})
    return new_last_id


# ---------------- State ----------------

def load_state():
    default = {"seen_ids": [], "trades": [], "last_update_id": None}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                default.update(data)
            elif isinstance(data, list):
                # فرمت خیلی قدیمی: فقط لیست id ها بود
                default["seen_ids"] = data
        except Exception:
            pass
    return default


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ---------------- Main ----------------

def main():
    state = load_state()
    seen_ids = set(state.get("seen_ids") or [])
    trades_history = state.get("trades") or []
    is_first_run = len(seen_ids) == 0

    trades = fetch_trades()
    new_trades = [t for t in trades if trade_id(t) not in seen_ids]

    if is_first_run:
        send_telegram(
            f"🟢 مانیتورینگ شروع شد\nWallet: {WALLET[:6]}...{WALLET[-4:]}\n"
            f"{len(trades)} معامله اخیر پیدا شد و به‌عنوان تاریخچه ذخیره شد.\n"
            f"از این به بعد فقط معاملات جدید بهت اطلاع داده میشه.\n"
            f"برای دیدن تاریخچه هر وقت خواستی، بنویس /history"
        )
    elif new_trades:
        for trade in reversed(new_trades):
            send_telegram(format_trade(trade))
        print(f"Sent {len(new_trades)} new trade notifications.")
    else:
        print("No new trades.")

    # آپدیت تاریخچه: جدیدترین‌ها اول لیست
    seen_ids |= {trade_id(t) for t in trades}
    existing_ids_in_history = {trade_id(t) for t in trades_history}
    for t in trades:
        if trade_id(t) not in existing_ids_in_history:
            trades_history.insert(0, t)
    trades_history = trades_history[:100]  # فقط ۱۰۰ تای آخر رو نگه دار

    # چک کردن دستور /history
    new_last_update_id = handle_commands(state.get("last_update_id"), trades_history)

    save_state({
        "seen_ids": list(seen_ids),
        "trades": trades_history,
        "last_update_id": new_last_update_id,
    })


if __name__ == "__main__":
    main()
