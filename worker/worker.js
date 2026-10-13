// Cloudflare Worker: bot tugmalarini darhol qabul qiladi va GitHub'dagi ishni shu zahoti ishga tushiradi.
// Sozlamalar (Worker → Settings → Variables): BOT_TOKEN, GH_TOKEN, HOOK_SECRET (secret sifatida),
// GH_REPO = "ahmadjanovahmadjon34/axmadjanovuz-autopost"; KV binding nomi: QUEUE.

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
  async fetch(req, env) {
    const url = new URL(req.url);

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
      await env.QUEUE.put(`u:${String(u.update_id).padStart(12, "0")}`, JSON.stringify(u), { expirationTtl: 259200 });
      if (u.callback_query || (u.message && u.message.text)) await dispatch(env);
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
