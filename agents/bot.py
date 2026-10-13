"""4-agent: admin bot. Qoralamani egasiga tugmalar bilan ko'rsatadi, tasdiqlansa kanalga chiqaradi."""
import html
import json
import os

import httpx

MAX_TEXT = 4096


class Bot:
    def __init__(self, token=None):
        self.api = f"https://api.telegram.org/bot{token or os.environ['TELEGRAM_BOT_TOKEN']}"

    def call(self, method, **params):
        data = {k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in params.items() if v is not None}
        r = httpx.post(f"{self.api}/{method}", data=data, timeout=60).json()
        if not r.get("ok"):
            raise RuntimeError(f"{method}: {r}")
        return r["result"]

    def updates(self, offset):
        return self.call("getUpdates", offset=offset, timeout=0,
                         allowed_updates=["message", "callback_query"])

    @staticmethod
    def media_of(item):
        return json.loads(item.get("media") or "[]")

    @classmethod
    def keyboard(cls, item):
        rows = [[
            {"text": "🔄 Qayta ishlash", "callback_data": f"redo:{item['id']}"},
            {"text": "✅ Kanalga yuborish", "callback_data": f"send:{item['id']}"},
        ]]
        media = cls.media_of(item)
        if media:
            label = "🚫 Mediasiz chiqadi (qaytarish)" if item.get("media_off") else f"🖼 Media bilan chiqadi ({len(media)})"
            rows.append([{"text": label, "callback_data": f"media:{item['id']}"}])
        return {"inline_keyboard": rows}

    def set_keyboard(self, chat_id, msg_id, item):
        self.call("editMessageReplyMarkup", chat_id=chat_id, message_id=msg_id, reply_markup=self.keyboard(item))

    @staticmethod
    def draft_text(item, post, qc):
        footer = (f"\n\n— — —\n🧾 Manba: {html.escape(item['source'])} {html.escape(item['url'] or '')}"
                  f"\n🔎 Sifat: {qc.get('score', '?')}/10")
        issues = qc.get("issues") or []
        if issues:
            footer += "\n⚠️ " + html.escape("; ".join(issues))[:400]
        return post[:MAX_TEXT - len(footer)] + footer

    def send_draft(self, chat_id, item, post, qc):
        media = self.media_of(item)
        if media:
            try:  # avval media'ni ko'rsatamiz, qoralama matni tugmalar bilan uning ostida
                self.send_media(chat_id, media)
            except RuntimeError as e:
                qc = {**qc, "issues": [*qc.get("issues", []), f"Media yuklanmadi: {e}"[:200]]}
        text = self.draft_text(item, post, qc)
        try:
            msg = self.call("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
                            link_preview_options={"is_disabled": True}, reply_markup=self.keyboard(item))
        except RuntimeError as e:
            # HTML xato bo'lsa ham qoralama yo'qolmasin: oddiy matn sifatida ko'rsatamiz
            msg = self.call("sendMessage", chat_id=chat_id, text=f"⚠️ HTML xatosi: {e}\n\n{text}"[:MAX_TEXT],
                            link_preview_options={"is_disabled": True}, reply_markup=self.keyboard(item))
        return msg["message_id"]

    def edit_draft(self, chat_id, msg_id, item, post, qc):
        self.call("editMessageText", chat_id=chat_id, message_id=msg_id, text=self.draft_text(item, post, qc),
                  parse_mode="HTML", link_preview_options={"is_disabled": True},
                  reply_markup=self.keyboard(item))

    def mark(self, chat_id, msg_id, note):
        """Tugmalarni olib tashlab, holatni yozib qo'yadi."""
        self.call("editMessageReplyMarkup", chat_id=chat_id, message_id=msg_id,
                  reply_markup={"inline_keyboard": [[{"text": note, "callback_data": "noop"}]]})

    def answer(self, callback_id, text=None):
        try:
            self.call("answerCallbackQuery", callback_query_id=callback_id, text=text)
        except RuntimeError:
            pass  # eski tugma bosilgan bo'lsa Telegram rad etadi — muhim emas

    def say(self, chat_id, text):
        self.call("sendMessage", chat_id=chat_id, text=text)

    def send_media(self, chat_id, media, caption=None):
        """1 ta media — sendPhoto/sendVideo, bir nechta — albom. caption ≤ 1024 belgi."""
        cap = {"caption": caption, "parse_mode": "HTML"} if caption else {}
        if len(media) == 1:
            m = media[0]
            method, field = ("sendVideo", "video") if m["type"] == "video" else ("sendPhoto", "photo")
            return self.call(method, chat_id=chat_id, **{field: m["url"]}, **cap)
        group = [{"type": m["type"], "media": m["url"]} for m in media[:10]]
        if caption:
            group[0].update(caption=caption, parse_mode="HTML")
        return self.call("sendMediaGroup", chat_id=chat_id, media=group)

    def publish(self, channel, post, media=None):
        """Kanalga chiqarish. Media bo'lsa post uning izohi bo'ladi; post uzun bo'lsa media, keyin matn."""
        if media:
            try:
                if len(post) <= 1024:
                    return self.send_media(channel, media, caption=post)
                self.send_media(channel, media)
            except RuntimeError as e:
                print(f"Media yuborilmadi, faqat matn: {e}")
        return self.call("sendMessage", chat_id=channel, text=post, parse_mode="HTML",
                         link_preview_options={"is_disabled": True})
