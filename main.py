import os
import json
import requests

# ---- تنظیمات از Secrets گیت‌هاب خونده میشه ----
HEISENBERG_TOKEN = os.environ["HEISENBERG_TOKEN"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
WALLET = "0x688051ca7cd43270d8f26b48ecdc9beb2d23cf03"

STATE_FILE = "state.json"

API_URL = "https://narrative.agent.heisenberg.so/v2/traders/stats"


def fetch_stats():
    payload = {
        "wallet": WALLET,
        "metrics": ["pnl", "roi", "win_rate", "drawdown"],
        "timeframe": "90d",
    }
    headers = {
        "Authorization": f"Bearer {HEISENBERG_TOKEN}",
        "Content-Type": "application/json",
    }
    resp = requests.post(API_URL, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def load_previous_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text})


def format_message(new, old, is_first_run):
    wallet_short = WALLET[:6] + "..." + WALLET[-4:]
    if is_first_run:
        return (
            f"🟢 مانیتورینگ شروع شد\n"
            f"Wallet: {wallet_short}\n\n"
            f"PnL: {new.get('total_pnl')}\n"
            f"ROI: {new.get('roi')}\n"
            f"Win rate: {new.get('win_rate')}\n"
            f"Max drawdown: {new.get('max_drawdown')}\n"
            f"Trades: {new.get('total_trades')}\n"
            f"Active positions: {new.get('active_positions')}"
        )

    lines = [f"🔔 تغییر در آمار Wallet {wallet_short}"]
    fields = [
        ("total_pnl", "PnL"),
        ("roi", "ROI"),
        ("win_rate", "Win rate"),
        ("max_drawdown", "Max drawdown"),
        ("total_trades", "Trades"),
        ("active_positions", "Active positions"),
    ]
    changed = False
    for key, label in fields:
        old_v = old.get(key)
        new_v = new.get(key)
        if old_v != new_v:
            changed = True
            lines.append(f"{label}: {old_v} → {new_v}")
    if not changed:
        return None
    return "\n".join(lines)


def main():
    new_state = fetch_stats()
    old_state = load_previous_state()

    message = format_message(new_state, old_state, is_first_run=(old_state is None))
    if message:
        send_telegram(message)
        print("Notification sent:\n", message)
    else:
        print("No change detected, no notification sent.")

    save_state(new_state)


if __name__ == "__main__":
    main()
