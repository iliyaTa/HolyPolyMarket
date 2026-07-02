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


def format_timestamp(ts):
    """تبدیل 2026-07-02T20:29:59Z به یه فرمت خواناتر"""
    try:
        from datetime import datetime
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
        return dt.strftime("%d %b, %H:%M UTC")
    except Exception:
        return ts


def format_trade(trade):
    side = (trade.get("side") or "").upper()
    slug = trade.get("slug") or ""
    outcome = trade.get("outcome") or ""
    size = trade.get("size")
    price = trade.get("price")
    timestamp = trade.get("timestamp") or ""

    if side == "BUY":
        emoji, action = "🟢", "باز کرد"
    elif side == "SELL":
        emoji, action = "🔴", "بست"
    else:
        emoji, action = "⚪️", side or "نامشخص"

    market_display = slug.replace("-", " ").title() if slug else "بازار نامشخص"
    market_link = f"https://polymarket.com/event/{slug}" if slug else None

    lines = [f"{emoji} <b>{action}</b>"]

    if market_link:
        lines.append(f'📊 <a href="{market_link}">{market_display}</a>')
    else:
        lines.append(f"📊 {market_display}")

    if outcome:
        lines.append(f"↳ سمت: <b>{outcome}</b>")

    if isinstance(size, (int, float)) and isinstance(price, (int, float)):
        total = size * price
        lines.append(f"💰 {size:,.0f} × ${price:.3f} = <b>${total:,.0f}</b>")
    elif size is not None:
        lines.append(f"💰 مبلغ: {size}")

    if timestamp:
        lines.append(f"🕒 {format_timestamp(timestamp)}")

    trader_link = f"https://polymarketanalytics.com/traders/{WALLET}#trades"
    lines.append(f'🔗 <a href="{trader_link}">مشاهده پروفایل تریدر</a>')

    return "\n".join(lines)


# ---------------- Telegram ----------------

def send_telegram(text):
    requests.post(f"{TELEGRAM_API}/sendMessage", json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    })


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

        SEPARATOR = "\n➖➖➖➖➖\n"

        if text.startswith("/start"):
            if not trades_history:
                reply = "هنوز هیچ معامله‌ای ثبت نشده."
            else:
                recent = trades_history[:3]
                blocks = [format_trade(t) for t in recent]
                reply = "📈 <b>۳ پوزیشن آخر</b>" + SEPARATOR + SEPARATOR.join(blocks)
            requests.post(f"{TELEGRAM_API}/sendMessage", json={
                "chat_id": chat_id, "text": reply,
                "parse_mode": "HTML", "disable_web_page_preview": True,
            })

        elif text.startswith("/history"):
            if not trades_history:
                reply = "هنوز هیچ معامله‌ای ذخیره نشده."
            else:
                recent = trades_history[:HISTORY_LIMIT]
                blocks = [format_trade(t) for t in recent]
                reply = f"📜 <b>آخرین {len(recent)} معامله</b>" + SEPARATOR + SEPARATOR.join(blocks)
            requests.post(f"{TELEGRAM_API}/sendMessage", json={
                "chat_id": chat_id, "text": reply,
                "parse_mode": "HTML", "disable_web_page_preview": True,
            })
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
        trader_link = f"https://polymarketanalytics.com/traders/{WALLET}#trades"
        send_telegram(
            f"🟢 <b>مانیتورینگ شروع شد</b>\n"
            f'👤 <a href="{trader_link}">{WALLET[:6]}...{WALLET[-4:]}</a>\n'
            f"{len(trades)} معامله اخیر پیدا شد و ذخیره شد.\n\n"
            f"از این به بعد فقط معاملات جدید بهت اطلاع داده میشه.\n"
            f"دستورها: /history (۱۰ معامله آخر) — /start (۳ پوزیشن آخر)"
        )
    elif new_trades:
        for trade in reversed(new_trades):
            send_telegram(format_trade(trade))
        print(f"Sent {len(new_trades)} new trade notifications.")
    else:
        print("No new trades.")

    # آپدیت تاریخچه: جدیدترین‌ها اول لیست
    # trades از API همیشه با ترتیب «جدید به قدیم» میاد، پس باید همون ترتیب حفظ بشه
    existing_ids_in_history = {trade_id(t) for t in trades_history}
    new_items = [t for t in trades if trade_id(t) not in existing_ids_in_history]
    trades_history = new_items + trades_history  # جدیدها میرن جلوی لیست، بدون بهم‌ریختن ترتیب
    trades_history = trades_history[:100]  # فقط ۱۰۰ تای آخر رو نگه دار
    seen_ids |= {trade_id(t) for t in trades}

    # چک کردن دستور /history
    new_last_update_id = handle_commands(state.get("last_update_id"), trades_history)

    save_state({
        "seen_ids": list(seen_ids),
        "trades": trades_history,
        "last_update_id": new_last_update_id,
    })


if __name__ == "__main__":
    main()
