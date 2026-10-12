// 평가위원 평가 화면 — 엑셀 평가시트 A~O열을 그대로 보여주고, 오른쪽에서 평가위원이 판단한다.
// 한 건씩 또는 체크박스로 여러 건을 한 번에 입력할 수 있고, 입력은 자동 저장된다.
const RV = { id: null, rows: [], review: { 평가위원: "", rows: {} }, 배점: {}, 연환산: 365,
  timer: null, filter: "all", sel: new Set(), lastIdx: null, view: loadView() };
function loadView() { try { return localStorage.getItem("pq-view") || "card"; } catch (_) { return "card"; } }
function saveView(v) { try { localStorage.setItem("pq-view", v); } catch (_) {} }
// 인정율은 평가기준(점수 편집)에서 온다
let RATE = { 유사: { hi: 1, lo: 0.5 }, 관련: { hi: 0.6, lo: 0.3 } };
const rateOptions = () => [...new Set([RATE.유사.hi, RATE.유사.lo, RATE.관련.hi, RATE.관련.lo])].sort((a, b) => b - a);
const ROLES = ["사업책임", "분야책임", "분야참여"];

function band(years, role) {
  for (const [th, pts] of RV.배점[role]) if (years >= th) return pts;
  return RV.배점[role][RV.배점[role].length - 1][1];
}
const pct = (r) => (r == null ? "" : Math.round(r * 100) + "%");
const fmt1 = (n) => (Math.round(n * 10) / 10).toLocaleString();
const enc = () => encodeURIComponent(RV.id);
function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null) continue;
    if (k === "class") e.className = v; else if (k === "text") e.textContent = v; else e.setAttribute(k, v);
  }
  kids.forEach((k) => k != null && e.append(k));
  return e;
}
const entry = (key) => RV.review.rows[key] || { 인정여부: "", 인정율: null, 사유: "" };
const autoRate = (r, kind) => (r.ai.분야 === "성능평가·진단" ? RATE[kind].hi : RATE[kind].lo);

async function openReview(id) {
  RV.id = id;
  RV.sel.clear();
  show("review");
  const d = await api(`/api/evaluations/${encodeURIComponent(id)}/rows`);
  Object.assign(RV, { rows: d.rows, review: d.review, 배점: d.배점, 연환산: d.일수_연환산 });
  RATE = { 유사: { hi: d.인정율.유사.진단성능, lo: d.인정율.유사.점검 }, 관련: { hi: d.인정율.관련.진단성능, lo: d.인정율.관련.점검 } };
  text($("#rv-rate-note"), `유사: 진단·성능평가 ${pct(RATE.유사.hi)}, 점검 ${pct(RATE.유사.lo)} / 관련: ${pct(RATE.관련.hi)}, ${pct(RATE.관련.lo)} · 일→년 ${d.일수_연환산}일 · 이적 보정 미적용`);
  const bk = $("#bk-rate"); bk.innerHTML = "";
  bk.append(el("option", { value: "auto", text: "인정율: 자동(사업명 판정)" }));
  rateOptions().forEach((v) => bk.append(el("option", { value: String(v), text: pct(v) })));
  text($("#rv-title"), `${d.일반.성명 || "(성명 없음)"} — ${d.rows.length}건`);
  $("#rv-name").value = RV.review.평가위원 || "";
  $("#rv-excel").href = `/api/evaluations/${enc()}/excel?review=1`;
  text($("#rv-saved"), "");
  renderGeneral(d.일반);
  renderNotes(d.메모);
  renderRows();
  refresh();
}

function renderGeneral(g) {
  const dl = $("#rv-general");
  dl.innerHTML = "";
  const items = [["참여형태", g.참여형태 || "미지정 (3개 병기)"], ["성명", g.성명], ["소속", g.소속 || "-"],
    ["등급", g.등급 || "-"], ["현 근무처", g.현근무처], ["판독", g.판독]];
  for (const [k, v] of items) {
    dl.append(el("dt", { text: k }), el("dd", { text: v, class: k === "판독" ? (g.판독정상 ? "good" : "warn") : null }));
  }
}

function renderNotes(lines) {
  const box = $("#rv-notes");
  box.innerHTML = "";
  for (const t of lines) box.append(el("p", { text: t, class: t.startsWith("[") ? "h" : null }));
}

// 평가위원 입력 컨트롤 (카드·표 공용)
function makeInputs(r) {
  const chk = el("input", { type: "checkbox", "aria-label": "선택" });
  const sel = el("select", { "aria-label": "평가위원 인정여부" });
  ["", "유사", "관련", "불인정"].forEach((o) => sel.append(el("option", { value: o, text: o || "인정여부 —" })));
  const rate = el("select", { "aria-label": "평가위원 인정율" });
  rate.append(el("option", { value: "", text: "인정율 —" }));
  rateOptions().forEach((v) => rate.append(el("option", { value: String(v), text: pct(v) })));
  const reason = el("input", { class: "reason", "aria-label": "판단사유", placeholder: "판단사유 (AI와 다르면)" });
  // 체크된 행에서 값을 바꾸면 체크된 행 전체에 같이 적용한다.
  sel.onchange = () => applyEdit(r, (row, cur) => {
    cur.인정여부 = sel.value;
    if (!sel.value || sel.value === "불인정") cur.인정율 = null;
    else if (cur.인정율 == null || !Object.values(RATE[sel.value]).includes(cur.인정율)) cur.인정율 = autoRate(row, sel.value);
  });
  rate.onchange = () => applyEdit(r, (row, cur) => { cur.인정율 = rate.value === "" ? null : Number(rate.value); });
  reason.oninput = () => applyEdit(r, (row, cur) => { cur.사유 = reason.value; }, false);
  [chk, sel, rate, reason].forEach((x) => x.addEventListener("click", (e) => e.stopPropagation()));
  return { chk, sel, rate, reason };
}

const container = () => (RV.view === "table" ? $("#rv-table tbody") : $("#rv-cards"));
const rowEls = () => [...container().querySelectorAll("[data-key]")];

function renderRows() {
  const card = RV.view !== "table";
  $("#rv-cards").hidden = !card;
  $("#rv-cards-foot").hidden = !card;
  $("#rv-table-wrap").hidden = card;
  $("#rv-selall").hidden = !card;
  document.querySelectorAll("#rv-view button").forEach((b) => b.classList.toggle("on", b.dataset.v === RV.view));
  $("#rv-table tbody").innerHTML = "";
  $("#rv-cards").innerHTML = "";
  RV.rows.forEach((r, idx) => {
    const ui = makeInputs(r);
    ui.chk.onclick = (e) => { e.stopPropagation(); toggleSel(idx, ui.chk.checked, e.shiftKey); };
    const node = card ? cardNode(r, idx, ui) : tableRow(r, idx, ui);
    node._ui = ui;
    node.onclick = () => showPage(r, node);
    container().append(node);
    paintRow(node, r);
  });
}

// 카드용 짧은 근거: 쪽 표시와 괄호 속 조항 원문 인용을 뺀다(전문은 마우스를 올리면 보임).
const shortWhy = (t) => t.replace(/^\[p\d+\]\s*/, "").replace(/\s*\((?:세부|가-2|일반)[^()]*(?:\([^()]*\)[^()]*)*\)/g, "").trim();

function cardNode(r, idx, ui) {
  const ai = r.ai, flagged = ai.확인필요.length > 0;
  const pg = "p" + String(r.쪽).padStart(2, "0");
  const node = el("article", { class: "ccard k-" + ai.인정여부 + (flagged ? " flagged" : ""), "data-key": r.key, "data-i": idx });
  const left = el("div", { class: "cc-when" },
    el("div", { class: "d", text: r.시작일 }), el("div", { class: "d2", text: "~ " + r.종료일 }),
    el("div", { class: "days", text: r.인정일.toLocaleString() + "일" }), el("div", { class: "pg", text: pg + " ▸" }));
  const meta = el("div", { class: "cc-meta" });
  [r.발주자, r.공사종류, [r.직무분야, r.전문분야].filter(Boolean).join(" · "), r.담당업무 && "담당 " + r.담당업무]
    .filter(Boolean).forEach((t) => meta.append(el("span", { text: t })));
  const strip = el("div", { class: "cc-ai" },
    el("span", { class: "cc-ai-lbl", text: "AI 근거" }),
    el("span", { class: "cc-why", text: shortWhy(ai.근거), title: ai.근거 }));
  // AI 판정을 오른쪽에 크게
  const axis = (n, label, value, why, ok) => el("div", { class: "ax" + (ok ? " ok" : " no") },
    el("span", { class: "ax-n", text: n }), el("span", { class: "ax-l", text: label }),
    el("b", { text: value || "-" }), why ? el("span", { class: "ax-w", text: why }) : null);
  const verdict = el("div", { class: "cc-verdict v-" + ai.인정여부 },
    el("div", { class: "vtop" }, el("span", { class: "vl", text: "AI 판정" }), el("span", { class: "vk", text: ai.인정여부 }),
      ai.인정율 != null ? el("span", { class: "vr", text: pct(ai.인정율) }) : null,
      ai.인정율 != null ? el("span", { class: "vd", text: "환산 " + fmt1(r.인정일 * ai.인정율) + "일" }) : null),
    el("div", { class: "axes" },
      axis("①", "해당분야", ai.해당분야, ai.해당분야근거, ai.해당분야 && !["아님", "확인 불가"].includes(ai.해당분야)),
      axis("②", "용역유형", ai.용역유형, ai.용역유형근거, ai.용역유형 && ai.용역유형 !== "해당 없음"),
      axis("③", "도로유형", ai.도로유형, ai.도로유형근거, true)),
    flagged ? el("div", { class: "vf", text: "▲ 확인필요 " + ai.확인필요.length }) : null);
  const flags = flagged ? el("ul", { class: "cc-flags" }, ...ai.확인필요.map((f) => el("li", { text: f }))) : null;
  const main = el("div", { class: "cc-main" },
    el("div", { class: "cc-name", text: r.사업명 }), meta,
    r.공사개요 ? el("div", { class: "cc-sum", text: r.공사개요 }) : null, strip, flags);
  ui.days = el("span", { class: "cc-rv-days" });
  const rv = el("div", { class: "cc-rv" },
    el("div", { class: "cc-rv-h", text: "평가위원 판단" }),
    el("div", { class: "row2" }, ui.sel, ui.rate), ui.reason, ui.days);
  const chkCell = el("div", { class: "cc-chk", title: "선택 (Shift+클릭: 범위 선택)" }, ui.chk);
  chkCell.onclick = (e) => { e.stopPropagation(); if (e.target !== ui.chk) { ui.chk.checked = !ui.chk.checked; toggleSel(idx, ui.chk.checked, e.shiftKey); } };
  node.append(chkCell, el("div", { class: "cc-left" }, left, main, verdict), rv);
  return node;
}

function chkTd(ui, idx) {
  const td = el("td", { class: "c-chk", title: "선택 (Shift+클릭: 범위 선택)" }, ui.chk);
  td.onclick = (e) => { e.stopPropagation(); if (e.target !== ui.chk) { ui.chk.checked = !ui.chk.checked; toggleSel(idx, ui.chk.checked, e.shiftKey); } };
  return td;
}

function tableRow(r, idx, ui) {
  const ai = r.ai, flagged = ai.확인필요.length > 0;
  const tr = el("tr", { "data-key": r.key, "data-i": idx, class: "k-" + ai.인정여부 });
  const why = el("td", { class: "why" + (flagged ? " flag" : "") }, ai.근거);
  ai.확인필요.forEach((f) => why.append(el("span", { class: "fl", text: "▲ 확인필요 · " + f })));
  tr.append(
    chkTd(ui, idx),
    el("td", { class: "c-pg", text: "p" + String(r.쪽).padStart(2, "0") }),
    el("td", { class: "nowrap c-area", text: ai.용역유형 || "-" }),
    el("td", { class: "name c-name", text: r.사업명 }),
    el("td", { class: "sum", text: r.공사개요 }),
    el("td", { class: "nowrap", text: r.시작일 }), el("td", { class: "nowrap", text: r.종료일 }),
    el("td", { class: "r", text: r.인정일.toLocaleString() }),
    el("td", { class: "c-org", text: r.발주자 }), el("td", { class: "c-kind", text: r.공사종류 }),
    el("td", { class: "nowrap", text: r.직무분야 }), el("td", { class: "c-spec", text: r.전문분야 }), el("td", { class: "c-job", text: r.담당업무 }),
    el("td", { class: "ai-c nowrap" }, el("span", { class: "badge b-" + ai.인정여부, text: ai.인정여부 })),
    el("td", { class: "ai-c r" + (flagged ? " flag" : ""), text: pct(ai.인정율) }),
    el("td", { class: "ai-c r", text: ai.인정율 != null ? fmt1(r.인정일 * ai.인정율) : "" }),
    why,
  );
  ui.days = el("td", { class: "rv-c r" });
  tr.append(el("td", { class: "rv-c" }, ui.sel), el("td", { class: "rv-c" }, ui.rate), ui.days, el("td", { class: "rv-c" }, ui.reason));
  return tr;
}

function paintRow(tr, r) {
  const v = entry(r.key), ui = tr._ui;
  ui.sel.value = v.인정여부 || "";
  ui.rate.value = v.인정율 == null ? "" : String(v.인정율);
  if (document.activeElement !== ui.reason) ui.reason.value = v.사유 || "";
  const d = v.인정여부 && v.인정율 != null && v.인정여부 !== "불인정" ? fmt1(r.인정일 * v.인정율) : "";
  ui.days.textContent = RV.view === "table" ? d : (d ? "환산 " + d + "일" : "");
  ui.chk.checked = RV.sel.has(r.key);
  tr.classList.toggle("sel", RV.sel.has(r.key));
}

function applyEdit(r, change, repaintSelf = true) {
  const targets = RV.sel.has(r.key) && RV.sel.size > 1 ? RV.rows.filter((x) => RV.sel.has(x.key)) : [r];
  for (const row of targets) {
    const cur = { ...entry(row.key) };
    change(row, cur);
    const empty = !cur.인정여부 && cur.인정율 == null && !cur.사유;
    if (empty) delete RV.review.rows[row.key]; else RV.review.rows[row.key] = cur;
    const tr = rowEl(row.key);
    if (tr && (row !== r || repaintSelf)) paintRow(tr, row);
  }
  refresh();
  scheduleSave();
}

function put(key, cur, repaint = true) {
  const empty = !cur.인정여부 && cur.인정율 == null && !cur.사유;
  if (empty) delete RV.review.rows[key]; else RV.review.rows[key] = cur;
  if (repaint) {
    const tr = rowEl(key);
    if (tr) paintRow(tr, RV.rows[tr.dataset.i]);
  }
  refresh();
  scheduleSave();
}
const rowEl = (key) => container().querySelector(`[data-key="${key}"]`);

function scheduleSave() {
  text($("#rv-saved"), "저장 중…");
  clearTimeout(RV.timer);
  RV.timer = setTimeout(async () => {
    try {
      await api(`/api/evaluations/${enc()}/review`, {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(RV.review),
      });
      text($("#rv-saved"), "✓ 저장됨 " + new Date().toLocaleTimeString().replace(/^오[전후] /, ""));
    } catch (e) { text($("#rv-saved"), "저장 실패: " + e.message); }
  }, 500);
}

// ── 합계·점수 ──
function totals(pick) {
  const t = { 유사: [0, 0], 관련: [0, 0] };
  for (const r of RV.rows) {
    const { 인정여부, 인정율 } = pick(r);
    if (t[인정여부] && 인정율 != null) { t[인정여부][0] += r.인정일; t[인정여부][1] += r.인정일 * 인정율; }
  }
  const days = t.유사[1] + t.관련[1], years = days / RV.연환산;
  return { t, raw: t.유사[0] + t.관련[0], days, years, pts: ROLES.map((role) => band(years, role)) };
}

function renderSummary(ai, rv) {
  const tb = $("#rv-summary tbody");
  tb.innerHTML = "";
  const line = (label, s, cls, other) => {
    if (other && !Object.keys(RV.review.rows).length) {
      tb.append(el("tr", { class: cls }, el("th", { text: label }), el("td", { colspan: 6, class: "muted", text: "아직 평가하지 않았습니다 — 아래 표에서 입력하거나 체크 후 일괄 처리" })));
      return;
    }
    const tr = el("tr", { class: cls }, el("th", { text: label }),
      el("td", { class: "r", text: s.raw.toLocaleString() + "일" }),
      el("td", { class: "r", text: fmt1(s.days) + "일" }),
      el("td", { class: "r", text: s.years.toFixed(2) + "년" }));
    s.pts.forEach((p, i) => tr.append(el("td", { class: "r" + (other && p !== other.pts[i] ? " diff" : ""), text: p.toFixed(2) })));
    tb.append(tr);
    for (const k of ["유사", "관련"]) {
      tb.append(el("tr", { class: "sub" }, el("th", { text: "　└ " + k }),
        el("td", { class: "r", text: s.t[k][0].toLocaleString() + "일" }),
        el("td", { class: "r", text: fmt1(s.t[k][1]) + "일" }), el("td", { colspan: 4 })));
    }
  };
  line("AI", ai, "ai-row");
  const n = Object.keys(RV.review.rows).filter((k) => RV.review.rows[k].인정여부).length;
  line(n < RV.rows.length ? `평가위원 (${n}/${RV.rows.length}행 기준)` : "평가위원", rv, "rv-row", ai);
}

function renderCardsFoot(ai, rv) {
  const f = $("#rv-cards-foot");
  f.innerHTML = "";
  const n = Object.values(RV.review.rows).filter((v) => v.인정여부).length;
  for (const [k, a, b] of [["유사용역", ai.t.유사, rv.t.유사], ["관련용역", ai.t.관련, rv.t.관련], ["총계", [ai.raw, ai.days], [rv.raw, rv.days]]]) {
    f.append(el("div", { class: "cf" + (k === "총계" ? " tot" : "") }, el("b", { text: k }),
      el("span", { class: "a", text: `AI 인정 ${a[0].toLocaleString()}일 → 환산 ${fmt1(a[1])}일` }),
      el("span", { class: "r", text: n ? `평가위원 인정 ${b[0].toLocaleString()}일 → 환산 ${fmt1(b[1])}일` : "평가위원 —" })));
  }
}

function renderFoot(ai, rv) {
  const tf = $("#rv-table tfoot");
  tf.innerHTML = "";
  for (const k of ["유사", "관련", "총계"]) {
    const a = k === "총계" ? [ai.raw, ai.days] : ai.t[k], b = k === "총계" ? [rv.raw, rv.days] : rv.t[k];
    tf.append(el("tr", {},
      el("td", { colspan: 7, class: "r", text: k === "총계" ? "총   계" : `${k}용역 소계` }),
      el("td", { class: "r", text: a[0].toLocaleString() }), el("td", { colspan: 6 }),
      el("td", { class: "ai-c r", text: "" }), el("td", { class: "ai-c r", text: fmt1(a[1]) }), el("td", { class: "ai-c" }),
      el("td", { class: "rv-c", text: k === "총계" ? "" : k }), el("td", { class: "rv-c" }),
      el("td", { class: "rv-c r", text: fmt1(b[1]) }), el("td", { class: "rv-c" })));
  }
}

function refresh() {
  const ai = totals((r) => r.ai), rv = totals((r) => entry(r.key));
  renderSummary(ai, rv);
  renderFoot(ai, rv);
  renderCardsFoot(ai, rv);
  const counts = { all: 0, ok: 0, flag: 0, no: 0, todo: 0, diff: 0 };
  let shown = 0, shownSel = 0;
  for (const r of RV.rows) {
    const v = entry(r.key), tr = rowEl(r.key);
    const done = !!v.인정여부;
    const diff = done && (v.인정여부 !== r.ai.인정여부 || (v.인정율 ?? null) !== (r.ai.인정율 ?? null));
    const f = { all: true, ok: r.ai.인정여부 !== "불인정", flag: r.ai.확인필요.length > 0, no: r.ai.인정여부 === "불인정", todo: !done, diff };
    for (const k in counts) counts[k] += f[k] ? 1 : 0;
    if (tr) {
      tr.classList.toggle("diff", diff);
      tr.hidden = !f[RV.filter];
      if (!tr.hidden) { shown++; if (RV.sel.has(r.key)) shownSel++; }
    }
  }
  document.querySelectorAll("#rv-filters button").forEach((b) => (b.querySelector("i").textContent = counts[b.dataset.f]));
  const done = RV.rows.length - counts.todo;
  text($("#rv-progress"), `평가 ${done}/${RV.rows.length} · AI와 다름 ${counts.diff}`);
  document.querySelectorAll(".rv-all").forEach((all) => {
    all.checked = shown > 0 && shownSel === shown;
    all.indeterminate = shownSel > 0 && shownSel < shown;
  });
  $("#rv-bulk").hidden = RV.sel.size === 0;
  text($("#bk-count"), `${RV.sel.size}행 선택 — 체크된 행의 인정여부·인정율·사유를 바꾸면 선택한 행 모두에 적용`);
}

// ── 선택·일괄 처리 ──
function toggleSel(idx, on, range) {
  const idxs = range && RV.lastIdx != null
    ? Array.from({ length: Math.abs(idx - RV.lastIdx) + 1 }, (_, k) => Math.min(idx, RV.lastIdx) + k) : [idx];
  for (const i of idxs) {
    const r = RV.rows[i], tr = rowEl(r.key);
    if (tr && tr.hidden) continue;
    on ? RV.sel.add(r.key) : RV.sel.delete(r.key);
    if (tr) paintRow(tr, r);
  }
  RV.lastIdx = idx;
  refresh();
}

function bulk(action) {
  const keys = [...RV.sel];
  if (action === "none") { RV.sel.clear(); }
  else {
    const rate = $("#bk-rate").value, reason = $("#bk-reason").value.trim();
    for (const key of keys) {
      const r = RV.rows.find((x) => x.key === key), cur = { ...entry(key) };
      if (action === "clear") { delete RV.review.rows[key]; continue; }
      if (action === "ai") { cur.인정여부 = r.ai.인정여부; cur.인정율 = r.ai.인정율; }
      else {
        cur.인정여부 = action;
        cur.인정율 = action === "불인정" ? null : rate === "auto" ? autoRate(r, action) : Number(rate);
      }
      if (reason) cur.사유 = reason;
      RV.review.rows[key] = cur;
    }
    scheduleSave();
  }
  rowEls().forEach((tr) => paintRow(tr, RV.rows[tr.dataset.i]));
  refresh();
}

function showPage(r, tr) {
  document.querySelectorAll(".cur").forEach((x) => x.classList.remove("cur"));
  tr.classList.add("cur");
  $("#rv-page-img").src = `/api/evaluations/${enc()}/pages/${r.쪽}`;
  $("#rv-page-img").alt = `경력증명서 ${r.쪽}쪽`;
  text($("#rv-page-cap"), `경력증명서 p${String(r.쪽).padStart(2, "0")} · ${r.사업명}`);
  openDrawer(true);
}

function openDrawer(on) { $("#drawer").hidden = !on; document.body.classList.toggle("drawer-open", on); }
$("#drawer-close").onclick = () => openDrawer(false);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") openDrawer(false); });
$("#rv-back").onclick = () => { openDrawer(false); openDetail(RV.id); };
$("#rv-name").oninput = () => { RV.review.평가위원 = $("#rv-name").value; scheduleSave(); };
document.querySelectorAll(".rv-all").forEach((box) => (box.onclick = () => {
  const on = box.checked;
  rowEls().forEach((tr) => {
    if (tr.hidden) return;
    on ? RV.sel.add(tr.dataset.key) : RV.sel.delete(tr.dataset.key);
    paintRow(tr, RV.rows[tr.dataset.i]);
  });
  refresh();
}));
$("#rv-view").onclick = (e) => {
  const b = e.target.closest("button[data-v]");
  if (!b || b.dataset.v === RV.view) return;
  RV.view = b.dataset.v;
  saveView(RV.view);
  renderRows();
  refresh();
};
$("#rv-bulk").onclick = (e) => { const b = e.target.closest("[data-bk]"); if (b) bulk(b.dataset.bk); };
$("#rv-accept").onclick = () => {
  const empty = RV.rows.filter((r) => !entry(r.key).인정여부);
  if (!empty.length) return;
  if (!confirm(`평가하지 않은 ${empty.length}행을 AI 판단대로 채웁니다. 계속할까요?`)) return;
  for (const r of empty) RV.review.rows[r.key] = { 인정여부: r.ai.인정여부, 인정율: r.ai.인정율, 사유: entry(r.key).사유 || "" };
  rowEls().forEach((tr) => paintRow(tr, RV.rows[tr.dataset.i]));
  refresh();
  scheduleSave();
};
$("#rv-filters").onclick = (e) => {
  const b = e.target.closest("button[data-f]");
  if (!b) return;
  RV.filter = b.dataset.f;
  document.querySelectorAll("#rv-filters button").forEach((x) => x.classList.toggle("on", x === b));
  refresh();
};
