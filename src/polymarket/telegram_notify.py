import os
import time
from dataclasses import dataclass

import requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8566238592:AAHFU4A5DgeQkU5hivcbNyAwuWcZDBlyomM")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "833255740")

def send_telegram(text: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
    except Exception:
        pass

@dataclass
class SignalStats:
    notify_every_signals: int = 10
    notify_every_seconds: int = 15*60
    started_at: float = time.time()
    total_signals: int = 0
    last_notify_at: float = 0.0

    def bump(self, extra_line: str | None = None) -> None:
        self.total_signals += 1
        now = time.time()
        should_send = (
            (self.total_signals % self.notify_every_signals) == 0
            or (now - self.last_notify_at) >= self.notify_every_seconds
        )
        if not should_send:
            return

        uptime_min = int((now - self.started_at) // 60)
        msg = [
            "📡 Polymarket Signals — Update",
            f"• Total signals: {self.total_signals}",
            f"• Uptime: {uptime_min} min",
        ]
        if extra_line:
            msg.append(f"• Last: {extra_line}")

        send_telegram("\n".join(msg))
        self.last_notify_at = now

