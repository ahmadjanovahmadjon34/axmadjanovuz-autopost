"""axmadjanov.uz avtomatik post tizimi.

  python main.py run       # asosiy: har 15-20 daqiqada ishga tushiriladi (GitHub Actions/cron).
                           # Yangiliklarni yig'adi va vaqt/limit ruxsat bersa bitta post chiqaradi.
  python main.py collect   # faqat 1-agent
  python main.py post      # limitlarga qaramay hozir bitta post tayyorlash (sinov uchun)
"""
from datetime import datetime, timedelta
import os
import sys
from zoneinfo import ZoneInfo

import yaml

from agents.collector import collect
from agents.publisher import publish
from agents.reviewer import review
from agents.storage import Store, utcnow
from agents.writer import write_post


def load_config():
    with open("config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def posted_today(cfg, store):
    tz = ZoneInfo(cfg["timezone"])
    midnight = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    return store.posted_since(midnight)


def can_post_now(cfg, store):
    sch = cfg["schedule"]
    tz = ZoneInfo(cfg["timezone"])
    now = datetime.now(tz).strftime("%H:%M")
    start, end = sch["active_hours"]
    if not (start <= now <= end):
        return False, f"faol vaqt emas ({now})"
    today = posted_today(cfg, store)
    if len(today) >= sch["max_posts_per_day"]:
        return False, f"bugungi limit to'ldi ({len(today)})"
    if today:
        last = datetime.fromisoformat(today[-1])
        if utcnow() - last < timedelta(minutes=sch["min_gap_minutes"]):
            return False, "oxirgi postdan beri vaqt kam o'tdi"
    return True, ""


def make_post(cfg, store, attempts=3):
    candidates = store.candidates(cfg["schedule"]["max_age_hours"])
    if not candidates:
        print("Yangi yangilik yo'q.")
        return False
    count = len(posted_today(cfg, store))
    feedback = post = None
    item = None
    for _ in range(attempts):
        res = write_post(cfg, candidates, store.recent_posted(), count, feedback, post)
        idx = res.get("index", -1)
        if not isinstance(idx, int) or not 0 <= idx < len(candidates):
            print(f"[2-agent] Muhim yangilik topilmadi: {res.get('reason')}")
            return False
        if item is not None and candidates[idx]["id"] != item["id"]:
            store.set_status(item["id"], "rejected")
        item, post = candidates[idx], res["post"]
        print(f"[2-agent] Tanlandi: {item['url']} — {res.get('reason')}")
        qc = review(cfg, post, item)
        print(f"[3-agent] Baho {qc.get('score')}/10, e'tirozlar: {qc['issues']}")
        if qc["ok"]:
            post = qc.get("fixed_post") or post
            if publish(cfg, post, item.get("image"), item["url"]):
                store.set_status(item["id"], "posted")
                return True
            return False
        feedback = "\n".join(qc["issues"])
    store.set_status(item["id"], "rejected")
    print("[3-agent] Post sifatdan o'tmadi, chiqarilmadi.")
    return False


def run(cfg, store):
    collect(cfg, store)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY yo'q: faqat yangiliklar yig'ildi, post yozilmaydi.")
        return
    ok, why = can_post_now(cfg, store)
    if not ok:
        print(f"Hozir post chiqmaydi: {why}")
        return
    make_post(cfg, store)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    cfg, store = load_config(), Store()
    {"run": lambda: run(cfg, store),
     "collect": lambda: collect(cfg, store),
     "post": lambda: (collect(cfg, store), make_post(cfg, store))}[cmd]()
