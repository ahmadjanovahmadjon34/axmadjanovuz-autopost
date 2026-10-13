"""3-agent: postni sifat nazoratidan o'tkazadi."""
import re

from .llm import ask_json

SYSTEM = """Siz Telegram kanali uchun sifat nazoratchisiz. Postni manba bilan solishtirib tekshiring:
1. Faktlar manbaga to'liq mos (raqam, ism, sana, lavozim) — eng muhimi.
2. Yangilik kanal auditoriyasi (abituriyent, talaba, ota-ona, o'qituvchi) uchun muhimmi.
3. Imlo va grammatika (o'zbek lotin yozuvi, o' g' tutuq belgisi to'g'ri).
4. Uslub kanal namunalariga mos, sarlavha jalb qiluvchi, lekin "klikbeyt" emas.
5. Siyosiy betaraflik, haqoratli yoki tasdiqlanmagan da'volar yo'q.
6. Telegram HTML formati to'g'ri, manba havolasi bor.

Faqat JSON qaytaring:
{"score": <0-10>, "issues": ["..."], "fixed_post": "<faqat mayda imlo xatolari bo'lsa tuzatilgan matn, aks holda bo'sh>"}"""

ALLOWED_TAGS = {"b", "i", "u", "s", "a", "code", "pre", "blockquote", "tg-spoiler"}


def rule_check(post):
    issues = []
    if len(post) > 4000:
        issues.append(f"Juda uzun: {len(post)} belgi (Telegram limiti 4096)")
    if len(post) < 150:
        issues.append("Juda qisqa")
    for tag in re.findall(r"</?([a-zA-Z-]+)", post):
        if tag.lower() not in ALLOWED_TAGS:
            issues.append(f"Telegram qo'llamaydigan teg: <{tag}>")
    if "**" in post or "__" in post:
        issues.append("Markdown belgilar qolgan")
    return issues


def review(cfg, post, source_item):
    issues = rule_check(post)
    if cfg["signature"] not in post:
        issues.append(f"Oxirida {cfg['signature']} yo'q")
    user = (f"MANBA ({source_item['source']}, {source_item['url']}):\n"
            f"{source_item['title']}\n{source_item['text'][:4000]}\n\nPOST:\n{post}")
    res = ask_json(cfg["model"], SYSTEM, user)
    res["issues"] = issues + res.get("issues", [])
    if issues:
        res["score"] = min(res.get("score", 0), cfg["min_quality_score"] - 1)
    res["ok"] = res.get("score", 0) >= cfg["min_quality_score"]
    return res
