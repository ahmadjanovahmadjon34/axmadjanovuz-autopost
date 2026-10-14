# Claude routine: 2- va 3-agent (Pro obuna hisobidan)

Bu fayl har soatda ishga tushadigan Claude routine uchun ko'rsatma. Yangiliklarni yig'ish, botga
yuborish va tugmalarni GitHub Actions bajaradi; routine faqat **tahlil, post yozish va sifat nazorati**ni qiladi.

## Qadamlar

1. `pip install -q -r requirements.txt` va `python main.py export > /tmp/task.json`.
   Fayl: `new_items` (tahlil qilinmagan yangiliklar), `redo` (egasi "Qayta ishlash" bosgan qoralamalar),
   `recent_posts` (takrorlamaslik uchun), `signature`, `avg_posts_per_day`, `max_drafts`, `min_quality_score`.
2. Hech narsa bo'lmasa (`new_items` va `redo` bo'sh) — hech narsa commit qilmay to'xtang.
3. **Egasi yuborgan xabarlar (eng birinchi):** `source` qiymati `owner_source` ga teng bo'lgan yangiliklarni egasi o'zi botga
   yuborgan. Ularni tanlovsiz, `max_drafts` ga qo'shmasdan **albatta** post qiling (matni kam bo'lsa ham, bor
   faktlar asosida). Egasining xabaridagi faktlarni o'zgartirmang.
4. **2-agent, tahlil:** `new_items` ni to'liq o'qing. `agents/writer.py` dagi `TRIAGE` qoidalari bo'yicha
   post qilishga arziydiganlarini tanlang (bir voqea haqidagi manbalarni birlashtiring; ko'pi bilan `max_drafts` ta).
5. **2-agent, yozish:** har bir tanlangan yangilik uchun `agents/writer.py` dagi `WRITE` qoidalari va
   `style_examples.txt` uslubida post yozing: sarlavha <b>qalin</b>, muhim raqam/sanalar qalin (me'yorida),
   oxirida shaxsiy xulosa yoki kursiv izoh **yozilmaydi** (egasining talabi): post faktlar bilan tugaydi, keyin imzo. Yangilikda `media` bo'lsa (rasm/video), post 850 belgidan oshmasin —
   u media ostida izoh bo'lib chiqadi. Postga manba havolasini qo'ymang (manba egasiga alohida ko'rsatiladi).
   Manba matnidagi faktlardan tashqari hech narsa qo'shmang.
   Kerak bo'lsa havola orqali manbaning to'liq matnini o'qing.
6. **Qayta ishlash:** `redo` dagi har biri uchun `previous_draft` dan ancha yaxshiroq variant yozing
   (kuchliroq sarlavha, aniqroq faktlar, faktlar o'zgarmaydi).
7. **3-agent, sifat nazorati:** har bir postni `agents/reviewer.py` dagi `SYSTEM` mezonlari bo'yicha manba bilan
   solishtirib 10 ballik baho bering. `min_quality_score` dan past bo'lsa tuzating va qayta baholang
   (3 urinish). Telegram HTML faqat `<b> <a href>`; oxirida `signature` bo'lsin.
8. Natijani `inbox/<UTC vaqt, masalan 20261013T150000>.json` ga yozing:
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
9. `python -c "import json,sys; json.load(open(sys.argv[1]))" inbox/<fayl>.json` bilan tekshiring, so'ng
   faqat shu faylni commit qiling: `git add inbox && git commit -m "qoralamalar" && git pull --rebase && git push`.
   `data.db` ni o'zgartirmang.
10. Qoralama botga darhol yetib borishi uchun GitHub ishini ishga tushiring:
    `gh api -X POST repos/ahmadjanovahmadjon34/axmadjanovuz-autopost/actions/workflows/post.yml/dispatches -f ref=main -f 'inputs[command]=run'`

## Tezkor tekshiruv (har 15 daqiqada, :22 / :37 / :52)
Egasi "🔄 Qayta ishlash" bosgan yoki botga xabar yuborgan bo'lsa, soatlik tahlilni kutmasdan bajariladi.
`python main.py export` dan faqat `redo` va `source == owner_source` bo'lgan `new_items` olinadi. Ikkalasi ham
bo'sh bo'lsa hech narsa commit qilinmaydi. Bo'lsa — faqat shular uchun post yoziladi (qolgan yangiliklar
soatlik tahlilga qoladi, ularni `processed_ids` ga qo'shmang), inbox push qilinadi va workflow ishga tushiriladi.
Qayta ishlangan postga eski variant avtomatik `prev_draft` bo'lib saqlanadi (botda "↩️ Avvalgi variantga qaytish").
