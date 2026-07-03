import os
import json
import requests
from datetime import datetime

# ---- تنظیمات از Secrets گیت‌هاب خونده میشه ----
HEISENBERG_TOKEN = os.environ["HEISENBERG_TOKEN"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
WALLET = "0x688051ca7cd43270d8f26b48ecdc9beb2d23cf03"

STATE_FILE = "state.json"
HISTORY_LIMIT = 10
BIG_TRADE_MULTIPLIER = 3  # اگه اندازه معامله بیشتر از ۳ برابر میانگین بود، هشدار بده

API_URL = "https://narrative.agent.heisenberg.so/api/v2/semantic/retrieve/parameterized"
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

TRADES_AGENT_ID = 556

TRADER_LINK = f"https://polymarketanalytics.com/traders/{WALLET}#trades"

MAIN_KEYBOARD = {
    "inline_keyboard": [[
        {"text": "🆕 آخرین معامله‌ها", "callback_data": "recent3"},
        {"text": "📜 ۱۰ معامله اخیر", "callback_data": "history"},
    ]]
}


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
    try:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
        return dt.strftime("%d %b, %H:%M UTC")
    except Exception:
        return ts


# ---------------- Positions / PnL ----------------

def update_positions_and_get_pnl(positions, trade):
    token_id = trade.get("token_id") or trade.get("slug", "") + trade.get("outcome", "")
    side = (trade.get("side") or "").upper()
    size = trade.get("size")
    price = trade.get("price")

    if not isinstance(size, (int, float)) or not isinstance(price, (int, float)):
        return None, None

    pos = positions.get(token_id, {"size": 0.0, "cost": 0.0})

    if side == "BUY":
        pos["size"] += size
        pos["cost"] += size * price
        positions[token_id] = pos
        return None, None

    elif side == "SELL":
        avg_cost = (pos["cost"] / pos["size"]) if pos["size"] > 0 else None
        realized_pnl = None
        if avg_cost is not None:
            realized_pnl = size * (price - avg_cost)
            pos["size"] -= size
            pos["cost"] -= size * avg_cost
            if pos["size"] < 0.0001:
                pos["size"] = 0.0
                pos["cost"] = 0.0
        positions[token_id] = pos
        return realized_pnl, avg_cost

    return None, None


# ---------------- Formatting ----------------

def format_trade(trade, realized_pnl=None, is_big=False):
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

    header = f"{emoji} <b>{action}</b>"
    if is_big:
        header = f"🚨 <b>معامله بزرگ!</b> {header}"
    lines = [header]

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

    if realized_pnl is not None:
        pnl_emoji = "📈" if realized_pnl >= 0 else "📉"
        sign = "+" if realized_pnl >= 0 else ""
        lines.append(f"{pnl_emoji} سود/زیان این پوزیشن: <b>{sign}${realized_pnl:,.0f}</b>")

    if timestamp:
        lines.append(f"🕒 {format_timestamp(timestamp)}")

    lines.append(f'🔗 <a href="{TRADER_LINK}">مشاهده پروفایل تریدر</a>')

    return "\n".join(lines)


def average_trade_size(trades_history, exclude_id=None):
    sizes = [
        t.get("size") for t in trades_history
        if isinstance(t.get("size"), (int, float)) and trade_id(t) != exclude_id
    ]
    if not sizes:
        return None
    return sum(sizes) / len(sizes)


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

    return new_last_id


# ---------------- State ----------------

def load_state():
    default = {"seen_ids": [], "trades": [], "last_update_id": None, "positions": {}}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                default.update(data)
            elif isinstance(data, list):
                default["seen_ids"] = data
        except Exception:
            pass
    if not isinstance(default.get("positions"), dict):
        default["positions"] = {}
    return default


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ---------------- Main ----------------

def main():
    state = load_state()
    seen_ids = set(state.get("seen_ids") or [])
    trades_history = state.get("trades") or []
    positions = state.get("positions") or {}
    is_first_run = len(seen_ids) == 0

    trades = fetch_trades()
    new_trades = [t for t in trades if trade_id(t) not in seen_ids]
    new_trades_chronological = list(reversed(new_trades))

    if is_first_run:
        for t in reversed(trades):
            update_positions_and_get_pnl(positions, t)
        send_telegram(
            f"🟢 <b>مانیتورینگ شروع شد</b>\n"
            f'👤 <a href="{TRADER_LINK}">{WALLET[:6]}...{WALLET[-4:]}</a>\n'
            f"{len(trades)} معامله اخیر پیدا شد و ذخیره شد.\n\n"
            f"از این به بعد فقط معاملات جدید بهت اطلاع داده میشه.",
            MAIN_KEYBOARD,
        )
    elif new_trades_chronological:
        for trade in new_trades_chronological:
            avg_size_before = average_trade_size(trades_history, exclude_id=trade_id(trade))
            is_big = (
                avg_size_before is not None
                and isinstance(trade.get("size"), (int, float))
                and trade["size"] > avg_size_before * BIG_TRADE_MULTIPLIER
            )
            realized_pnl, _ = update_positions_and_get_pnl(positions, trade)
            send_telegram(format_trade(trade, realized_pnl=realized_pnl, is_big=is_big))
        print(f"Sent {len(new_trades_chronological)} new trade notifications.")
    else:
        print("No new trades.")

    existing_ids_in_history = {trade_id(t) for t in trades_history}
    new_items = [t for t in trades if trade_id(t) not in existing_ids_in_history]
    trades_history = new_items + trades_history
    trades_history = trades_history[:100]
    seen_ids |= {trade_id(t) for t in trades}

    new_last_update_id = handle_commands(state.get("last_update_id"), trades_history)

    save_state({
        "seen_ids": list(seen_ids),
        "trades": trades_history,
        "last_update_id": new_last_update_id,
        "positions": positions,
    })


if __name__ == "__main__":
    main()
