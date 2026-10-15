"""2-agent: barcha yangi yangiliklarni tahlil qiladi, muhimlarini tanlaydi va kanal uslubida post yozadi."""
from pathlib import Path

from .llm import ask_json

AUDIENCE = """@Axmadjanovuz Telegram kanali auditoriyasi: abituriyentlar, talabalar, ota-onalar, o'qituvchilar.
Mavzular: {topics} (asosan ta'lim, qabul, OTM, nodavlat OTMlar, grant/kontrakt, imtiyozlar, ijtimoiy masalalar)."""

TRIAGE = AUDIENCE + """

Vazifa: quyidagi barcha yangi yangiliklarni tahlil qiling va kanal uchun post qilishga arziydiganlarini tanlang.
- Bir xil voqea haqida bir nechta manba bo'lsa, bittasini asosiy qiling, qolganlarini "related" ga qo'shing.
- Kalit so'z bo'lmasa ham muhim ta'lim/ijtimoiy yangilik tanlanishi mumkin.
- Sport, shou-biznes, kriminal, reklama, obunaga chaqiruv, tabriklar va auditoriyaga aloqasizlarini tanlamang.
- Oxirgi chiqqan/tayyorlangan postlarni takrorlamang.
- Kanalda kuniga o'rtacha {avg} ta post chiqadi; bu qat'iy cheklov emas, muhim yangilik ko'p bo'lsa ko'proq
  tanlang, bo'lmasa kamroq. Lekin bitta tahlilda {cap} tadan ko'p tanlamang, eng muhimlarini oling.

Faqat JSON: {{"selected": [{{"index": 3, "related": [7, 12], "reason": "..."}}]}}"""

WRITE = AUDIENCE + """

Vazifa: berilgan yangilikdan kanal uslubida o'zbek tilida (lotin yozuvida) post yozing.

Uslub qoidalari (namunalarga qarang):
- Birinchi qator — sarlavha: qisqa, e'tiborni tortuvchi, butunlay <b>qalin</b>. Sarlavha boshida doim
  ⚡️ yoki ❗️ emojisi turadi; boshqa emoji faqat juda zarur holatda.
- Matn ichidagi eng muhim qismlar (raqamlar, sanalar, muddatlar, summalar) <b>qalin</b>,
  lekin me'yorida: bir postda 3–6 joydan oshmasin.
- Oxirida shaxsiy fikr, xulosa yoki kursiv (<i>) izoh YOZILMAYDI: post faktlar bilan tugaydi, keyin imzo.
- Emojilar o'rinli va kam: ❓ ✅ ❗️ ➡️ ➖ 1️⃣ 2️⃣.
- Muddat, talab yoki kim uchun ekani kabi amaliy ma'lumot faktlar ichida aniq berilsin.
- Postda manba havolasini (boshqa kanal yoki sayt linkini) QO'YMANG — manba kanal egasiga alohida
  ko'rsatiladi. Rasmiy idora nomini aytish mumkin ("Bilimni baholash agentligi ma'lumotiga ko'ra").
  Faqat o'quvchiga amaliy kerak bo'lgan rasmiy sayt manzili (my.gov.uz kabi) yozilishi mumkin.
- Oxirida bo'sh qatordan keyin "{signature}", kerak bo'lsa hashtag (#Qabul2026 kabi).
- Faqat manbada bor faktlarni yozing, raqam, sana, ismlarni o'zgartirmang, hech narsa o'ylab topmang.
- Telegram HTML: faqat <b>, <i>, <a href="...">. Markdown (** yoki __) ishlatmang. & < > belgilarini
  matnda &amp; &lt; &gt; deb yozing.
- 300–1500 belgi. Yangilikda rasm/video bo'lsa ("Media: bor"), post 850 belgidan oshmasin,
  chunki u media ostiga izoh sifatida chiqadi.
- Manbani so'zma-so'z ko'chirmang, o'z uslubingizda qayta yozing.

Kanal uslubidan namunalar:
{examples}

Faqat JSON: {{"post": "<post>"}}"""


def load_examples(path):
    p = Path(path)
    if not p.exists():
        return "(namuna yo'q)"
    lines = [l for l in p.read_text(encoding="utf-8").splitlines() if not l.startswith("#")]
    return "\n".join(lines).strip() or "(namuna yo'q)"


def _fmt(i, c, limit):
    media = "bor" if c.get("media") and c["media"] != "[]" else "yo'q"
    return (f"[{i}] {c['source']} | {c['url']} | {c['published'][:16]} | Media: {media}\n"
            f"{c['title']}\n{c['text'][:limit]}")


def select_news(cfg, items, recent):
    """Barcha yangi yangiliklarni bo'laklab tahlil qiladi. Qaytaradi: [(asosiy, [bog'liqlar], sabab)]."""
    out = []
    cap = cfg["review"]["max_drafts_per_run"]
    system = TRIAGE.format(topics=", ".join(cfg["topics"]), avg=cfg["review"]["avg_posts_per_day"], cap=cap)
    for start in range(0, len(items), 40):
        chunk = items[start:start + 40]
        user = "Yangiliklar:\n\n" + "\n\n".join(_fmt(i, c, 600) for i, c in enumerate(chunk))
        if recent:
            user += "\n\nOxirgi chiqqan/tayyorlangan postlar:\n- " + "\n- ".join(recent)
        res = ask_json(cfg["model"], system, user, max_tokens=2000)
        for s in res.get("selected", []):
            i = s.get("index")
            if isinstance(i, int) and 0 <= i < len(chunk):
                rel = [chunk[j] for j in s.get("related", []) if isinstance(j, int) and 0 <= j < len(chunk) and j != i]
                out.append((chunk[i], rel, s.get("reason", "")))
    return out[:cap]


# "🔄 Qayta ishlash" ichidagi tanlovlar (redo_mode)
REDO_TASKS = {
    "improve": ("Kanal egasi buni qayta ishlashni so'radi. Ancha yaxshiroq variant yozing: sarlavhani kuchliroq,"
                " faktlarni aniqroq va o'quvchi uchun foydaliroq joylashtiring, faktlarni saqlang."),
    "formal": ("Kanal egasi postni rasmiyroq qilishni so'radi. Rasmiy-ishchan uslubda qayta yozing: so'zlashuv"
               " iboralari, undovlar va ortiqcha emojisiz, aniq va vazmin jumlalar bilan. Faktlarni saqlang."),
    "no_emoji": ("Kanal egasi postni emojisiz qilishni so'radi. Matn va faktlarni saqlab, sarlavha va matndagi"
                 " barcha emojilarni olib tashlang (ro'yxat belgisi kerak bo'lsa \"—\" ishlating)."
                 " Faqat oxiridagi imzo o'zgarmaydi."),
}


# 6-agent: faqat qayta ishlash ("🔄 Qayta ishlash" tugmasi). Avvalgi variantning kamchiliklarini aniqlab,
# REDO_TASKS dagi tanlov bo'yicha qayta yozadi.
REDO_AGENT = ("6-agent (qayta ishlash): avval oldingi variantning kamchiliklarini aniqlang (zaif sarlavha, ortiqcha"
              " so'z, yashirin qolgan muhim fakt, noto'g'ri tartib), keyin ularni tuzatib, egasi tanlagan usulda yozing.")


def write_post(cfg, item, related=(), feedback=None, previous=None, improve=False):
    system = WRITE.format(topics=", ".join(cfg["topics"]), signature=cfg["signature"],
                          examples=load_examples(cfg["style_examples_file"]))
    user = "Asosiy manba:\n" + _fmt(0, item, 4000)
    if related:
        user += "\n\nShu voqea haqida boshqa manbalar:\n" + "\n\n".join(_fmt(i + 1, r, 1500) for i, r in enumerate(related))
    if previous and improve:
        user += (f"\n\nOldingi variant:\n{previous}\n\n" + REDO_AGENT + "\n"
                 + REDO_TASKS.get(improve, REDO_TASKS["improve"]))
    if feedback:
        user += f"\n\nOldingi variant:\n{previous}\n\nSifat nazoratchisi e'tirozlari, tuzatib qayta yozing:\n{feedback}"
    return ask_json(cfg["model"], system, user, max_tokens=3000).get("post", "")
