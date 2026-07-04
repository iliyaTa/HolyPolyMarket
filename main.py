import os
import json
import requests
from datetime import datetime, timezone

# ---- تنظیمات از Secrets گیت‌هاب خونده میشه ----
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
WALLET = "0x688051ca7cd43270d8f26b48ecdc9beb2d23cf03"

STATE_FILE = "state.json"
HISTORY_LIMIT = 10
BIG_TRADE_MULTIPLIER = 3

# ---- API رسمی Polymarket (رایگان، بدون نیاز به توکن) ----
DATA_API = "https://data-api.polymarket.com"
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
TRADER_LINK = f"https://polymarketanalytics.com/traders/{WALLET}#trades"

MAIN_KEYBOARD = {
    "inline_keyboard": [
        [
            {"text": "🆕 آخرین معامله‌ها", "callback_data": "recent3"},
            {"text": "📜 ۱۰ معامله اخیر", "callback_data": "history"},
        ],
        [
            {"text": "📍 پوزیشن‌های باز الان", "callback_data": "positions"},
        ],
    ]
}


# ---------------- Polymarket Data API ----------------

def fetch_activity(limit=25):
    """تاریخچه معاملات (Buy/Sell) این wallet، جدید به قدیم"""
    resp = requests.get(
        f"{DATA_API}/activity",
        params={"user": WALLET, "limit": limit, "type": "TRADE"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


def fetch_positions():
    """پوزیشن‌های الان بازِ این wallet، با قیمت/احتمال زنده"""
    resp = requests.get(
        f"{DATA_API}/positions",
        params={"user": WALLET, "sizeThreshold": 1, "limit": 200},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    positions = data if isinstance(data, list) else []

    # بازارهایی که نتیجه‌شون مشخص شده (curPrice دقیقاً 0 یا 1) یا قابل-نقد-کردن‌ان
    # یعنی دیگه واقعاً «باز» نیستن، فقط منتظر Redeem موندن - حذفشون می‌کنیم
    def is_actually_open(pos):
        if pos.get("redeemable") is True:
            return False
        cur_price = pos.get("curPrice")
        if isinstance(cur_price, (int, float)) and (cur_price <= 0.001 or cur_price >= 0.999):
            return False
        return True

    return [p for p in positions if is_actually_open(p)]


def trade_id(trade):
    if trade.get("transactionHash"):
        return f"{trade['transactionHash']}_{trade.get('asset', '')}"
    return "|".join(
        str(trade.get(k, ""))
        for k in ("slug", "outcome", "side", "size", "price", "timestamp")
    )


def format_timestamp(ts):
    """timestamp از API به‌صورت epoch seconds میاد"""
    try:
        dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        return dt.strftime("%d %b, %H:%M UTC")
    except Exception:
        return str(ts)


# ---------------- Formatting: Trades ----------------

def format_trade(trade, is_big=False):
    size = trade.get("size")
    price = trade.get("price")
    usdc_size = trade.get("usdcSize")
    title = trade.get("title") or "بازار نامشخص"
    outcome = trade.get("outcome") or ""
    slug = trade.get("slug") or trade.get("eventSlug") or ""
    timestamp = trade.get("timestamp")

    side = (trade.get("side") or "").upper()
    if side == "BUY":
        emoji, action = "🟢", "باز کرد"
    elif side == "SELL":
        emoji, action = "🔴", "بست"
    else:
        emoji, action = "⚪️", "معامله"

    market_link = f"https://polymarket.com/event/{slug}" if slug else None

    header = f"{emoji} <b>{action}</b>"
    if is_big:
        header = f"🚨 <b>معامله بزرگ!</b> {header}"
    lines = [header]

    if market_link:
        lines.append(f'📊 <a href="{market_link}">{title}</a>')
    else:
        lines.append(f"📊 {title}")

    if outcome:
        odds_txt = f" (احتمال: {price*100:.1f}%)" if isinstance(price, (int, float)) else ""
        lines.append(f"↳ سمت: <b>{outcome}</b>{odds_txt}")

    if isinstance(usdc_size, (int, float)):
        lines.append(f"💰 مبلغ: <b>${usdc_size:,.0f}</b>")
    elif isinstance(size, (int, float)) and isinstance(price, (int, float)):
        lines.append(f"💰 مبلغ: <b>${size * price:,.0f}</b>")

    if timestamp:
        lines.append(f"🕒 {format_timestamp(timestamp)}")

    lines.append(f'🔗 <a href="{TRADER_LINK}">مشاهده پروفایل تریدر</a>')

    return "\n".join(lines)


def average_usdc_size(trades_history, exclude_id=None):
    values = [
        t.get("usdcSize") for t in trades_history
        if isinstance(t.get("usdcSize"), (int, float)) and trade_id(t) != exclude_id
    ]
    if not values:
        return None
    return sum(values) / len(values)


# ---------------- Formatting: Positions (زنده) ----------------

def format_position(pos):
    title = pos.get("title") or "بازار نامشخص"
    outcome = pos.get("outcome") or ""
    slug = pos.get("slug") or pos.get("eventSlug") or ""
    cur_price = pos.get("curPrice")
    avg_price = pos.get("avgPrice")
    initial_value = pos.get("initialValue")
    current_value = pos.get("currentValue")
    cash_pnl = pos.get("cashPnl")
    percent_pnl = pos.get("percentPnl")

    market_link = f"https://polymarket.com/event/{slug}" if slug else None
    market_display = f'<a href="{market_link}">{title}</a>' if market_link else title

    lines = [f"📊 {market_display}"]
    if outcome:
        lines.append(f"↳ سمت: <b>{outcome}</b>")

    if isinstance(cur_price, (int, float)):
        odds_line = f"🎯 احتمال الان: <b>{cur_price*100:.1f}%</b>"
        if isinstance(avg_price, (int, float)):
            odds_line += f"  (خرید با {avg_price*100:.1f}%)"
        lines.append(odds_line)

    if isinstance(initial_value, (int, float)) and isinstance(current_value, (int, float)):
        lines.append(f"💵 سرمایه: ${initial_value:,.0f} ← ارزش الان: ${current_value:,.0f}")

    if isinstance(cash_pnl, (int, float)):
        emoji = "📈" if cash_pnl >= 0 else "📉"
        sign = "+" if cash_pnl >= 0 else ""
        pct_txt = f" ({sign}{percent_pnl:.1f}%)" if isinstance(percent_pnl, (int, float)) else ""
        lines.append(f"{emoji} سود/زیان: <b>{sign}${cash_pnl:,.0f}</b>{pct_txt}")

    return "\n".join(lines)


def build_positions_reply():
    positions = fetch_positions()
    if not positions:
        return "الان هیچ پوزیشن بازی نداره."
    positions = sorted(positions, key=lambda p: p.get("currentValue") or 0, reverse=True)
    blocks = [format_position(p) for p in positions]
    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    header = f"📍 <b>پوزیشن‌های باز الان</b> (بروزرسانی: {now})"
    return header + SEPARATOR + SEPARATOR.join(blocks)


# ---------------- Telegram ----------------

def send_telegram(text, keyboard=None):
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if keyboard:
        payload["reply_markup"] = json.dumps(keyboard)
    requests.post(f"{TELEGRAM_API}/sendMessage", json=payload)


def send_telegram_to(chat_id, text, keyboard=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if keyboard:
        payload["reply_markup"] = json.dumps(keyboard)
    requests.post(f"{TELEGRAM_API}/sendMessage", json=payload)


def answer_callback(callback_query_id):
    requests.post(f"{TELEGRAM_API}/answerCallbackQuery", json={"callback_query_id": callback_query_id})


def get_telegram_updates(offset):
    params = {"timeout": 0}
    if offset is not None:
        params["offset"] = offset
    resp = requests.get(f"{TELEGRAM_API}/getUpdates", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("result", [])


SEPARATOR = "\n➖➖➖➖➖\n"


def build_recent3_reply(trades_history):
    if not trades_history:
        return "هنوز هیچ معامله‌ای ثبت نشده."
    recent = trades_history[:3]
    blocks = [format_trade(t) for t in recent]
    return "🆕 <b>آخرین معامله‌ها</b>" + SEPARATOR + SEPARATOR.join(blocks)


def build_history_reply(trades_history):
    if not trades_history:
        return "هنوز هیچ معامله‌ای ذخیره نشده."
    recent = trades_history[:HISTORY_LIMIT]
    blocks = [format_trade(t) for t in recent]
    return f"📜 <b>{len(recent)} معامله اخیر</b>" + SEPARATOR + SEPARATOR.join(blocks)


def handle_commands(last_update_id, trades_history):
    updates = get_telegram_updates(offset=(last_update_id + 1) if last_update_id else None)
    new_last_id = last_update_id
    for update in updates:
        new_last_id = update["update_id"]

        callback = update.get("callback_query")
        if callback:
            data = callback.get("data")
            chat_id = callback.get("message", {}).get("chat", {}).get("id")
            if data == "recent3":
                send_telegram_to(chat_id, build_recent3_reply(trades_history), MAIN_KEYBOARD)
            elif data == "history":
                send_telegram_to(chat_id, build_history_reply(trades_history), MAIN_KEYBOARD)
            elif data == "positions":
                send_telegram_to(chat_id, build_positions_reply(), MAIN_KEYBOARD)
            answer_callback(callback.get("id"))
            continue

        message = update.get("message") or update.get("channel_post")
        if not message:
            continue
        text = (message.get("text") or "").strip().lower()
        chat_id = message.get("chat", {}).get("id")

        if text.startswith("/start"):
            send_telegram_to(chat_id, build_recent3_reply(trades_history), MAIN_KEYBOARD)
        elif text.startswith("/history"):
            send_telegram_to(chat_id, build_history_reply(trades_history), MAIN_KEYBOARD)
        elif text.startswith("/positions"):
            send_telegram_to(chat_id, build_positions_reply(), MAIN_KEYBOARD)

    return new_last_id


# ---------------- State ----------------

def load_state():
    default = {"seen_ids": [], "trades": [], "last_update_id": None}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                default.update({k: v for k, v in data.items() if k in default})
            elif isinstance(data, list):
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

    trades = fetch_activity(limit=25)
    new_trades = [t for t in trades if trade_id(t) not in seen_ids]
    new_trades_chronological = list(reversed(new_trades))

    if is_first_run:
        send_telegram(
            f"🟢 <b>مانیتورینگ شروع شد</b>\n"
            f'👤 <a href="{TRADER_LINK}">{WALLET[:6]}...{WALLET[-4:]}</a>\n'
            f"{len(trades)} معامله اخیر پیدا شد و ذخیره شد.\n\n"
            f"از این به بعد فقط معاملات جدید بهت اطلاع داده میشه.",
            MAIN_KEYBOARD,
        )
    elif new_trades_chronological:
        for trade in new_trades_chronological:
            avg_before = average_usdc_size(trades_history, exclude_id=trade_id(trade))
            is_big = (
                avg_before is not None
                and isinstance(trade.get("usdcSize"), (int, float))
                and trade["usdcSize"] > avg_before * BIG_TRADE_MULTIPLIER
            )
            send_telegram(format_trade(trade, is_big=is_big))
        print(f"Sent {len(new_trades_chronological)} new trade notifications.")
    else:
        print("No new trades.")

    existing_ids = {trade_id(t) for t in trades_history}
    new_items = [t for t in trades if trade_id(t) not in existing_ids]
    trades_history = new_items + trades_history
    trades_history = trades_history[:100]
    seen_ids |= {trade_id(t) for t in trades}

    new_last_update_id = handle_commands(state.get("last_update_id"), trades_history)

    save_state({
        "seen_ids": list(seen_ids),
        "trades": trades_history,
        "last_update_id": new_last_update_id,
    })


if __name__ == "__main__":
    main()
