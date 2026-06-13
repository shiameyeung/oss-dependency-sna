# -*- coding: utf-8 -*-
"""
make_demo.py — 分析結果 JSON を埋め込んだ自己完結型 HTML デモを生成する

特徴:
  - 単一ファイル・外部 CDN 依存なし（学内発表などオフライン環境でも動作）
  - 配色は 2026-06-03 発表スライドのパレットに統一（クリーム地・青・キャンディイエロー）
  - 領域切替（PyPI / Go）、指標切替、コミュニティ着色、Top10 ランキング、切断点 ⚠ 表示
  - 【DSS 機能】診断カード: ノードクリックで「指標データ＋これは何を意味するか＋推奨」を表示。
    生成は AI ではなく決定論的なルール＋テンプレート（ノード型 × 意思決定場面の対応表）。
    型判定条件: 切断点 = art フラグ ／ 橋渡し型 = btw>0 かつ 被依存順位−媒介順位 ≥ 5 ／
    土台型 = 被依存上位 10 位以内 かつ btw≈0 かつ indeg≥3 ／ 孤立 = indeg=outdeg=0 ／ 他は標準。
  - 【DSS 機能】切断点クリックで「その点を除くと孤立する範囲」をハイライト（cut_impact を事前計算）
  - 【DSS 機能】散布図ビュー: 被依存数 × 媒介中心性。順位乖離（RQ3）が一枚で見える
  - 【DSS 機能】コミュニティのフォーカス表示と統計（規模・内部密度・代表ノード）
  - 【規模対策】表示ノード数の Top-N フィルタ（選択中指標の上位 N 件のみ描画）
  - フッターに再現性情報（取得日・シード成功率・seed・指標処理時間・Spearman ρ）

使い方:
  python3 make_demo.py --inputs output/pypi_metrics.json output/go_metrics.json \
                       --out output/oss_sna_demo_v2.html
"""

import argparse
import json
import pathlib

TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>OSS 依存ネットワーク分析デモ v2 — DSS 型分析支援システム（研究用プロトタイプ）</title>
<style>
  /* 配色: 2026-06-03 発表スライドのパレットに統一（クリーム地・青・キャンディイエロー） */
  :root { --bg:#FFFDF5; --panel:#ffffff; --panel2:#EAF4FF; --txt:#1F2D40; --sub:#5C6B7A;
          --acc:#2C5F94; --acc2:#5DA8E8; --warn:#E2A82E; --warnbg:#FFF8D6; --line:#DCE6F2; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--txt);
         font-family:"Yu Gothic","Hiragino Kaku Gothic ProN","Noto Sans JP",sans-serif; }
  header { padding:14px 20px 10px; border-bottom:1px solid var(--line); }
  h1 { font-size:17px; margin:0 0 6px; font-weight:700; color:var(--acc); }
  .sub { color:var(--sub); font-size:12px; }
  .bar { display:flex; gap:10px; flex-wrap:wrap; padding:12px 20px 10px; align-items:stretch; }
  .grp { display:flex; align-items:center; gap:5px; background:var(--panel);
         border:1px solid var(--line); border-radius:9px; padding:6px 12px; }
  .grp .lbl { color:var(--sub); font-size:10.5px; font-weight:700; letter-spacing:.06em;
              margin-right:5px; white-space:nowrap; }
  button { background:#F2F6FA; color:var(--txt); border:1px solid transparent;
           border-radius:6px; padding:6px 12px; font-size:12.5px; cursor:pointer; }
  button:hover { border-color:var(--acc2); }
  button.on { background:var(--acc); color:#ffffff; font-weight:700; }
  button.dis { opacity:.35; pointer-events:none; }
  .sliderbox { display:inline-flex; align-items:center; gap:6px; }
  .sliderbox input { width:130px; accent-color:var(--acc); }
  .sliderbox .val { font-size:12px; color:var(--sub); min-width:86px; }
  #q { border:1px solid var(--line); border-radius:6px; padding:6px 9px; font-size:12px;
       width:150px; background:#F2F6FA; color:var(--txt); font-family:inherit; }
  #q:focus { outline:none; border-color:var(--acc2); background:#fff; }
  #catSel { border:1px solid var(--line); border-radius:6px; padding:5px 6px; font-size:12px;
            background:#F2F6FA; color:var(--txt); font-family:inherit; max-width:170px; }
  .diag-desc { font-size:11px; color:var(--sub); font-style:italic; margin:1px 0 5px; line-height:1.45; }
  main { display:grid; grid-template-columns: 1fr 360px; gap:12px; padding:0 20px 8px; }
  .stage { background:var(--panel); border:1px solid var(--line); border-radius:10px; position:relative; }
  svg { width:100%; height:660px; display:block; }
  svg text { pointer-events:none; }  /* ラベルがノードのクリックを遮らないように */
  .side { display:flex; flex-direction:column; gap:12px; max-height:660px; overflow-y:auto; }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:12px 14px; }
  .card h2 { font-size:13px; margin:0 0 8px; color:var(--acc); font-weight:700; }
  .badge { display:inline-block; font-size:11px; font-weight:700; color:#fff; border-radius:4px;
           padding:2px 8px; margin:0 4px 6px 0; }
  .diag-name { font-size:14px; font-weight:700; color:var(--txt); margin-bottom:4px; word-break:break-all; }
  .diag-table { width:100%; border-collapse:collapse; font-size:11.5px; margin:6px 0 8px; }
  .diag-table td { padding:2.5px 4px; border-bottom:1px solid var(--line); }
  .diag-table td:first-child { color:var(--sub); width:46%; }
  .diag-text { font-size:12px; line-height:1.55; margin:0 0 6px; }
  .diag-reco { font-size:11.5px; line-height:1.5; background:var(--warnbg); border-left:3px solid #F2C84B;
               border-radius:4px; padding:6px 8px; margin-top:6px; }
  .diag-cut { font-size:11px; line-height:1.5; background:var(--panel2); border-radius:4px;
              padding:6px 8px; margin-top:6px; word-break:break-all; }
  .hint { color:var(--sub); font-size:11.5px; line-height:1.5; }
  .rank-row { display:flex; align-items:center; gap:8px; padding:3px 4px; border-radius:5px;
              cursor:pointer; font-size:12px; }
  .rank-row:hover { background:var(--panel2); }
  .rank-row.sel { background:var(--panel2); outline:1px solid var(--acc2); }
  .rank-row .nm { flex:0 0 150px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .rank-row .bar-bg { flex:1; height:9px; background:var(--panel2); border-radius:4px; overflow:hidden; }
  .rank-row .bar-fg { height:100%; background:var(--acc2); }
  .rank-row .val { flex:0 0 56px; text-align:right; color:var(--sub); font-variant-numeric:tabular-nums; }
  .divband { margin:12px 20px 0; background:var(--panel); border:1px solid var(--line);
             border-radius:10px; padding:12px 14px; }
  .divband h2 { font-size:13px; margin:0 0 8px; color:var(--acc); font-weight:700; }
  #divList { display:grid; grid-template-columns:repeat(auto-fill, minmax(300px, 1fr)); gap:6px; }
  .div-row { font-size:12px; padding:5px 6px; border-left:3px solid #F2C84B;
             background:var(--warnbg); border-radius:4px; cursor:pointer; }
  .div-row b { color:#A8761A; }
  .muted { color:var(--sub); font-size:11.5px; }
  footer { padding:8px 20px 16px; color:var(--sub); font-size:11.5px; line-height:1.7; }
  #tip { position:absolute; pointer-events:none; background:#ffffffee; border:1px solid var(--line);
         border-radius:8px; padding:8px 10px; font-size:12px; display:none; max-width:280px; z-index:5;
         color:var(--txt); box-shadow:0 2px 10px rgba(31,45,64,.12); }
  #tip b { color:var(--acc); }
  .legend { display:flex; gap:14px; flex-wrap:wrap; font-size:11.5px; color:var(--sub);
            padding:6px 20px 2px; }
  .legend span { display:inline-flex; align-items:center; gap:5px; }
  .dot { width:10px; height:10px; border-radius:50%; display:inline-block; }
</style>
</head>
<body>
<header>
  <h1>OSS 依存ネットワーク分析デモ v2 <span class="sub">— DSS 型分析支援システム（研究用プロトタイプ）</span></h1>
  <div class="sub">エッジの向き: 依存元 → 依存先。ノードの大きさ・色 = 選択中の指標。⚠ = 切断点（除去すると孤立が生じるノード）。ノードをクリックすると右上に診断を表示。</div>
</header>
<div class="bar">
  <div class="grp"><span class="lbl">領域</span><span id="domains"></span></div>
  <div class="grp"><span class="lbl">ビュー</span><span id="views"></span></div>
  <div class="grp"><span class="lbl">指標</span><span id="metrics"></span>
    <button id="comBtn" title="Louvain 法で検出したコミュニティごとに着色">コミュニティ着色</button></div>
  <div class="grp"><span class="lbl">検索・分類</span>
    <input type="text" id="q" list="qlist" placeholder="名前で検索…">
    <datalist id="qlist"></datalist>
    <select id="catSel"></select></div>
  <div class="grp"><span class="lbl">表示数</span>
    <span class="sliderbox"><input type="range" id="topn" min="10" max="300" step="10">
    <span class="val" id="topnVal"></span></span></div>
</div>
<main>
  <div class="stage">
    <svg id="svg" viewBox="0 0 1000 660" xmlns="http://www.w3.org/2000/svg">
      <g id="edges"></g><g id="nodes"></g><g id="labels"></g>
    </svg>
    <div id="tip"></div>
  </div>
  <div class="side">
    <div class="card">
      <h2>診断 — これは何を意味するか</h2>
      <div id="diag"><div class="hint">ノード（またはコミュニティ着色時のコミュニティ行）をクリックすると、
        指標データと「意思決定上何を意味するか」の診断を表示します。<br>
        診断はノード型 × 意思決定場面の対応表に基づく決定論的なルール＋テンプレートで生成（AI 不使用・再現可能）。</div></div>
    </div>
    <div class="card">
      <h2 id="rankTitle">Top 10</h2>
      <div id="rankList"></div>
    </div>
  </div>
</main>
<div class="divband">
  <h2>順位の乖離 — 単純統計では見えない「要衝」（RQ3）</h2>
  <div id="divList"></div>
  <div class="muted" id="spearman" style="margin-top:8px"></div>
</div>
<div class="legend">
  <span><span class="dot" style="background:#5DA8E8"></span>通常ノード</span>
  <span><span class="dot" style="background:#5DA8E8; outline:2px solid #1F2D40"></span>シード（分析起点）</span>
  <span><span class="dot" style="background:transparent; border:2.5px solid var(--warn)"></span>切断点 ⚠（クリックで孤立する範囲を表示）</span>
  <span><span class="dot" style="background:#F2C84B"></span>切断時に孤立する範囲</span>
</div>
<footer id="meta"></footer>
<script>
const DATA = __DATA_JSON__;
const MLAB = { indeg:"被依存数（直接依存元の数・単純統計）", impact:"影響範囲（推移的に波及する依存元数）",
               btw:"媒介中心性（橋渡し・経路上の要）", pr:"PageRank（構造的重要度）",
               eig:"固有ベクトル中心性（重要ノードから依存される度合い）" };
const COLORS = ["#5DA8E8","#F2C84B","#81c784","#ba68c8","#ff8a65","#4dd0e1","#f06292","#a1887f","#90a4ae","#dce775"];
const TYPE_INFO = {
  cutpoint:   {label:"切断点",   color:"#E2A82E"},
  bridge:     {label:"橋渡し型", color:"#A8761A"},
  foundation: {label:"土台型",   color:"#2C5F94"},
  isolated:   {label:"孤立",     color:"#5C6B7A"},
  normal:     {label:"標準",     color:"#5C6B7A"},
};
let curD = Object.keys(DATA)[0], curM = "indeg", view = "net",
    comMode = false, selected = null, selectedCom = null, topN = 0, catFilter = "";

const $ = s => document.querySelector(s);
function colorOf(t){ // 指標値 t∈[0,1] を青系グラデーションに（CFE6FF→5DA8E8→1F4E79）
  const s=[[207,230,255],[93,168,232],[31,78,121]];
  const [a,b,k]= t<.5 ? [s[0],s[1],t*2] : [s[1],s[2],(t-.5)*2];
  return `rgb(${a.map((v,i)=>Math.round(v+(b[i]-v)*k)).join(",")})`;
}
function px(n){ return 40 + n.x*920; }
function py(n){ return 30 + n.y*600; }
function esc(t){ return String(t).replace(/&/g,"&amp;").replace(/</g,"&lt;"); }

function visibleIds(g){
  // 分類フィルタ → Top-N の順に適用。両方なしなら null（全表示）
  let pool = catFilter ? g.nodes.filter(n=>n.cat===catFilter) : g.nodes;
  if (topN && topN < pool.length){
    pool = [...pool].sort((a,b)=> b[curM]-a[curM] || (a.id<b.id?-1:1)).slice(0, topN);
  } else if (!catFilter) {
    return null;
  }
  return new Set(pool.map(n=>n.id));
}

// 隣接集合（フォーカス表示用・領域ごとにキャッシュ）
const adjCache = new Map();
function neighborsOf(g, id){
  if (!adjCache.has(g.domain)){
    const m = new Map();
    for (const e of g.edges){
      if (!m.has(e.s)) m.set(e.s, new Set());
      if (!m.has(e.t)) m.set(e.t, new Set());
      m.get(e.s).add(e.t); m.get(e.t).add(e.s);
    }
    adjCache.set(g.domain, m);
  }
  return adjCache.get(g.domain).get(id) || new Set();
}

/* ---------- 診断（決定的ルール + テンプレート。AI 不使用） ---------- */
function nodeTypes(n){
  const t = [];
  if (n.art) t.push("cutpoint");
  if (n.btw > 0 && (n.r_in - n.r_bt) >= 5) t.push("bridge");
  if (n.indeg >= 3 && n.btw <= 1e-6 && n.r_in <= 10) t.push("foundation");
  if (n.indeg === 0 && n.outdeg === 0) t.push("isolated");
  if (!t.length) t.push("normal");
  return t;
}
function diagnoseNode(n, g){
  const N = g.nodes.length, CUT = g.cut_impact || {};
  const types = nodeTypes(n);
  let badges = types.map(t=>`<span class="badge" style="background:${TYPE_INFO[t].color}">${TYPE_INFO[t].label}</span>`).join("");
  if (n.seed) badges += `<span class="badge" style="background:#5DA8E8">シード</span>`;
  if (n.cat) badges += `<span class="badge" style="background:#8FA8C0">${esc(n.cat)}</span>`;
  const descHtml = n.desc ? `<div class="diag-desc">${esc(n.desc)}</div>` : "";
  const table = `<table class="diag-table">
    <tr><td>被依存数（単純統計）</td><td>${n.indeg}（全 ${N} 中 ${n.r_in}位）</td></tr>
    <tr><td>影響範囲（推移的）</td><td>${n.impact} パッケージ</td></tr>
    <tr><td>媒介中心性</td><td>${n.btw}（${n.r_bt}位）</td></tr>
    <tr><td>PageRank</td><td>${n.pr}</td></tr>
    <tr><td>コミュニティ</td><td>${n.com}</td></tr></table>`;
  const texts = [], recos = [];
  for (const t of types){
    if (t === "cutpoint"){
      const cut = CUT[n.id] || [];
      // 規模に応じた決定論的な言い分け（テンプレートの段階化）
      const phrase = cut.length >= 10
        ? `<b>${cut.length} 個</b>のパッケージが一斉に主要ネットワークから孤立し、影響が特に広範に及ぶ`
        : cut.length >= 3
        ? `<b>${cut.length} 個</b>のパッケージが主要ネットワークから孤立する`
        : `孤立する範囲は <b>${cut.length} パッケージ</b>と局所的にとどまるが、構造上の急所であることに変わりはない`;
      texts.push(`ネットワークの<b>切断点</b>にあたる。仮にこのパッケージが利用不能になると、${phrase}（図中に黄色でハイライト表示）。`);
      recos.push(`<b>集中リスク把握:</b> 最優先での監視を推奨。<b>利用・支援判断:</b> 代替経路の有無の事前確認を推奨。`);
      if (cut.length){
        const head = cut.slice(0,8).map(esc).join("、");
        texts.push(`<div class="diag-cut"><b>孤立する範囲:</b> ${head}${cut.length>8?` 他 ${cut.length-8} 件`:""}</div>`);
      }
    } else if (t === "bridge"){
      const gap = n.r_in - n.r_bt;
      const gapNote = gap >= 100 ? `両指標の順位差は ${gap} に達し、順位の乖離が際立って大きい。`
                    : gap >= 30  ? `両指標の順位差は ${gap} と大きい。` : "";
      texts.push(`被依存数（${n.r_in}位）に比べ、媒介中心性は <b>${n.r_bt}位</b>と明確に高い。${gapNote}依存経路の要衝（<b>橋渡し</b>）に位置し、障害時には複数のパッケージ群の間の依存経路が分断されるおそれがある。単純統計では検出しにくい型。`);
      recos.push(`<b>利用判断:</b> 保守体制・更新頻度の確認を推奨。<b>支援判断:</b> 見落とされやすい支援先候補。`);
    } else if (t === "foundation"){
      const share = n.impact / N;
      const reach = share >= 0.25 ? `分析対象ネットワーク全体の約 ${Math.round(share*100)}%（${n.impact} パッケージ）へ波及する`
                                  : `推移的に ${n.impact} パッケージへ波及する`;
      texts.push(`被依存数 ${n.indeg}（全体 ${n.r_in}位）の<b>基盤（土台型）</b>パッケージ。停止・脆弱性の影響は${reach}。単純統計でも検出できる型。`);
      recos.push(`<b>利用判断:</b> 広く利用されている標準的な選択肢。<b>集中リスク把握:</b> 依存が一点に集中する典型例。保守の継続性に注意。`);
    } else if (t === "isolated"){
      texts.push(`このデータ範囲では他のパッケージとの依存関係が観測されない（依存先が収集範囲外、または独立したパッケージ）。`);
    } else {
      texts.push(`構造上の特異性は検出されない（被依存 ${n.r_in}位・媒介 ${n.r_bt}位）。依存構造上は標準的な位置にあり、個別指標の確認で十分と考えられる。`);
    }
  }
  return `<div class="diag-name">${esc(n.label)}</div>${badges}${descHtml}${table}
    ${texts.map(t=>`<div class="diag-text">${t}</div>`).join("")}
    ${recos.length?`<div class="diag-reco">${recos.join("<br>")}</div>`:""}
    <div class="muted" style="margin-top:7px">解釈規則は、SNA 指標の標準的解釈（Chen et al. 2022 のレビューに整理されている）および
    依存ネットワーク研究の知見（Decan et al. 2019）に基づく（規則表は README を参照）。</div>`;
}
function diagnoseCom(cid, g){
  const st = (g.communities||[]).find(c=>c.id===cid);
  if (!st) return `<div class="hint">コミュニティ情報なし</div>`;
  const member = g.nodes.filter(n=>n.com===cid);
  const avgIn = member.length ? (member.reduce((a,n)=>a+n.indeg,0)/member.length).toFixed(1) : 0;
  return `<div class="diag-name">コミュニティ ${cid}</div>
    <span class="badge" style="background:${COLORS[cid%COLORS.length]}; color:#1F2D40">機能群</span>
    <table class="diag-table">
      <tr><td>ノード数</td><td>${st.n}</td></tr>
      <tr><td>内部エッジ数</td><td>${st.m_in}</td></tr>
      <tr><td>内部密度</td><td>${st.density}</td></tr>
      <tr><td>平均被依存数</td><td>${avgIn}</td></tr></table>
    <div class="diag-text"><b>代表ノード（PageRank 上位）:</b> ${st.top.map(esc).join("、")}</div>
    <div class="diag-text">コミュニティは依存が相対的に密な<b>機能群</b>に対応する。</div>
    <div class="diag-reco"><b>利用判断:</b> 代替候補はまず同一コミュニティ内から探索するのが有効。<b>集中リスク把握:</b> 障害が伝播しうる範囲の目安。</div>
    <div class="muted" style="margin-top:7px">解釈規則の根拠と規則表は README を参照。</div>`;
}

/* ---------- 適応レイアウト（決定論的・乱数不使用） ----------
   表示集合が変わるたびに、可視部分グラフへ Fruchterman–Reingold を再適用する。
   初期値 = 事前計算座標、反復回数固定、同値時の微小オフセットもインデックス由来
   → 同じ表示集合からは常に同じ配置（再現性を維持）。
   理想間距 k=√(1/n) により、ノード数が少ないほど自動的に広く展開される。
   成分ごとに計算し、最大成分を主領域・小成分を下部の帯に詰める（事前計算側と同方式）。 */
const layoutCache = new Map();
function frComponent(P, E, n){
  if (n > 1){
    const k = Math.sqrt(1.0/n);
    const iters = n > 400 ? 50 : 80;
    let t = 0.1; const dt = t/(iters+1);
    for (let it=0; it<iters; it++){
      const D = P.map(()=>[0,0]);
      for (let i=0;i<n;i++) for (let j=i+1;j<n;j++){
        let dx=P[i][0]-P[j][0], dy=P[i][1]-P[j][1];
        let d=Math.sqrt(dx*dx+dy*dy);
        if (d<0.01){ d=0.01; dx=0.01*((i+j)%2?1:-1); dy=0.005; }
        const f=(k*k)/(d*d);
        D[i][0]+=dx*f; D[i][1]+=dy*f; D[j][0]-=dx*f; D[j][1]-=dy*f;
      }
      for (const [i,j] of E){
        let dx=P[i][0]-P[j][0], dy=P[i][1]-P[j][1];
        let d=Math.sqrt(dx*dx+dy*dy); if (d<0.01) d=0.01;
        const c=d/k;
        D[i][0]-=dx*c; D[i][1]-=dy*c; D[j][0]+=dx*c; D[j][1]+=dy*c;
      }
      for (let i=0;i<n;i++){
        const dl=Math.sqrt(D[i][0]*D[i][0]+D[i][1]*D[i][1])||0.01;
        const st=Math.min(dl,t);
        P[i][0]+=D[i][0]/dl*st; P[i][1]+=D[i][1]/dl*st;
      }
      t-=dt;
    }
  }
  let mnx=Infinity,mny=Infinity,mxx=-Infinity,mxy=-Infinity;
  for (const p of P){ mnx=Math.min(mnx,p[0]); mny=Math.min(mny,p[1]); mxx=Math.max(mxx,p[0]); mxy=Math.max(mxy,p[1]); }
  const sx=(mxx-mnx)>1e-9?(mxx-mnx):1, sy=(mxy-mny)>1e-9?(mxy-mny):1;
  return P.map(p=>[(p[0]-mnx)/sx, (p[1]-mny)/sy]);
}
function layoutFor(g){
  const vis = visibleIds(g);
  const key = g.domain + "|" + (vis ? (topN + "|" + curM + "|" + catFilter) : "all");   // キーは g と全フィルタ状態から導出
  if (layoutCache.has(key)) return layoutCache.get(key);
  const nodes = vis ? g.nodes.filter(n=>vis.has(n.id)) : g.nodes;
  const idx = new Map(nodes.map((n,i)=>[n.id,i]));
  const N = nodes.length;
  const adj = Array.from({length:N},()=>[]);
  const E = [];
  for (const e of g.edges){
    const a=idx.get(e.s), b=idx.get(e.t);
    if (a===undefined||b===undefined||a===b) continue;
    adj[a].push(b); adj[b].push(a); E.push([a,b]);
  }
  // 連結成分（インデックス順 BFS・決定的）
  const comp = new Array(N).fill(-1); let nc=0;
  for (let s=0;s<N;s++){
    if (comp[s]>=0) continue;
    comp[s]=nc; const q=[s];
    while (q.length){ const c=q.pop(); for (const nb of adj[c]) if (comp[nb]<0){ comp[nb]=nc; q.push(nb); } }
    nc++;
  }
  const members = Array.from({length:nc},()=>[]);
  for (let i=0;i<N;i++) members[comp[i]].push(i);
  const order = members.map((m,ci)=>ci).sort((a,b)=> members[b].length-members[a].length || a-b);
  const laid = new Map();
  const place = (ci, rx, ry, rw, rh) => {
    const mem = members[ci];
    const local = new Map(mem.map((gi,i)=>[gi,i]));
    const P = mem.map((gi,i)=>[nodes[gi].x + 1e-5*(i+1), nodes[gi].y + 1e-5*((i*7)%13)]);
    const El = [];
    for (const [a,b] of E){ const i=local.get(a), j=local.get(b); if (i!==undefined&&j!==undefined) El.push([i,j]); }
    const Q = frComponent(P, El, mem.length);
    mem.forEach((gi,i)=> laid.set(nodes[gi].id, [rx+rw*Q[i][0], ry+rh*Q[i][1]]));
  };
  if (nc === 1){
    place(order[0], 0.02, 0.02, 0.96, 0.93);
  } else {
    place(order[0], 0.02, 0.02, 0.96, 0.78);     // 最大成分 = 上部主領域
    const rest = order.slice(1);
    const cell = 0.92/rest.length;
    rest.forEach((ci,i)=> place(ci, 0.04+cell*i, 0.875, cell*0.78, 0.105));  // 小成分 = 下部の帯
  }
  layoutCache.set(key, laid);
  return laid;
}

/* ---------- 配置（ピクセル座標・衝突緩和・Z オーダー） ----------
   クリック容易性のための 2 つの工夫（いずれも決定論的）:
   1) 衝突緩和: 重なったノード対を連結線方向に押し離す（指標値が大きい＝重要な
      ノードほど動かさない）。完全分離はせず 2/3 程度まで許容し、クラスタの
      まとまりは保つ。
   2) Z オーダー: 指標昇順に描画 → 重要なノードほど常に最前面でクリック可能。 */
const placeCache = new Map();
function placedFor(g){
  const vis = visibleIds(g);
  const key = g.domain + "|" + (vis ? (topN + "|" + catFilter) : "all") + "|" + curM;   // キーは g と全フィルタ状態から導出
  if (placeCache.has(key)) return placeCache.get(key);
  const laid = layoutFor(g);
  const mx = Math.max(...g.nodes.map(n=>n[curM])) || 1;
  const nVis = laid.size;
  const sizeK = nVis <= 60 ? 1.5 : nVis <= 120 ? 1.25 : 1.0;
  // 指標昇順の安定ソート（描画順 = Z オーダー: 高指標が最前面）
  const order = g.nodes.filter(n=>laid.has(n.id))
    .sort((a,b)=> a[curM]-b[curM] || (a.id<b.id?-1:1));
  const pts = order.map(n => {
    const p = laid.get(n.id);
    return { id:n.id, x:40+p[0]*920, y:30+p[1]*600, r:(4+13*Math.sqrt(n[curM]/mx))*sizeK };
  });
  // 衝突緩和（パス数固定・対の走査順固定 → 決定論的）
  const PAD = 1.5, PASSES = 8;
  for (let pass=0; pass<PASSES; pass++){
    let moved = false;
    for (let i=0;i<pts.length;i++) for (let j=i+1;j<pts.length;j++){
      const a=pts[i], b=pts[j];
      let dx=b.x-a.x, dy=b.y-a.y;
      let d=Math.sqrt(dx*dx+dy*dy);
      const min=(a.r+b.r)*0.66 + PAD;
      if (d >= min) continue;
      if (d < 0.01){ d=0.01; dx=((i+j)%2?1:-1)*0.01; dy=0.005; }
      const need=min-d, ux=dx/d, uy=dy/d;
      const sa=b.r/(a.r+b.r), sb=a.r/(a.r+b.r);   // 大きい（重要な）方ほど動かない
      a.x-=ux*need*sa; a.y-=uy*need*sa;
      b.x+=ux*need*sb; b.y+=uy*need*sb;
      moved = true;
    }
    if (!moved) break;
  }
  for (const p of pts){ p.x=Math.min(985,Math.max(15,p.x)); p.y=Math.min(648,Math.max(12,p.y)); }
  const out = { placed:new Map(pts.map(p=>[p.id,p])), order, sizeK };
  placeCache.set(key, out);
  return out;
}

/* ---------- 描画 ---------- */
function drawButtons(){
  $("#domains").innerHTML = Object.entries(DATA).map(([k,g]) =>
    `<button data-d="${k}" class="${k===curD?'on':''}">${g.label}</button>`).join(" ");
  $("#views").innerHTML =
    `<button data-v="net" class="${view==='net'?'on':''}">ネットワーク図</button> ` +
    `<button data-v="scatter" class="${view==='scatter'?'on':''}">散布図（被依存×媒介）</button>`;
  const dis = view==="scatter" ? " dis" : "";
  $("#metrics").innerHTML = Object.keys(MLAB).map(m =>
    `<button data-m="${m}" class="${m===curM&&!comMode?'on':''}${dis}">${MLAB[m].split("（")[0]}</button>`).join(" ");
  $("#comBtn").className = (comMode ? "on" : "") + dis;
  document.querySelectorAll("[data-d]").forEach(b => b.onclick = () => {
    curD=b.dataset.d; selected=null; selectedCom=null; topN=0; catFilter="";
    initSlider(); initSearch(); render(); });
  document.querySelectorAll("[data-v]").forEach(b => b.onclick = () => { view=b.dataset.v; render(); });
  document.querySelectorAll("[data-m]").forEach(b => b.onclick = () => { curM=b.dataset.m; comMode=false; selectedCom=null; render(); });
  $("#comBtn").onclick = () => { comMode=!comMode; if(!comMode) selectedCom=null; render(); };
}
function initSlider(){
  const g = DATA[curD], el = $("#topn");
  el.min = 10; el.step = 10;
  el.max = Math.ceil(g.nodes.length / 10) * 10;   // step 非整合のノード数でも「全表示」へ戻せるよう切り上げ
  el.value = topN && topN < g.nodes.length ? topN : el.max;
  el.oninput = () => { topN = (+el.value >= g.nodes.length) ? 0 : +el.value; render(); };
}
function sliderLabel(g){
  const vis = visibleIds(g);
  if (catFilter) $("#topnVal").textContent = `${vis ? vis.size : 0} ノード表示中`;
  else $("#topnVal").textContent = topN ? `上位 ${topN}/${g.nodes.length}` : `全 ${g.nodes.length} ノード`;
}
function initSearch(){
  const g = DATA[curD];
  $("#qlist").innerHTML = g.nodes.map(n=>`<option value="${esc(n.id)}">`).join("");
  $("#catSel").innerHTML = `<option value="">分類: すべて</option>` +
    (g.categories||[]).map(c=>`<option value="${esc(c.name)}"${c.name===catFilter?" selected":""}>${esc(c.name)}（${c.n}）</option>`).join("");
  $("#q").value = "";
}
$("#catSel").addEventListener("change", () => {
  catFilter = $("#catSel").value;
  if (catFilter){ comMode=false; selectedCom=null; }
  render();
});
$("#q").addEventListener("change", () => {
  const v = $("#q").value.trim().toLowerCase();
  if (!v) return;
  const g = DATA[curD];
  const hit = g.nodes.find(n=>n.id===v) || g.nodes.find(n=>n.id.includes(v));
  if (hit){
    catFilter=""; $("#catSel").value="";
    const vis = visibleIds(g);
    if (vis && !vis.has(hit.id)) topN = 0;
    comMode=false; selectedCom=null; selected=hit.id; view="net";
    initSlider(); render();
  }
});

function renderNet(g, byId){
  const vis = visibleIds(g);
  const shown = n => !vis || vis.has(n.id);
  const { placed, order } = placedFor(g);   // 適応レイアウト＋衝突緩和済みのピクセル座標
  const lx = id => placed.get(id).x;
  const ly = id => placed.get(id).y;
  const selNode = selected ? byId[selected] : null;
  const selShown = selNode && (!vis || vis.has(selNode.id));   // フィルタで非表示の選択はハイライト無効
  const cutSet = (selShown && selNode.art) ? new Set((g.cut_impact||{})[selected]||[]) : null;
  // フォーカス表示（エゴネットワーク）: 選択ノード＋直接の依存関係のみを残し、他は強く淡化。
  // 完全な非表示ではなく淡化（opacity 0.07）とするのは、全体地図の中での位置という文脈を保つため。
  // 切断点の場合もエゴを併存させ、「切断後に孤立する方向」のみ金色で強調し、
  // 残存側（主ネットワークへ向かう辺）はエゴの一部として青で表示する（黄線が全方向に出る誤解を防ぐ）。
  const ego = selShown
    ? (() => { const s = new Set(neighborsOf(g, selected)); s.add(selected); return s; })() : null;
  const focusCom = (comMode && selectedCom!=null) ? selectedCom : null;
  const mx = Math.max(...g.nodes.map(n=>n[curM])) || 1;
  $("#edges").innerHTML = g.edges.map(e => {
    const a=byId[e.s], b=byId[e.t]; if(!a||!b||!shown(a)||!shown(b)) return "";
    // inCut = 切断後に孤立する方向（切断点→孤立側、孤立側内部）。これだけを金色で示す。
    const inCut = cutSet && (cutSet.has(e.s)||e.s===selected) && (cutSet.has(e.t)||e.t===selected);
    const hot = selShown && !cutSet && (e.s===selected || e.t===selected);  // 通常エゴの中心辺（切断点では金線を出さない）
    const inCom = focusCom!=null && a.com===focusCom && b.com===focusCom;
    const inEgo = ego && ego.has(e.s) && ego.has(e.t);
    let stroke="#C9D8E8", w=0.7, op=0.55;
    if (inCut){ stroke="#E2A82E"; w=1.4; op=0.9; }
    else if (hot){ stroke="#E2A82E"; w=1.6; op=0.95; }
    else if (inCom){ stroke="#2C5F94"; w=1.1; op=0.85; }
    else if (ego){ op = inEgo ? 0.5 : 0.05; if (inEgo) stroke="#9DBBD6"; }  // 残存側を含むエゴ辺＝青
    else if (focusCom!=null){ op=0.18; }
    return `<line x1="${lx(e.s)}" y1="${ly(e.s)}" x2="${lx(e.t)}" y2="${ly(e.t)}"
      stroke="${stroke}" stroke-width="${w}" opacity="${op}"/>`;
  }).join("");
  // ノードの不透明度: 切断点では「切断点・孤立側・直接隣接（残存側）」をすべて表示し、無関係のみ淡化。
  const opOf = n => {
    if (cutSet) return (n.id===selected || cutSet.has(n.id) || (ego && ego.has(n.id))) ? 1 : 0.07;
    if (ego) return ego.has(n.id) ? 1 : 0.07;
    if (focusCom!=null && n.com!==focusCom) return 0.12;
    return 1;
  };
  $("#nodes").innerHTML = order.map(n => {   // 指標昇順に描画 → 高指標ノードが最前面でクリック可能
    const t = n[curM]/mx;
    const r = placed.get(n.id).r;
    let fill = comMode ? COLORS[n.com % COLORS.length] : colorOf(t);
    const op = opOf(n);
    if (cutSet){
      if (n.id===selected) fill="#E2A82E";
      else if (cutSet.has(n.id)) fill="#F2C84B";
    }
    const ring = n.art ? `<circle cx="${lx(n.id)}" cy="${ly(n.id)}" r="${r+3.5}" fill="none" stroke="#E2A82E" stroke-width="2.2" opacity="${op}"/>` : "";
    const sel = n.id===selected ? `<circle cx="${lx(n.id)}" cy="${ly(n.id)}" r="${r+7}" fill="none" stroke="#1F2D40" stroke-dasharray="3 3" stroke-width="1.5"/>` : "";
    const seedStroke = n.seed ? `stroke="#1F2D40" stroke-width="1.6"` : `stroke="#ffffff" stroke-width="0.8"`;
    return `${ring}${sel}<circle data-id="${n.id}" cx="${lx(n.id)}" cy="${ly(n.id)}" r="${r}" fill="${fill}" opacity="${op}" ${seedStroke} style="cursor:pointer"/>`;
  }).join("");
  const tops = g.nodes.filter(shown).sort((a,b)=>b[curM]-a[curM]).slice(0,12);
  $("#labels").innerHTML = tops.map(n =>
    `<text x="${lx(n.id)+8}" y="${ly(n.id)-7}" font-size="10.5" fill="#1F2D40" opacity="${opOf(n)}" paint-order="stroke" stroke="#ffffff" stroke-width="3">${esc(n.label)}</text>`).join("");
}

function renderScatter(g, byId){
  const vis = visibleIds(g);
  const shown = n => !vis || vis.has(n.id);
  const W=1000,H=660,L=80,R=40,T=40,B=70;
  const pts = g.nodes.filter(shown);
  const xmax = Math.max(...pts.map(n=>n.indeg), 1);
  const ymax = Math.max(...pts.map(n=>n.btw), 1e-6);
  const xs = v => L + (W-L-R) * Math.sqrt(v/xmax);
  const ys = v => H-B - (H-T-B) * Math.sqrt(v/ymax);
  const divIds = new Set((g.divergence||[]).map(d=>d.id));
  const fndIds = new Set((g.foundation||[]).map(d=>d.id));
  // 軸とグリッド（sqrt 標度。値は i/4 の二乗で決定的）
  let ax = `<line x1="${L}" y1="${H-B}" x2="${W-R}" y2="${H-B}" stroke="#9FB2C6" stroke-width="1"/>
            <line x1="${L}" y1="${T}" x2="${L}" y2="${H-B}" stroke="#9FB2C6" stroke-width="1"/>`;
  for (let i=1;i<=4;i++){
    const fx = xmax*(i/4)**2, fy = ymax*(i/4)**2;
    ax += `<line x1="${xs(fx)}" y1="${T}" x2="${xs(fx)}" y2="${H-B}" stroke="#E4ECF4" stroke-width="1"/>
           <text x="${xs(fx)}" y="${H-B+18}" font-size="10" fill="#5C6B7A" text-anchor="middle">${Math.round(fx)}</text>
           <line x1="${L}" y1="${ys(fy)}" x2="${W-R}" y2="${ys(fy)}" stroke="#E4ECF4" stroke-width="1"/>
           <text x="${L-8}" y="${ys(fy)+3}" font-size="10" fill="#5C6B7A" text-anchor="end">${fy.toFixed(4)}</text>`;
  }
  ax += `<text x="${(L+W-R)/2}" y="${H-B+40}" font-size="12" fill="#1F2D40" text-anchor="middle" font-weight="bold">被依存数（単純統計）→</text>
         <text x="22" y="${(T+H-B)/2}" font-size="12" fill="#1F2D40" text-anchor="middle" font-weight="bold" transform="rotate(-90 22 ${(T+H-B)/2})">媒介中心性（SNA）→</text>
         <text x="${L+14}" y="${T+18}" font-size="11.5" fill="#A8761A" font-weight="bold">← 左上 = 被依存は少ないが媒介が高い（単純統計では見えない要衝・RQ3）</text>`;
  $("#edges").innerHTML = ax;
  const drawOrder = [...pts].sort((a,b)=> a.btw-b.btw || (a.id<b.id?-1:1));   // 高媒介が最前面
  $("#nodes").innerHTML = drawOrder.map(n => {
    let fill="#A9C9E8", stroke="#ffffff", sw=0.8, r=5;
    if (divIds.has(n.id)){ fill="#F2C84B"; stroke="#A8761A"; sw=1.4; r=6.5; }
    else if (fndIds.has(n.id)){ fill="#2C5F94"; r=6.5; }
    const sel = n.id===selected ? `<circle cx="${xs(n.indeg)}" cy="${ys(n.btw)}" r="${r+6}" fill="none" stroke="#1F2D40" stroke-dasharray="3 3" stroke-width="1.5"/>` : "";
    return `${sel}<circle data-id="${n.id}" cx="${xs(n.indeg)}" cy="${ys(n.btw)}" r="${r}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}" style="cursor:pointer"/>`;
  }).join("");
  const lab = pts.filter(n=>divIds.has(n.id)).sort((a,b)=>a.r_bt-b.r_bt).slice(0,6)
    .concat(pts.sort((a,b)=>b.indeg-a.indeg).slice(0,3));
  $("#labels").innerHTML = lab.map(n =>
    `<text x="${xs(n.indeg)+8}" y="${ys(n.btw)-7}" font-size="10.5" fill="#1F2D40" paint-order="stroke" stroke="#ffffff" stroke-width="3">${esc(n.label)}</text>`).join("");
}

function renderSide(g, byId){
  const comActive = comMode && view==="net";   // 散布図ではコミュニティフォーカスを適用しない
  // 診断カード
  if (comActive && selectedCom!=null){
    $("#diag").innerHTML = diagnoseCom(selectedCom, g);
  } else if (selected && byId[selected]){
    $("#diag").innerHTML = diagnoseNode(byId[selected], g);
  } else {
    $("#diag").innerHTML = `<div class="hint">ノード（またはコミュニティ着色時のコミュニティ行）をクリックすると、
      指標データと「意思決定上何を意味するか」の診断を表示します。<br>
      診断はノード型 × 意思決定場面の対応表に基づく決定論的なルール＋テンプレートで生成（AI 不使用・再現可能）。</div>`;
  }
  // ランキング / コミュニティ一覧
  if (comActive){
    $("#rankTitle").textContent = "コミュニティ（クリックでフォーカス）";
    const cs = g.communities || [];
    $("#rankList").innerHTML = cs.slice(0,10).map(c =>
      `<div class="rank-row${selectedCom===c.id?' sel':''}" data-com="${c.id}">
        <span class="dot" style="background:${COLORS[c.id%COLORS.length]}"></span>
        <span class="nm">コミュニティ ${c.id} <span class="muted">(${esc(c.top[0]||"")}系)</span></span>
        <span class="bar-bg"><span class="bar-fg" style="width:${100*c.n/g.nodes.length}%"></span></span>
        <span class="val">${c.n}</span></div>`).join("");
    document.querySelectorAll(".rank-row[data-com]").forEach(r => r.onclick = () => {
      const cid = +r.dataset.com;
      selectedCom = (selectedCom===cid) ? null : cid; selected=null; render(); });
  } else {
    $("#rankTitle").textContent = (MLAB[curM]) + " — Top 10";
    const mx2 = Math.max(...g.nodes.map(n=>n[curM])) || 1;
    const rows = [...g.nodes].sort((a,b)=>b[curM]-a[curM]).slice(0,10);
    const eigNote = curM==="eig"
      ? `<div class="diag-cut" style="background:var(--warnbg);border-left:3px solid #F2C84B;margin:0 0 8px">
         <b>※ 参考値</b>: 依存ネットワークはほぼ非巡回（DAG）であり、固有ベクトル中心性の反復計算は
         依存の終端（sink）に値が集中して退化しやすい（順位が大きく断絶するのはこのため）。
         診断には次数・媒介・PageRank を用いる。<b>「この指標は依存ネットワーク向きではない」こと自体が RQ2 の知見</b>。</div>`
      : "";
    $("#rankList").innerHTML = eigNote + rows.map(n =>
      `<div class="rank-row${n.id===selected?' sel':''}" data-id="${n.id}">
        <span class="nm">${n.art?"⚠ ":""}${esc(n.label)}</span>
        <span class="bar-bg"><span class="bar-fg" style="width:${100*n[curM]/mx2}%"></span></span>
        <span class="val">${(+n[curM]).toLocaleString(undefined,{maximumFractionDigits:4})}</span></div>`).join("");
    document.querySelectorAll(".rank-row[data-id]").forEach(r => r.onclick = () => { selected=r.dataset.id; render(); });
  }
  // 乖離パネル
  const dv = (g.divergence||[]).slice(0,6);
  const fd = (g.foundation||[]).slice(0,3);
  $("#divList").innerHTML =
    (dv.length ? dv.map(d =>
      `<div class="div-row" data-id="${d.id}"><b>${esc(d.id)}</b> — 被依存 ${d.rank_indeg}位 → 媒介 <b>${d.rank_btw}位</b>
       <span class="muted">(indeg=${d.indeg}, btw=${d.btw}) 橋渡し型</span></div>`).join("") :
      `<div class="muted">この領域では顕著な乖離ノードなし</div>`) +
    fd.map(d =>
      `<div class="div-row" data-id="${d.id}" style="border-left-color:#2C5F94; background:#EAF4FF"><b style="color:#2C5F94">${esc(d.id)}</b>
       — 被依存 ${d.rank_indeg}位・影響範囲 ${d.impact}
       <span class="muted">土台型（単純統計でも見える）</span></div>`).join("");
  document.querySelectorAll(".div-row[data-id]").forEach(r => r.onclick = () => { selected=r.dataset.id; comMode=false; selectedCom=null; render(); });
  const sp = g.spearman||{};
  $("#spearman").textContent =
    `Spearman ρ: 被依存×媒介=${sp.indeg_vs_btw} ／ ×PageRank=${sp.indeg_vs_pagerank} ／ ×固有ベクトル=${sp.indeg_vs_eigenvector}（1.0 から離れるほど SNA 独自の情報が多い）`;
}

function render(){
  const g = DATA[curD], byId = Object.fromEntries(g.nodes.map(n=>[n.id,n]));
  drawButtons();
  sliderLabel(g);
  if (view === "scatter") renderScatter(g, byId); else renderNet(g, byId);
  renderSide(g, byId);
  // メタ情報
  const c=g.collect||{}, rp=g.repro||{};
  $("#meta").innerHTML =
    `<b>再現性情報（${g.label}）</b> — 取得日: ${(c.fetched_dates||[]).join(", ")||"—"} ／ データソース: deps.dev API v3 ／ ` +
    `シード成功率: ${c.n_seeds_ok??"—"}/${(c.n_seeds_ok??0)+(c.n_seeds_failed??0)} (${((c.success_rate??0)*100).toFixed(1)}%) ／ ` +
    `規模: ${g.n} ノード・${g.m} エッジ ／ 密度 ${g.density} ／ 弱連結成分 ${g.n_components} ／ ` +
    `モジュラリティ ${g.modularity}（コミュニティ ${g.n_communities}）<br>` +
    `乱数 seed=${rp.random_seed}（レイアウト・コミュニティ検出に使用） ／ 指標処理時間: ` +
    `媒介 ${rp.durations_sec?.betweenness}s・全体 ${rp.durations_sec?.total}s ／ 生成日時: ${g.generated_at}<br>` +
    `診断は決定論的ルールにより生成（AI 不使用） ／ 表示レイアウトは表示集合に応じて決定論的に再計算（初期値＝事前計算座標・反復固定・乱数不使用）`;
  // ツールチップ + クリック
  const tip = $("#tip");
  document.querySelectorAll("circle[data-id]").forEach(cc => {
    cc.onmousemove = ev => {
      const n = byId[cc.dataset.id];
      tip.innerHTML = `<b>${esc(n.label)}</b>${n.seed?" 🌱シード":""}${n.art?" ⚠切断点":""}<br>` +
        (n.desc?`<span style="color:#5C6B7A;font-style:italic">${esc(n.desc.slice(0,70))}${n.desc.length>70?"…":""}</span><br>`:"") +
        `分類: ${esc(n.cat||"—")} ／ コミュニティ ${n.com}<br>` +
        `被依存 ${n.indeg}（${n.r_in}位） ／ 依存先 ${n.outdeg} ／ 影響範囲 ${n.impact}<br>` +
        `媒介 ${n.btw}（${n.r_bt}位） — クリックで診断とフォーカス表示`;
      tip.style.display="block";
      // 内容を設定してから寸法を測り、ステージ端で反転させる（右端・下端での潰れ防止）
      const cw = tip.parentElement.clientWidth, ch = tip.parentElement.clientHeight;
      const tw = tip.offsetWidth, th = tip.offsetHeight;
      let lx = ev.offsetX + 16, ty = ev.offsetY + 12;
      if (lx + tw > cw - 4) lx = ev.offsetX - tw - 16;   // 右にはみ出すなら左側へ
      if (ty + th > ch - 4) ty = ev.offsetY - th - 12;   // 下にはみ出すなら上側へ
      tip.style.left = Math.max(4, lx) + "px";
      tip.style.top  = Math.max(4, ty) + "px";
    };
    cc.onmouseleave = () => tip.style.display="none";
    cc.onclick = () => {
      const id = cc.dataset.id;
      if (comMode && view==="net"){ selectedCom = (selectedCom===byId[id].com)?null:byId[id].com; selected=null; }
      else { selected = id===selected ? null : id; selectedCom = null; }
      render();
    };
  });
}
initSlider();
initSearch();
render();
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", nargs="+", required=True, help="*_metrics.json（複数可）")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    data = {}
    for p in args.inputs:
        d = json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
        data[d["domain"]] = d
    html = TEMPLATE.replace("__DATA_JSON__", json.dumps(data, ensure_ascii=False))
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"-> {out} ({out.stat().st_size//1024} KB, 領域: {list(data)})")


if __name__ == "__main__":
    main()
