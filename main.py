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

# agent_id 581 = Wallet 360 (60+ wallet performance, behavior, and risk metrics)
TRADER_STATS_AGENT_ID = 581


def fetch_stats():
    payload = {
        "agent_id": TRADER_STATS_AGENT_ID,
        "params": {
            "proxy_wallet": WALLET,
            "window_days": "3",
        },
        "pagination": {"limit": 100, "offset": 0},
        "formatter_config": {"format_type": "raw"},
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

    # اگه پاسخ داخل یه لیست (نتایج جستجو) اومده باشه، اولین آیتم رو برمی‌داریم
    if isinstance(new, dict) and "results" in new and isinstance(new["results"], list):
        new = new["results"][0] if new["results"] else {}
    if isinstance(old, dict) and "results" in old and isinstance(old["results"], list):
        old = old["results"][0] if old["results"] else {}

    if is_first_run:
        lines = [f"🟢 مانیتورینگ شروع شد\nWallet: {wallet_short}\n"]
        for key, value in new.items():
            lines.append(f"{key}: {value}")
        return "\n".join(lines)

    lines = [f"🔔 تغییر در آمار Wallet {wallet_short}"]
    changed = False
    all_keys = set(new.keys()) | set(old.keys())
    for key in sorted(all_keys):
        old_v = old.get(key)
        new_v = new.get(key)
        if old_v != new_v:
            changed = True
            lines.append(f"{key}: {old_v} → {new_v}")
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
