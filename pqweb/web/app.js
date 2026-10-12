const $ = (s) => document.querySelector(s);
const views = ["list", "upload", "detail", "review", "rules", "scores"];
let timer = null;

function show(name) {
  views.forEach((v) => ($("#view-" + v).hidden = v !== name));
  const nav = ["rules", "scores"].includes(name) ? name : "list";
  document.querySelectorAll(".topnav button").forEach((b) => b.classList.toggle("on", b.dataset.go === nav));
  if (typeof openDrawer === "function" && name !== "review") openDrawer(false);
  if (timer && name !== "detail") { clearTimeout(timer); timer = null; }
}

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch (_) {}
    throw new Error(msg);
  }
  return res.json();
}

function text(el, v) { el.textContent = v; return el; }
function td(tr, v, cls) { const c = document.createElement("td"); text(c, v ?? ""); if (cls) c.className = cls; tr.appendChild(c); return c; }

async function loadConfig() {
  const c = await api("/api/config");
  text($("#crit"), `${c.criteria} · 판독 모델 ${c.model}`);
  $("#key-warn").hidden = c.gemini_ready;
  $("#btn-start").disabled = !c.gemini_ready;
}

async function loadList() {
  show("list");
  const items = await api("/api/evaluations");
  const tb = $("#list tbody");
  tb.innerHTML = "";
  $("#empty").hidden = items.length > 0;
  for (const it of items) {
    const r = it.status.결과 || {};
    const tr = document.createElement("tr");
    tr.className = "link";
    td(tr, it.meta.생성); td(tr, it.meta.성명); td(tr, it.meta.소속); td(tr, it.meta.참여형태 || "-");
    const stc = { 완료: "done", 오류: "err" }[it.status.단계] || "run";
    const st = document.createElement("td"); const pill = document.createElement("span");
    pill.className = "pill " + stc; pill.textContent = it.status.단계; st.append(pill); tr.append(st);
    td(tr, r.환산년수 != null ? r.환산년수.toFixed(2) + "년" : "", "r");
    td(tr, r.확인필요 != null ? r.확인필요 + "건" : "", "r");
    td(tr, "열기 ›", "muted");
    tr.onclick = () => openDetail(it.id);
    tb.appendChild(tr);
  }
}

async function openDetail(id) {
  show("detail");
  $("#result").hidden = true;
  $("#d-error").hidden = true;
  const poll = async () => {
    let d;
    try { d = await api(`/api/evaluations/${encodeURIComponent(id)}`); }
    catch (e) { text($("#d-error"), e.message).hidden = false; return; }
    const st = d.status;
    text($("#d-title"), `${d.meta.성명 || "(성명 없음)"} · ${d.meta.생성}`);
    const total = st.전체쪽 || 0, done = st.완료쪽 || 0;
    const stageText = { 대기: "대기 중", 쪽변환: "PDF를 쪽 이미지로 변환 중", 판독: `판독 중 ${done}/${total}쪽`,
      판정: "평가기준으로 판정 중", 완료: `완료 (${total}쪽)`, 오류: "오류" }[st.단계] || st.단계;
    text($("#d-stage"), stageText);
    $("#d-meter").style.width = (st.단계 === "완료" ? 100 : total ? (done / total) * 100 : 5) + "%";
    const failed = st.실패쪽 || [];
    $("#d-failed").hidden = failed.length === 0;
    text($("#d-failed"), "판독 실패 쪽: " + failed.map((p) => "p" + String(p).padStart(2, "0")).join(", ") + " — 엑셀에서 수동 확인 필요");
    const finished = st.단계 === "완료" || st.단계 === "오류";
    $("#retry-box").hidden = !(finished && failed.length > 0);
    $("#btn-retry").onclick = async () => {
      $("#btn-retry").disabled = true;
      try {
        await api(`/api/evaluations/${encodeURIComponent(id)}/retry`, { method: "POST" });
        openDetail(id);
      } catch (e) { text($("#d-error"), e.message).hidden = false; }
      finally { $("#btn-retry").disabled = false; }
    };
    if (st.단계 === "오류") { text($("#d-error"), "처리 중 오류: " + st.오류).hidden = false; return; }
    if (st.단계 === "완료") { renderResult(id, d); return; }
    timer = setTimeout(poll, 1500);
  };
  poll();
}

function renderResult(id, d) {
  const r = d.status.결과;
  text($("#r-sim"), `${r.건수.유사}건 · ${r.유사_인정일.toLocaleString()}일`);
  text($("#r-rel"), `${r.건수.관련}건 · ${r.관련_인정일.toLocaleString()}일`);
  text($("#r-no"), `${r.건수.불인정}건`);
  text($("#r-years"), `${r.환산일수.toLocaleString()}일 · ${r.환산년수.toFixed(2)}년`);
  text($("#r-flag"), `${r.확인필요}건`);
  const sb = $("#scores tbody"); sb.innerHTML = "";
  for (const [role, pts] of Object.entries(r.점수)) {
    const tr = document.createElement("tr");
    td(tr, role + (role === d.meta.참여형태 ? " (선택)" : "")); td(tr, pts.toFixed(2) + "점", "r");
    sb.appendChild(tr);
  }
  const cb = $("#check tbody"); cb.innerHTML = "";
  text($("#r-check"), !r.대조가능 ? "증명서 합계표를 찾지 못해 대조하지 못함" : r.판독정상 ? "모두 정상" : "불일치 있음");
  for (const c of r.대조 || []) {
    const tr = document.createElement("tr");
    td(tr, c.공사종류); td(tr, c.판독.toLocaleString(), "r"); td(tr, c.증명서.toLocaleString(), "r"); td(tr, c.행수, "r");
    td(tr, c.상태, c.상태 === "정상" ? "ok" : "bad");
    cb.appendChild(tr);
  }
  const ul = $("#r-errors"); ul.innerHTML = "";
  for (const e of r.형식오류 || []) { const li = document.createElement("li"); text(li, e); ul.appendChild(li); }
  $("#r-excel").href = `/api/evaluations/${encodeURIComponent(id)}/excel`;
  $("#r-excel-review").href = `/api/evaluations/${encodeURIComponent(id)}/excel?review=1`;
  $("#rejudge-msg").hidden = true;
  $("#btn-rejudge").onclick = async () => {
    if (!confirm("판독 결과는 그대로 두고, 지금 저장된 평가기준·점수로 판정과 엑셀을 다시 만듭니다. 계속할까요?")) return;
    $("#btn-rejudge").disabled = true;
    try {
      const before = r.환산년수;
      const res = (await api(`/api/evaluations/${encodeURIComponent(id)}/rejudge`, { method: "POST" })).결과;
      await openDetail(id);
      text($("#rejudge-msg"), `다시 판정했습니다 — 환산년수 ${before.toFixed(2)}년 → ${res.환산년수.toFixed(2)}년`).hidden = false;
    } catch (e) { text($("#d-error"), e.message).hidden = false; }
    finally { $("#btn-rejudge").disabled = false; }
  };
  $("#btn-review").onclick = () => openReview(id);
  $("#result").hidden = false;
}

$("#btn-new").onclick = () => { $("#form").reset(); $("#form-error").hidden = true; resetDrop(); show("upload"); };
const dropInput = document.querySelector(".drop input");
function resetDrop() { document.querySelector(".drop").classList.remove("has"); text(document.querySelector(".drop-t"), "경력증명서 PDF 선택"); }
dropInput.onchange = () => {
  const f = dropInput.files[0];
  document.querySelector(".drop").classList.toggle("has", !!f);
  text(document.querySelector(".drop-t"), f ? "✓ " + f.name : "경력증명서 PDF 선택");
};
$("#btn-cancel").onclick = loadList;
$("#btn-back").onclick = loadList;
$("#form").onsubmit = async (ev) => {
  ev.preventDefault();
  const fd = new FormData(ev.target);
  const err = $("#form-error");
  if (!fd.get("file") || !fd.get("file").name) { text(err, "PDF 파일을 선택하세요.").hidden = false; return; }
  $("#btn-start").disabled = true;
  try {
    const { id } = await api("/api/evaluations", { method: "POST", body: fd });
    openDetail(id);
  } catch (e) {
    text(err, e.message).hidden = false;
  } finally {
    $("#btn-start").disabled = false;
  }
};
$("#form").addEventListener("input", () => ($("#form-error").hidden = true));

loadConfig().then(loadList).catch((e) => alert("서버 연결 실패: " + e.message));
