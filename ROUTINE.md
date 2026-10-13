# Claude routine: 2- va 3-agent (Pro obuna hisobidan)

Bu fayl har soatda ishga tushadigan Claude routine uchun ko'rsatma. Yangiliklarni yig'ish, botga
yuborish va tugmalarni GitHub Actions bajaradi; routine faqat **tahlil, post yozish va sifat nazorati**ni qiladi.

## Qadamlar

1. `pip install -q -r requirements.txt` va `python main.py export > /tmp/task.json`.
   Fayl: `new_items` (tahlil qilinmagan yangiliklar), `redo` (egasi "Qayta ishlash" bosgan qoralamalar),
   `recent_posts` (takrorlamaslik uchun), `signature`, `avg_posts_per_day`, `max_drafts`, `min_quality_score`.
2. Hech narsa bo'lmasa (`new_items` va `redo` bo'sh) — hech narsa commit qilmay to'xtang.
3. **2-agent, tahlil:** `new_items` ni to'liq o'qing. `agents/writer.py` dagi `TRIAGE` qoidalari bo'yicha
   post qilishga arziydiganlarini tanlang (bir voqea haqidagi manbalarni birlashtiring; ko'pi bilan `max_drafts` ta).
4. **2-agent, yozish:** har bir tanlangan yangilik uchun `agents/writer.py` dagi `WRITE` qoidalari va
   `style_examples.txt` uslubida post yozing: sarlavha <b>qalin</b>, muhim raqam/sanalar qalin (me'yorida),
   oxirgi izoh/eslatma <i>kursiv</i>. Yangilikda `media` bo'lsa (rasm/video), post 1000 belgidan oshmasin —
   u media ostida izoh bo'lib chiqadi. Manba matnidagi faktlardan tashqari hech narsa qo'shmang.
   Kerak bo'lsa havola orqali manbaning to'liq matnini o'qing.
5. **Qayta ishlash:** `redo` dagi har biri uchun `previous_draft` dan ancha yaxshiroq variant yozing
   (kuchliroq sarlavha, chuqurroq izoh, faktlar o'zgarmaydi).
6. **3-agent, sifat nazorati:** har bir postni `agents/reviewer.py` dagi `SYSTEM` mezonlari bo'yicha manba bilan
   solishtirib 10 ballik baho bering. `min_quality_score` dan past bo'lsa tuzating va qayta baholang
   (3 urinish). Telegram HTML faqat `<b> <i> <a href>`; oxirida `signature` bo'lsin.
7. Natijani `inbox/<UTC vaqt, masalan 20261013T150000>.json` ga yozing:
   ```json
   {
     "processed_ids": ["<new_items dagi BARCHA id lar, tanlanmaganlari ham>"],
     "drafts": [
       {"id": "<asosiy yangilik id>", "related": ["<birlashtirilgan id lar>"],
        "post": "<Telegram HTML post>", "qc": {"score": 9, "issues": []}, "redo": false}
     ]
   }
   ```
   `redo` qoralamalari uchun `"redo": true` va o'sha `id`.
8. `python -c "import json,sys; json.load(open(sys.argv[1]))" inbox/<fayl>.json` bilan tekshiring, so'ng
   faqat shu faylni commit qiling: `git add inbox && git commit -m "qoralamalar" && git pull --rebase && git push`.
   `data.db` ni o'zgartirmang.
