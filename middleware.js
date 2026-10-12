// 설명자료 페이지 비밀번호 화면 (Vercel Routing Middleware).
// 비밀번호 원문은 어디에도 두지 않는다. Vercel 환경변수 PAGE_PASSWORD_SHA256 에
// 비밀번호의 SHA-256(hex)만 넣는다. 맞히면 7일짜리 쿠키를 준다.

export const config = { matcher: "/((?!_vercel).*)" };

const COOKIE = "pq_auth";
const LOGIN = "/__login";
const enc = new TextEncoder();

const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
const sha256 = async (s) => hex(await crypto.subtle.digest("SHA-256", enc.encode(s)));

async function tokenFor(hash) {
  const key = await crypto.subtle.importKey("raw", enc.encode(hash), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return hex(await crypto.subtle.sign("HMAC", key, enc.encode("pq-explainer-ok")));
}

function same(a, b) {
  if (a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

function cookieOf(req, name) {
  for (const part of (req.headers.get("cookie") || "").split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (k === name) return v.join("=");
  }
  return "";
}

function page(message, status) {
  const html = `<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>PQ 경력평가 웹 — 비밀번호</title>
<style>
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#F7F5EF;color:#1A1D21;font-family:'Malgun Gothic',sans-serif}
form{width:min(340px,calc(100vw - 32px));display:flex;flex-direction:column;gap:12px;padding:28px;background:#fff;border:1px solid #1A1D21}
h1{margin:0;font-size:20px} p{margin:0;font-size:14px;color:#3D434B}
label{font-size:13px;font-weight:600} input{font:inherit;font-size:16px;padding:10px;border:1px solid #8A8F96}
button{font:inherit;font-size:16px;font-weight:600;padding:11px;border:0;background:#1A1D21;color:#F7F5EF;cursor:pointer}
.err{color:#B42318;font-weight:600}
</style></head><body>
<form method="post" action="${LOGIN}">
<h1>PQ 경력평가 웹 설명자료</h1>
<p>비밀번호를 입력하세요.</p>
${message ? `<p class="err">${message}</p>` : ""}
<label for="pw">비밀번호</label>
<input id="pw" name="password" type="password" autocomplete="current-password" autofocus required>
<button type="submit">들어가기</button>
</form></body></html>`;
  return new Response(html, { status, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } });
}

export default async function middleware(req) {
  const hash = (process.env.PAGE_PASSWORD_SHA256 || "").trim().toLowerCase();
  if (!/^[0-9a-f]{64}$/.test(hash)) return page("비밀번호가 아직 설정되지 않았습니다.", 503);
  const token = await tokenFor(hash);
  const url = new URL(req.url);

  if (url.pathname === LOGIN) {
    if (req.method !== "POST") return page("", 200);
    const form = await req.formData();
    const pw = String(form.get("password") || "").normalize("NFC");
    if (!same(await sha256(pw), hash)) return page("비밀번호가 맞지 않습니다.", 401);
    return new Response(null, {
      status: 303,
      headers: {
        location: "/",
        "set-cookie": `${COOKIE}=${token}; Path=/; Max-Age=604800; HttpOnly; Secure; SameSite=Lax`,
      },
    });
  }

  if (same(cookieOf(req, COOKIE), token)) return; // 통과: 정적 페이지로
  return page("", 401);
}
