// 평가기준 편집 / 점수 편집 화면.
// 두 화면은 같은 틀(상단 저장 막대 + 본문)을 쓰고, 서버의 기준 파일 한 개를 나눠서 고친다.
const ED = {
  rules: { data: null, orig: null, url: "/api/criteria/rules", key: "규칙", body: "#rules-body", render: () => renderRules() },
  scores: { data: null, orig: null, url: "/api/criteria/scores", key: "점수", body: "#scores-body", render: () => renderScores() },
};
const clone = (o) => JSON.parse(JSON.stringify(o));

async function openEditor(kind) {
  show(kind);
  const d = await api("/api/criteria");
  for (const k of ["rules", "scores"]) { ED[k].data = clone(d[ED[k].key]); ED[k].orig = clone(d[ED[k].key]); }
  ED.file = d.파일;
  renderBar(kind);
  ED[kind].render();
}

const dirty = (kind) => JSON.stringify(ED[kind].data) !== JSON.stringify(ED[kind].orig);
function markDirty(kind) {
  const bar = document.querySelector(`.ed-bar[data-ed="${kind}"]`);
  bar.classList.toggle("dirty", dirty(kind));
  text(bar.querySelector(".ed-state"), dirty(kind) ? "● 저장하지 않은 변경이 있습니다" : `저장된 기준 · ${ED.file}`);
}

function renderBar(kind) {
  const bar = document.querySelector(`.ed-bar[data-ed="${kind}"]`);
  bar.innerHTML = "";
  const memo = el("input", { class: "ed-memo", placeholder: "변경 메모 (예: '법면' 추가)" });
  const save = el("button", { class: "btn primary", text: "저장" });
  const reset = el("button", { class: "btn ghost", text: "변경 취소" });
  const histBtn = el("button", { class: "btn ghost", text: "변경 이력" });
  const msg = el("span", { class: "ed-msg" });
  const hist = el("div", { class: "ed-hist", hidden: "" });
  bar.append(el("span", { class: "ed-state" }), el("span", { class: "grow" }), msg, memo, reset, histBtn, save, hist);
  save.onclick = async () => {
    msg.className = "ed-msg";
    text(msg, "저장 중…");
    try {
      const d = await api(ED[kind].url, { method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 값: ED[kind].data, 메모: memo.value }) });
      for (const k of ["rules", "scores"]) { ED[k].data = clone(d[ED[k].key]); ED[k].orig = clone(d[ED[k].key]); }
      memo.value = "";
      text(msg, "✓ 저장됨 — 새 평가부터 적용 (기존 평가는 결과 화면의 [현재 기준으로 다시 판정])");
      msg.className = "ed-msg ok";
      ED[kind].render();
      markDirty(kind);
      if (!hist.hidden) loadHistory(kind, hist);
    } catch (e) { text(msg, "저장 안 됨: " + e.message); msg.className = "ed-msg err"; }
  };
  reset.onclick = () => {
    if (dirty(kind) && !confirm("저장하지 않은 변경을 버립니다.")) return;
    ED[kind].data = clone(ED[kind].orig); ED[kind].render(); markDirty(kind); text(msg, "");
  };
  histBtn.onclick = () => { hist.hidden = !hist.hidden; if (!hist.hidden) loadHistory(kind, hist); };
  markDirty(kind);
}

async function loadHistory(kind, box) {
  box.innerHTML = "";
  const list = await api("/api/criteria/history");
  if (!list.length) { box.append(el("p", { class: "muted", text: "아직 저장 이력이 없습니다." })); return; }
  box.append(el("p", { class: "muted small", text: "저장할 때마다 그 직전 기준이 남습니다. 되돌리면 지금 기준도 이력에 남습니다." }));
  for (const h of list.slice(0, 30)) {
    const b = el("button", { class: "btn sm", text: "이 버전으로 되돌리기" });
    b.onclick = async () => {
      if (!confirm(`${h.저장전시각} 저장 직전 기준으로 되돌릴까요?`)) return;
      const d = await api("/api/criteria/restore", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ 파일: h.파일 }) });
      for (const k of ["rules", "scores"]) { ED[k].data = clone(d[ED[k].key]); ED[k].orig = clone(d[ED[k].key]); }
      ED[kind].render(); markDirty(kind); loadHistory(kind, box);
    };
    box.append(el("div", { class: "ed-hrow" }, el("span", { text: h.저장전시각 + " 이전" }),
      el("span", { class: "muted", text: (h.메모 || "").replaceAll("_", " ") }), b));
  }
}

// ── 공통 편집 부품 ──
function getAt(obj, path) { return path.reduce((o, k) => (o == null ? o : o[k]), obj); }
function setAt(obj, path, v) { const last = path[path.length - 1]; getAt(obj, path.slice(0, -1))[last] = v; }

function chips(kind, path, opts = {}) {
  const wrap = el("div", { class: "chips-ed" });
  const draw = () => {
    wrap.innerHTML = "";
    const list = getAt(ED[kind].data, path) || [];
    list.forEach((w, i) => {
      const x = el("button", { class: "x", "aria-label": `'${w}' 삭제`, text: "×" });
      x.onclick = () => { list.splice(i, 1); draw(); markDirty(kind); };
      wrap.append(el("span", { class: "chip" + (opts.regex ? " mono" : "") }, el("span", { text: w }), x));
    });
    const inp = el("input", { class: "chip-in", placeholder: opts.placeholder || "단어 입력 후 Enter" });
    const add = () => {
      const v = inp.value.trim();
      if (!v) return;
      if (list.includes(v)) { inp.value = ""; return; }
      list.push(v);
      draw(); markDirty(kind);
      wrap.querySelector(".chip-in").focus();
    };
    inp.onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); add(); } };
    wrap.append(inp, el("button", { class: "btn sm", text: "추가", onclick: null }));
    wrap.lastChild.onclick = add;
  };
  draw();
  return wrap;
}

function field(title, desc, control, extra) {
  return el("div", { class: "ed-field" + (extra ? " " + extra : "") },
    el("div", { class: "ed-lbl" }, el("b", { text: title }), desc ? el("p", { text: desc }) : null), control);
}
const group = (step, title, desc, ...fields) =>
  el("section", { class: "ed-group" }, el("div", { class: "ed-gh" }, step ? el("span", { class: "step", text: step }) : null,
    el("h3", { text: title }), desc ? el("p", { class: "muted small", text: desc }) : null), ...fields);

function textInput(kind, path, attrs = {}) {
  const i = el("input", { value: getAt(ED[kind].data, path) ?? "", ...attrs });
  i.oninput = () => { setAt(ED[kind].data, path, i.value); markDirty(kind); };
  return i;
}
function textArea(kind, path) {
  const t = el("textarea", { rows: 2 });
  t.value = getAt(ED[kind].data, path) ?? "";
  t.oninput = () => { setAt(ED[kind].data, path, t.value); markDirty(kind); };
  return t;
}

// ── 평가기준 편집 ──
function renderRules() {
  const body = $("#rules-body"), K = "rules", D = ED.rules.data;
  body.innerHTML = "";
  const roadGroup = (part) => {
    const box = el("div", { class: "roads" });
    for (const label of Object.keys(D.유사어휘[part])) {
      box.append(el("div", { class: "road" }, el("span", { class: "road-l", text: label }), chips(K, ["유사어휘", part, label])));
    }
    return box;
  };
  body.append(
    group("", "기본", "",
      field("기준 이름", "엑셀·화면에 표시되는 평가기준 이름", textInput(K, ["이름"])),
      field("경력 기산일", "이 날짜 이전 경력은 불인정 (YYYY.MM.DD)", textInput(K, ["기산일"], { class: "w-date", placeholder: "1995.01.05" }))),
    group("R2", "용역 종류", "사업명에 아래 단어가 없으면 점검·진단·성능평가 용역이 아니므로 불인정",
      field("인정 용역 단어", "사업명에 하나라도 있으면 점검·진단·성능평가 용역", chips(K, ["용역어휘"])),
      field("제외할 표현", "이 표현은 용역 단어로 보지 않음 (예: 내진성능평가)", chips(K, ["용역제외어휘"])),
      field("급경사지 단어", "있으면 불인정 + 확인필요(급경사지법 용역 여부)", chips(K, ["급경사지어휘"]))),
    group("R3", "대상 시설 (절토사면·옹벽)", "사업명 → 공사종류 → 공사개요 순으로 확인. 대상·비대상 단어가 섞이면 확인필요",
      field("대상 단어 (사업명)", "절토사면·옹벽 대상으로 보는 단어", chips(K, ["대상어휘"])),
      field("비대상 단어 (사업명)", "교량·터널 등 대상이 아닌 시설", chips(K, ["비대상어휘"])),
      field("대상 공사종류", "경력증명서 '공사종류' 칸 값", chips(K, ["대상공사종류"])),
      field("비대상 공사종류", "", chips(K, ["비대상공사종류"])),
      field("대상 단어 (공사개요)", "사업명·공사종류로 못 정할 때 공사개요에서 찾는 단어", chips(K, ["개요대상어휘"]))),
    group("R4", "위치 — 유사 / 관련", "도로법 제10조 도로면 유사, 그 밖이면 관련. 노선을 못 찾으면 유사로 가정하고 확인필요",
      field("관련으로 볼 사업명 단어", "도로법 도로가 아닌 곳 (면도·학교·농공단지 등)", chips(K, ["관련어휘", "사업명"])),
      field("관련으로 볼 발주자 단어", "", chips(K, ["관련어휘", "발주자"])),
      field("유사 — 사업명의 도로 종류", "사업명에 있으면 해당 도로법 도로로 판정", roadGroup("사업명")),
      field("유사 — 발주자로 보는 도로 종류", "사업명에 노선이 없을 때 발주자로 판정", roadGroup("발주자"))),
    group("R5", "인정율 판단", "사업명에 아래 단어가 있으면 진단·성능평가 인정율, 없으면 점검 인정율 (율 자체는 [점수 편집])",
      field("진단·성능평가 단어", "", chips(K, ["진단성능어휘"])),
      field("정기점검 단어", "사업명에 있으면 확인필요(정기점검 혼재)", chips(K, ["정기어휘"]))),
  );
  const g = el("section", { class: "ed-group" }, el("div", { class: "ed-gh" }, el("h3", { text: "조항 근거 문구" }),
    el("p", { class: "muted small", text: "판단근거와 엑셀 하단 메모에 그대로 찍히는 평가기준 원문" })));
  for (const k of Object.keys(D.근거)) g.append(field(k, "", textArea(K, ["근거", k]), "wide"));
  body.append(g);
  const adv = el("details", { class: "ed-group adv" }, el("summary", { text: "고급 설정 — 정규식 (잘못 고치면 판정이 틀어질 수 있음)" }),
    field("교량 이름 형태", "'○○교' 같은 교량명을 찾는 식", textInput(K, ["교량명정규식"], { class: "mono" })),
    field("지방도 약칭", "'지456호' 같은 표현", textInput(K, ["지방도약칭정규식"], { class: "mono" })),
    field("고속국도 노선명", "'경부선', '서울외곽선' 등", textInput(K, ["고속노선정규식"], { class: "mono" })),
    field("관련 사업명 정규식", "", chips(K, ["관련어휘", "사업명정규식"], { regex: true, placeholder: "정규식 입력 후 Enter" })));
  body.append(adv);
}

// ── 점수 편집 ──
const ROLE_LIST = ["사업책임", "분야책임", "분야참여"];
function numInput(kind, get, set, attrs = {}) {
  const i = el("input", { type: "number", value: get(), ...attrs });
  i.oninput = () => { const v = i.value === "" ? NaN : Number(i.value); set(v); markDirty(kind); updatePreview(); };
  return i;
}

function renderScores() {
  const body = $("#scores-body"), K = "scores", D = ED.scores.data;
  body.innerHTML = "";
  const pctIn = (g, k) => numInput(K, () => Math.round(D.인정율[g][k] * 1000) / 10,
    (v) => (D.인정율[g][k] = Math.round(v * 10) / 1000), { min: 0, max: 100, step: 5, class: "w-num" });
  const rates = el("table", { class: "grid compact ed-rates" },
    el("thead", {}, el("tr", {}, el("th"), el("th", { text: "정밀안전진단·성능평가" }), el("th", { text: "정밀안전점검·긴급안전점검" }))),
    el("tbody", {},
      el("tr", {}, el("th", { text: "유사용역 — 당해분야" }), el("td", {}, pctIn("유사", "진단성능"), " %"), el("td", {}, pctIn("유사", "점검"), " %")),
      el("tr", {}, el("th", { text: "관련용역 — 그 외 분야" }), el("td", {}, pctIn("관련", "진단성능"), " %"), el("td", {}, pctIn("관련", "점검"), " %"))));
  body.append(group("", "인정율", "환산일수 = 인정일 × 인정율. 어느 율을 쓸지는 [평가기준 편집]의 R5 단어로 정함", rates),
    group("", "일 → 년 환산", "환산년수 = 환산일수 ÷ 이 값",
      field("1년 = ", "", el("span", {}, numInput(K, () => D.일수_연환산, (v) => (D.일수_연환산 = Math.round(v)),
        { min: 1, max: 366, step: 1, class: "w-num" }), " 일"))));

  const bands = el("div", { class: "bands" });
  for (const role of ROLE_LIST) {
    const rows = D.배점[role];
    const tb = el("tbody");
    rows.forEach((row, i) => {
      const last = i === rows.length - 1;
      const del = el("button", { class: "btn sm ghost", text: "삭제", "aria-label": `${role} 구간 삭제` });
      del.onclick = () => { rows.splice(i, 1); renderScores(); markDirty(K); };
      tb.append(el("tr", {},
        el("td", {}, last ? el("span", { class: "muted", text: "그 미만 (0년~)" })
          : el("span", {}, numInput(K, () => row[0], (v) => (row[0] = v), { min: 0, step: 0.5, class: "w-num" }), " 년 이상")),
        el("td", {}, numInput(K, () => row[1], (v) => (row[1] = v), { min: 0, step: 0.05, class: "w-num" }), " 점"),
        el("td", {}, last || rows.length <= 2 ? null : del)));
    });
    const add = el("button", { class: "btn sm", text: "＋ 구간 추가" });
    add.onclick = () => {
      const top = rows[0];
      rows.unshift([Math.round((top[0] + 1) * 10) / 10, top[1]]);
      renderScores(); markDirty(K);
    };
    bands.append(el("div", { class: "band panel" }, el("h3", { text: role + "기술인" }),
      el("table", { class: "grid compact" }, el("thead", {}, el("tr", {}, el("th", { text: "환산년수" }), el("th", { text: "점수" }), el("th"))), tb), add));
  }
  body.append(group("", "경력 배점표 (가-2 ①)", "위에서 아래로 기준년수가 줄어들어야 하고, 마지막 줄은 '그 미만'입니다", bands));

  const prev = el("div", { class: "preview" }, el("label", {}, "환산년수 ",
    el("input", { type: "number", id: "pv-years", value: "2.62", step: "0.01", min: "0", class: "w-num" }), " 년이면 →"),
    el("span", { id: "pv-out" }));
  body.append(group("", "미리 계산", "저장 전에 배점표가 맞게 들어갔는지 확인", prev));
  $("#pv-years").oninput = updatePreview;
  updatePreview();
}

function updatePreview() {
  const out = $("#pv-out");
  if (!out || !ED.scores.data) return;
  const y = Number($("#pv-years").value) || 0;
  out.textContent = ROLE_LIST.map((role) => {
    const rows = ED.scores.data.배점[role];
    const hit = rows.find(([th]) => y >= th) || rows[rows.length - 1];
    return `${role} ${hit[1]}점`;
  }).join("   ·   ");
}

document.querySelector(".topnav").onclick = (e) => {
  const b = e.target.closest("button[data-go]");
  if (!b) return;
  const cur = views.find((v) => !$("#view-" + v).hidden);
  if (["rules", "scores"].includes(cur) && cur !== b.dataset.go && dirty(cur) && !confirm("저장하지 않은 변경을 버리고 이동할까요?")) return;
  if (b.dataset.go === "list") loadList(); else openEditor(b.dataset.go);
};
window.addEventListener("beforeunload", (e) => {
  if (["rules", "scores"].some((k) => ED[k].data && dirty(k))) { e.preventDefault(); e.returnValue = ""; }
});
