// Cloudflare Worker: bot tugmalarini darhol qabul qiladi va GitHub'dagi ishni shu zahoti ishga tushiradi.
// KV binding nomi: QUEUE. Sozlamalar BOT_TOKEN, GH_TOKEN, HOOK_SECRET, GH_REPO Worker o'zgaruvchisi
// sifatida yoki shu KV ichida kalit sifatida saqlanadi (o'zgaruvchi bo'lsa, u ustun).
const KEYS = ["BOT_TOKEN", "GH_TOKEN", "HOOK_SECRET", "GH_REPO"];

// Har bir kanal posti ostidagi izohga qo'yiladigan tugmalar (kanal username'i kichik harflarda).
const SOCIAL = {
  axmadjanovuz: [
    { text: "Instagram", url: "https://www.instagram.com/axmadjanov.uz/" },
    { text: "Telegram", url: "https://t.me/Axmadjanovuz" },
  ],
  nodavlattalim: [
    { text: "Telegram", url: "https://t.me/nodavlattalim" },
  ],
};

async function config(env) {
  const c = {};
  for (const k of KEYS) c[k] = env[k] || (await env.QUEUE.get(k)) || "";
  for (const k of KEYS) c[k] = c[k].trim();
  // Telegram va GitHub Actions parolning o'zini emas, sha256 xeshini yuboradi.
  if (c.HOOK_SECRET) {
    const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(c.HOOK_SECRET));
    c.HOOK_SECRET = [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
  }
  if (!c.GH_REPO) c.GH_REPO = "ahmadjanovahmadjon34/axmadjanovuz-autopost";
  c.QUEUE = env.QUEUE;
  return c;
}

async function tg(env, method, body) {
  return fetch(`https://api.telegram.org/bot${env.BOT_TOKEN}/${method}`, {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
  });
}

async function dispatch(env) {
  return fetch(`https://api.github.com/repos/${env.GH_REPO}/actions/workflows/post.yml/dispatches`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${env.GH_TOKEN}`, accept: "application/vnd.github+json",
      "user-agent": "axmadjanovuz-autopost-worker",
    },
    body: JSON.stringify({ ref: "main", inputs: { command: "run" } }),
  });
}

export default {
  async fetch(req, rawEnv) {
    const url = new URL(req.url);
    if (url.pathname !== "/tg" && url.pathname !== "/updates") return new Response("ok");
    const env = await config(rawEnv);
    if (!env.HOOK_SECRET) return new Response("not configured", { status: 503 });

    // Telegram webhook
    if (url.pathname === "/tg" && req.method === "POST") {
      if (req.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.HOOK_SECRET) {
        return new Response("forbidden", { status: 403 });
      }
      const u = await req.json();
      if (u.callback_query && u.callback_query.data !== "noop") {
        await tg(env, "answerCallbackQuery", {
          callback_query_id: u.callback_query.id, text: "⏳ Qabul qilindi, 1 daqiqada bajariladi",
        });
      }
      // Kanalda yangi post chiqdi: izohlarga darhol birinchi bo'lib ijtimoiy tarmoqlar tugmalarini qoldiramiz.
      const origin = ((u.message && u.message.is_automatic_forward && u.message.forward_origin &&
        u.message.forward_origin.chat && u.message.forward_origin.chat.username) || "").toLowerCase();
      const social = SOCIAL[origin];
      if (social) {
        await tg(env, "sendMessage", {
          chat_id: u.message.chat.id, text: "📢 Bizni barcha ijtimoiy tarmoqlarda kuzatib boring:",
          reply_parameters: { message_id: u.message.message_id },
          reply_markup: { inline_keyboard: [social] },
        });
        return new Response("ok");
      }
      await env.QUEUE.put(`u:${String(u.update_id).padStart(12, "0")}`, JSON.stringify(u), { expirationTtl: 259200 });
      if (u.callback_query || u.message) await dispatch(env);
      return new Response("ok");
    }

    // GitHub Actions navbatdagi bosishlarni shu yerdan oladi
    if (url.pathname === "/updates" && req.headers.get("x-hook-secret") === env.HOOK_SECRET) {
      const list = await env.QUEUE.list({ prefix: "u:" });
      const out = [];
      for (const k of list.keys) {
        const v = await env.QUEUE.get(k.name);
        if (v) out.push(JSON.parse(v));
        await env.QUEUE.delete(k.name);
      }
      return Response.json(out);
    }

    return new Response("ok");
  },
};
