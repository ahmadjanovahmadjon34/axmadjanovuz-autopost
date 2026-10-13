"""4-agent: tayyor postni admin bot orqali chiqaradi.

PUBLISH_MODE muhit o'zgaruvchisi:
  live    — kanalga (config.yaml dagi channel)
  preview — faqat PREVIEW_CHAT_ID ga (sizning shaxsiy chatingiz), kanalga emas
  (bo'sh) — hech qayerga yubormaydi, out/ papkaga yozadi
"""
import json
import os
from datetime import datetime
from pathlib import Path

import httpx


def _send(token, chat_id, post, image):
    api = f"https://api.telegram.org/bot{token}"
    base = {"chat_id": chat_id, "parse_mode": "HTML"}
    if image and len(post) <= 1024:
        r = httpx.post(f"{api}/sendPhoto", data={**base, "photo": image, "caption": post}, timeout=30)
        if r.json().get("ok"):
            return r.json()
    r = httpx.post(f"{api}/sendMessage", timeout=30, data={
        **base, "text": post, "link_preview_options": json.dumps({"is_disabled": True})})
    return r.json()


def publish(cfg, post, image=None, source_url=None, log=print):
    mode = os.environ.get("PUBLISH_MODE", "").strip().lower()
    if mode not in ("live", "preview"):
        out = Path("out")
        out.mkdir(exist_ok=True)
        f = out / f"{datetime.now():%Y%m%d_%H%M%S}.html"
        f.write_text(f"{post}\n\n[manba: {source_url}] [rasm: {image}]", encoding="utf-8")
        log(f"[4-agent] Hech qayerga yuborilmadi, {f} ga yozildi")
        return True
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    if mode == "preview":
        chat = os.environ["PREVIEW_CHAT_ID"]
        post = f"🧪 SINOV (kanalga chiqmadi)\nManba: {source_url}\n\n{post}"
    else:
        chat = cfg["channel"]
    res = _send(token, chat, post, image)
    log(f"[4-agent] {mode}: {'yuborildi' if res.get('ok') else res}")
    return bool(res.get("ok"))
