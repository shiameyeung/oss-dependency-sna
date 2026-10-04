# -*- coding: utf-8 -*-
"""
make_demo.py — 分析結果 JSON を埋め込んだ自己完結型 HTML デモを生成する

特徴:
  - 単一ファイル・外部 CDN 依存なし（オフライン環境でも動作）
  - 配色は一貫したパレット（クリーム地・青・キャンディイエロー）を使用
  - 領域切替（PyPI / Go）、指標切替、コミュニティ着色、Top10 ランキング、切断点 ⚠ 表示
  - 【DSS 機能】診断カード: ノードクリックで「指標データ＋これは何を意味するか＋推奨」を表示。
    生成は AI ではなく決定論的なルール＋テンプレート（ノード型 × 意思決定場面の対応表）。
    型判定条件: 切断点 = art フラグ ／ 橋渡し型 = btw>0 かつ 被依存順位−媒介順位 ≥ 5 ／
    土台型 = 被依存上位 10 位以内 かつ btw≈0 かつ indeg≥3 ／ 孤立 = indeg=outdeg=0 ／ 他は標準。
  - 【DSS 機能】切断点クリックで「その点を除くと孤立する範囲」をハイライト（cut_impact を事前計算）
  - 【DSS 機能】散布図ビュー: 被依存数 × 媒介中心性。順位乖離が一枚で見える
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
<title>OSS 依存ネットワーク分析</title>
<style>
  /* 配色: クリーム地・青・キャンディイエロー */
  :root { --bg:#FFFDF5; --panel:#ffffff; --panel2:#EAF4FF; --txt:#1F2D40; --sub:#5C6B7A;
          --acc:#2C5F94; --acc2:#5DA8E8; --warn:#E2A82E; --warnbg:#FFF8D6; --line:#DCE6F2; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--txt);
         font-family:"Yu Gothic","Hiragino Kaku Gothic ProN","Noto Sans JP",sans-serif; }
  header { padding:14px 20px 10px; border-bottom:1px solid var(--line); position:relative; }
  #langbar { position:absolute; top:12px; right:18px; display:flex; align-items:center; gap:7px; }
  #langbar .globe { font-size:15px; opacity:.65; }
  #langbar button { padding:3px 9px; font-size:11.5px; border-radius:5px; }
  h1 { font-size:17px; margin:0 0 6px; font-weight:700; color:var(--acc); }
  .sub { color:var(--sub); font-size:12px; }
  .hintbar { display:flex; flex-wrap:wrap; gap:4px 16px; padding:5px 0 1px; }
  .hint-item { display:inline-flex; align-items:center; gap:5px; color:var(--sub);
               font-size:11.5px; line-height:1.35; white-space:nowrap; }
  .hint-item svg { flex:none; display:block; height:14px; width:auto; }  /* 全体の svg{height:660px} を上書き */
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
  svg { width:100%; height:660px; display:block; cursor:grab; touch-action:none; }
  svg:active { cursor:grabbing; }
  #zoomReset { position:absolute; right:10px; bottom:10px; z-index:6; width:30px; height:30px;
               padding:0; font-size:16px; line-height:1; border-radius:7px; background:#ffffffdd; }
  .extlink { color:var(--acc); text-decoration:underline; cursor:pointer; }
  .extlink:hover { color:var(--acc2); }
  svg text { pointer-events:none; }  /* ラベルがノードのクリックを遮らないように */
  svg circle[fill="none"] { pointer-events:none; }  /* 装飾リング（切断点/選択）がクリックを奪わないように */
  .side { display:flex; flex-direction:column; gap:12px; max-height:660px; overflow-y:auto; }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:12px 14px; }
  .card h2 { font-size:13px; margin:0 0 8px; color:var(--acc); font-weight:700; }
  .badge { display:inline-block; font-size:11px; font-weight:700; color:#fff; border-radius:4px;
           padding:2px 8px; margin:0 4px 6px 0; cursor:help; position:relative; }
  /* 即時表示のツールチップ（ネイティブ title の遅延を避ける） */
  button[data-tip] { position:relative; }
  [data-tip]:hover::after {
    content: attr(data-tip); position:absolute; left:0; top:calc(100% + 4px);
    background:#1F2D40; color:#fff; font-size:11px; font-weight:400; line-height:1.45;
    padding:6px 9px; border-radius:6px; width:max-content; max-width:230px; white-space:normal;
    z-index:30; box-shadow:0 3px 12px rgba(31,45,64,.25); pointer-events:none; }
  .nodelink { color:var(--acc); cursor:pointer; border-bottom:1px dotted var(--acc2); word-break:break-all; }
  .nodelink:hover { color:var(--acc2); background:var(--panel2); }
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

  /* 発表時にも読める配置。操作・図・選択結果を同じ画面に収める。 */
  :root { --bg:#F5F7FA; --line:#DFE6EE; --sub:#586A7E; }
  header { background:#fff; padding:18px 24px 12px; }
  h1 { font-size:21px; letter-spacing:.01em; padding-right:270px; }
  #h1sub { display:block; margin-top:5px; font-size:13px; font-weight:400; }
  #langbar { top:20px; right:24px; }
  .hintbar { margin-top:10px; gap:8px 18px; }
  .hint-item { font-size:12px; }
  .bar { padding:14px 24px; gap:10px; display:grid; grid-template-columns:1.2fr 1fr 1fr; }
  .grp { border:0; padding:0; background:none; min-width:0; flex-wrap:wrap; gap:6px; }
  .grp:nth-child(1) { grid-column:1; grid-row:1; }
  .grp:nth-child(2) { grid-column:2; grid-row:1; }
  .grp:nth-child(5) { grid-column:3; grid-row:1; justify-content:flex-end; }
  .grp:nth-child(3) { grid-column:1 / 3; grid-row:2; }
  .grp:nth-child(4) { grid-column:3; grid-row:2; justify-content:flex-end; }
  .grp .lbl { font-size:11px; letter-spacing:0; margin-right:3px; }
  #domains, #views, #metrics { display:inline-flex; gap:3px; flex-wrap:wrap; }
  button { font-family:inherit; background:#fff; border-color:var(--line); padding:7px 10px; font-size:12px; min-height:34px; }
  button.on { border-color:var(--acc); box-shadow:0 2px 5px #2C5F9414; }
  button:focus-visible, input:focus-visible, select:focus-visible, [role=button]:focus-visible, summary:focus-visible { outline:3px solid #5DA8E8; outline-offset:3px; }
  #q { width:132px; font-size:12px; min-height:34px; background:#fff; }
  #catSel { max-width:150px; min-height:34px; background:#fff; }
  .sliderbox input { width:100px; }
  main { padding:0 24px; grid-template-columns:minmax(0,1fr) 350px; gap:16px; }
  .stage { overflow:hidden; border-radius:12px; }
  #svg { height:clamp(400px,calc(100vh - 265px),620px); }
  .side { scrollbar-gutter:stable; max-height:clamp(400px,calc(100vh - 265px),620px); gap:12px; scrollbar-width:thin; }
  .card { border-radius:12px; padding:16px; }
  .card h2 { font-size:14px; margin-bottom:12px; }
  .diag-name { font-size:19px; margin:0 0 8px; overflow-wrap:anywhere; }
  .diag-purpose { margin:10px 0 12px; padding:12px; background:#EDF4FB; border-left:3px solid var(--acc); border-radius:4px; }
  .diag-purpose h3 { margin:0 0 6px; font-size:14px; color:var(--acc); }
  .diag-desc { margin:0; color:var(--txt); font-size:15px; font-style:normal; line-height:1.65; overflow-wrap:anywhere; }
  .diag-table { font-size:12px; margin:10px 0; }
  .diag-table td { padding:5px 0; }
  .diag-table td:last-child { text-align:right; font-variant-numeric:tabular-nums; }
  .diag-text, .diag-reco { font-size:12px; line-height:1.7; }
  .diag-cut { padding:9px; }
  .hint { font-size:13px; line-height:1.9; }
  .rank-row { padding:6px 2px; }
  .rank-row .nm { flex:1; min-width:0; }
  .bar-bg { display:block; }
  .bar-fg { display:block; }
  .rank-row .bar-bg { flex:0 0 52px; }
  #zoomReset { width:auto; height:34px; padding:0 10px; font-size:12px; border-color:var(--line); }
  .divband { margin:16px 24px 0; padding:16px; border-radius:12px; }
  .divband h2 { font-size:15px; }
  .div-row { line-height:1.7; padding:10px; overflow-wrap:anywhere; }
  .div-row:hover { outline:1px solid var(--warn); }
  .legend { padding:12px 24px 0; }
  footer { padding:12px 24px 20px; }
  .method-detail { border-top:1px solid var(--line); padding-top:9px; margin-top:10px; font-size:11px; line-height:1.6; color:var(--sub); }
  .method-detail summary { cursor:pointer; color:var(--acc); font-size:12px; }
  @media(max-width:1100px) {
    .bar { grid-template-columns:1fr 1fr; }
    .grp:nth-child(5) { grid-column:2; grid-row:3; }
    .grp:nth-child(3) { grid-column:1 / 3; grid-row:2; }
    .grp:nth-child(4) { grid-column:1; grid-row:3; justify-content:flex-start; }
    h1 { font-size:18px; }
  }
  @media(max-width:760px) {
    header { padding:16px; } h1 { padding-right:0; } #langbar { position:static; justify-content:flex-end; margin-bottom:10px; }
    .bar { display:flex; padding:12px 16px; } .grp { width:100%; justify-content:flex-start!important; }
    main { grid-template-columns:1fr; padding:0 16px; } .side { max-height:none; }
    #svg { height:400px; } .divband { margin:16px; } #divList { grid-template-columns:1fr; }
  }

  /* Portfolio navigation is separate from the research controls. */
  .portfolio-header { position:sticky;top:0;z-index:80;background:#fbf9f6ed;backdrop-filter:blur(18px);border-bottom:1px solid #e7e0d9;color:#23201f; }
  .portfolio-nav-inner { max-width:1120px;min-height:64px;padding:0 24px;margin:auto;display:flex;align-items:center;justify-content:space-between;gap:24px; }
  .portfolio-brand { display:inline-flex;align-items:center;gap:10px;color:inherit;text-decoration:none;font:700 15px "Helvetica Neue",Arial,sans-serif;letter-spacing:.12em;white-space:nowrap; }
  .portfolio-brand img { width:44px;height:44px;object-fit:contain; }
  .portfolio-links { display:flex;align-items:center;gap:26px; }
  .portfolio-links a { font-size:13px;color:#6f6763;text-decoration:none;padding:19px 0;white-space:nowrap; }
  .portfolio-links a:hover { color:#23201f;text-decoration:underline;text-underline-offset:5px; }
  .portfolio-header a:focus-visible { outline:3px solid #5a8879;outline-offset:4px; }
  @media(max-width:760px) { .portfolio-nav-inner { padding:8px 16px;gap:4px;flex-wrap:wrap; }.portfolio-brand { font-size:13px; }.portfolio-brand img { width:32px;height:32px; }.portfolio-links { flex-basis:100%;justify-content:space-between;gap:10px; }.portfolio-links a { font-size:12px;padding:8px 0; } }
  @media print { .portfolio-header { display:none; } }
</style>
</head>
<body>
<nav class="portfolio-header" id="portfolio-header"><div class="portfolio-nav-inner"><a class="portfolio-brand" id="portfolio-home" href="https://yotenra.com"><img src="data:image/png;base64,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" width="44" height="44" alt=""><span>YO TENRA</span></a><div class="portfolio-links" id="portfolio-links"></div></div></nav>
<header>
  <div id="langbar"><span class="globe" aria-hidden="true">🌐</span><span id="langs"></span></div>
  <h1><span id="h1main"></span> <span class="sub" id="h1sub"></span></h1>
  <div class="hintbar" id="hintbar"></div>
</header>
<div class="bar">
  <div class="grp"><span class="lbl" id="lblDomain"></span><span id="domains"></span></div>
  <div class="grp"><span class="lbl" id="lblView"></span><span id="views"></span></div>
  <div class="grp"><span class="lbl" id="lblMetric"></span><span id="metrics"></span>
    <button id="comBtn"></button></div>
  <div class="grp"><span class="lbl" id="lblSearch"></span>
    <input type="text" id="q" list="qlist">
    <datalist id="qlist"></datalist>
    <select id="catSel"></select></div>
  <div class="grp"><span class="lbl" id="lblTopn"></span>
    <span class="sliderbox"><input type="range" id="topn" min="10" max="300" step="10">
    <span class="val" id="topnVal"></span></span></div>
</div>
<main>
  <div class="stage">
    <svg id="svg" viewBox="0 0 1000 660" xmlns="http://www.w3.org/2000/svg">
      <g id="viewport">
        <g id="edges"></g><g id="nodes"></g><g id="labels"></g>
      </g>
    </svg>
    <button id="zoomReset">⟲</button>
    <div id="tip"></div>
  </div>
  <div class="side">
    <div class="card">
      <h2 id="diagTitle"></h2>
      <div id="diag"></div>
    </div>
    <div class="card">
      <h2 id="rankTitle">Top 10</h2>
      <div id="rankList"></div>
    </div>
  </div>
</main>
<div class="divband">
  <h2 id="divTitle"></h2>
  <div id="divList"></div>
  <div class="muted" id="spearman" style="margin-top:8px"></div>
</div>
<div class="legend">
  <span><span class="dot" style="background:#5DA8E8"></span><span id="legNormal"></span></span>
  <span><span class="dot" style="background:#5DA8E8; outline:2px solid #1F2D40"></span><span id="legSeed"></span></span>
  <span><span class="dot" style="background:transparent; border:2.5px solid var(--warn)"></span><span id="legCut"></span></span>
  <span><span class="dot" style="background:#F2C84B"></span><span id="legIso"></span></span>
</div>
<footer id="meta"></footer>
<script>
const DATA = __DATA_JSON__;
const requestedLanguage = new URLSearchParams(location.search).get("lang");
let lang = ({zh:"zhHans", "zh-Hans":"zhHans", "zh-Hant":"zhHant"})[requestedLanguage] || (["ja","en","zhHant","zhHans"].includes(requestedLanguage) ? requestedLanguage : "ja");   // 表示言語（ja / en）。データ・指標値は不変、表示文字列のみ切替。
const COLORS = ["#5DA8E8","#F2C84B","#81c784","#ba68c8","#ff8a65","#4dd0e1","#f06292","#a1887f","#90a4ae","#dce775"];
const LANGS = [["ja","日本語"],["en","English"],["zhHant","繁體"],["zhHans","简体"]];
const HTMLLANG = {ja:"ja", en:"en", zhHant:"zh-Hant", zhHans:"zh-Hans"};
// ヘッダの凡例（読み方・操作）— アイコンは言語非依存。文言は STR.headerHint[キー]。
const HINT_ORDER = ["edge","size","cut","click","zoom"];
const HINT_ICONS = {
  edge:'<svg width="21" height="13" viewBox="0 0 21 13" aria-hidden="true"><circle cx="3" cy="6.5" r="2.6" fill="#5DA8E8"/><line x1="6.2" y1="6.5" x2="14" y2="6.5" stroke="#9DB2C6" stroke-width="1.4"/><path d="M13 4L16.5 6.5L13 9" fill="none" stroke="#9DB2C6" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  size:'<svg width="23" height="13" viewBox="0 0 23 13" aria-hidden="true"><circle cx="4" cy="6.5" r="2.2" fill="#CFE6FF"/><circle cx="15" cy="6.5" r="5" fill="#5DA8E8"/></svg>',
  cut:'<svg width="14" height="13" viewBox="0 0 14 13" aria-hidden="true"><circle cx="7" cy="6.5" r="4.4" fill="none" stroke="#E2A82E" stroke-width="2"/></svg>',
  click:'<svg width="13" height="13" viewBox="0 0 13 13" aria-hidden="true"><path d="M2.5 1.5L2.5 10.5L4.8 8.3L6.6 12L8 11.3L6.2 7.7L9.3 7.7Z" fill="#5C6B7A"/></svg>',
  zoom:'<svg width="14" height="13" viewBox="0 0 14 13" aria-hidden="true"><circle cx="5.5" cy="5.5" r="3.5" fill="none" stroke="#5C6B7A" stroke-width="1.5"/><line x1="8.1" y1="8.1" x2="11.5" y2="11.5" stroke="#5C6B7A" stroke-width="1.5" stroke-linecap="round"/></svg>',
};
const MLAB = {
  indeg:{ja:"被依存数（直接依存元の数・単純統計）", en:"In-degree (direct dependents · simple stat)",
         zhHant:"被依賴數（直接依賴者數·簡單統計）", zhHans:"被依赖数（直接依赖者数·简单统计）"},
  impact:{ja:"影響範囲（推移的に波及する依存元数）", en:"Reach (transitively affected dependents)",
          zhHant:"影響範圍（遞移波及的依賴者數）", zhHans:"影响范围（传递波及的依赖者数）"},
  btw:{ja:"媒介中心性（橋渡し・経路上の要）", en:"Betweenness (bridge · path bottleneck)",
       zhHant:"中介中心性（橋接·路徑要衝）", zhHans:"中介中心性（桥接·路径要冲）"},
  pr:{ja:"PageRank（構造的重要度）", en:"PageRank (structural importance)",
      zhHant:"PageRank（結構重要度）", zhHans:"PageRank（结构重要度）"},
  eig:{ja:"固有ベクトル中心性（重要ノードから依存される度合い）", en:"Eigenvector centrality (importance from important nodes)",
       zhHant:"特徵向量中心性（來自重要節點的被依賴度）", zhHans:"特征向量中心性（来自重要节点的被依赖度）"},
};
function mlab(m){ return MLAB[m][lang]; }
function mshort(m){ return mlab(m).split(lang==="en" ? " (" : "（")[0]; }
const TYPE_INFO = {
  cutpoint:   {color:"#E2A82E", ja:"切断点",   en:"Cut point",  zhHant:"切斷點", zhHans:"切断点"},
  bridge:     {color:"#A8761A", ja:"橋渡し型", en:"Bridge",     zhHant:"橋接型", zhHans:"桥接型"},
  foundation: {color:"#2C5F94", ja:"土台型",   en:"Foundation", zhHant:"基礎型", zhHans:"基础型"},
  isolated:   {color:"#5C6B7A", ja:"孤立",     en:"Isolated",   zhHant:"孤立",   zhHans:"孤立"},
  normal:     {color:"#5C6B7A", ja:"標準",     en:"Standard",   zhHant:"標準",   zhHans:"标准"},
};
const DOMAIN_I18N = {
  ds:{en:"Data science (PyPI)", zhHant:"資料科學類（PyPI）", zhHans:"数据科学系（PyPI）"},
  cn:{en:"Cloud native (Go)",   zhHant:"雲原生類（Go）",     zhHans:"云原生系（Go）"},
};
function domLabel(g){ return lang==="ja" ? g.label : ((DOMAIN_I18N[g.domain]||{})[lang] || g.label); }
// 機能分類名の多言語対応（分類キーは日本語のまま・表示のみ翻訳）
const CAT_I18N = {
  "Jupyter・開発環境":{en:"Jupyter & dev tools", zhHant:"Jupyter·開發環境", zhHans:"Jupyter·开发环境"},
  "機械学習":{en:"Machine learning", zhHant:"機器學習", zhHans:"机器学习"},
  "統計・時系列":{en:"Statistics & time series", zhHant:"統計·時間序列", zhHans:"统计·时间序列"},
  "可視化":{en:"Visualization", zhHant:"視覺化", zhHans:"可视化"},
  "自然言語処理":{en:"NLP", zhHant:"自然語言處理", zhHans:"自然语言处理"},
  "データ処理・数値計算":{en:"Data & numerics", zhHant:"資料處理·數值計算", zhHans:"数据处理·数值计算"},
  "Web・通信":{en:"Web & networking", zhHant:"Web·通訊", zhHans:"Web·通信"},
  "基盤・ユーティリティ":{en:"Core & utilities", zhHant:"基礎·工具", zhHans:"基础·工具"},
  "Kubernetes 関連":{en:"Kubernetes", zhHant:"Kubernetes 相關", zhHans:"Kubernetes 相关"},
  "可観測性・監視":{en:"Observability", zhHant:"可觀測性·監控", zhHans:"可观测性·监控"},
  "ネットワーク・メッシュ":{en:"Networking & mesh", zhHant:"網路·服務網格", zhHans:"网络·服务网格"},
  "ストレージ・データベース":{en:"Storage & database", zhHant:"儲存·資料庫", zhHans:"存储·数据库"},
  "コンテナ・デプロイ":{en:"Container & deploy", zhHant:"容器·部署", zhHans:"容器·部署"},
  "クラウド SDK":{en:"Cloud SDK", zhHant:"雲端 SDK", zhHans:"云 SDK"},
  "開発・テスト":{en:"Dev & testing", zhHant:"開發·測試", zhHans:"开发·测试"},
  "基盤ライブラリ":{en:"Core libraries", zhHant:"基礎函式庫", zhHans:"基础库"},
};
function catLabel(name){ return lang==="ja" ? name : ((CAT_I18N[name]||{})[lang] || name); }
// 用途の平易な説明を優先する。未整備の項目は保存済みの説明文に戻す。
function descOf(n){ return n.purpose?.[lang] || (lang==="ja" ? (n.desc_ja || n.desc_en || "") : (n.desc_en || n.desc_ja || "")); }
const PURPOSE_LABEL={ja:"何に使うもの？",en:"What is it used for?",zhHant:"這個軟體用來做什麼？",zhHans:"这个软件用来做什么？"};
const PURPOSE_MISSING={ja:"用途の説明はまだ確認できていません。",en:"A description of its purpose is not available yet.",zhHant:"尚未確認這個軟體的用途說明。",zhHans:"尚未确认这个软件的用途说明。"};

// UI 文字列・診断テンプレート（日/英）。データ準備段階で固定（実行時 LLM 不使用）。
const STR = {
 ja: {
  h1main:"OSS 依存ネットワーク分析",
  h1sub:"依存関係を可視化し、詳しく確認するパッケージを探す",
  headerHint:{edge:"依存元 → 依存先", size:"大きさ・色 = 選択中の指標", cut:"金色の輪 = 切断点", click:"点を選ぶと詳細を表示", zoom:"ホイールで拡大・ドラッグで移動"},
  gDomain:"領域", gView:"表示", gMetric:"指標", gSearch:"検索・分類", gTopn:"表示数", gLang:"言語",
  comBtn:"コミュニティ着色", comBtnTitle:"Louvain 法で検出したコミュニティごとに着色", zoomResetTitle:"図の位置を戻す",
  vNet:"ネットワーク図", vScatter:"散布図",
  qPlaceholder:"名前で検索…", catAll:"分類: すべて",
  diagTitle:"選択したパッケージ",
  diagHint:'図の点やランキングの名前を選ぶと、依存関係と指標を確認できます。<br><br>名前がわかる場合は検索欄に入力し、Enter キーで選択できます。<br><br>図の余白をクリックすると全体表示に戻ります。',
  divTitle:'指標による順位の違い — 名前を選んで確認',
  legNormal:"通常ノード", legSeed:"シード（分析起点）", legCut:"切断点 ⚠（クリックで孤立する範囲を表示）", legIso:"切断時に孤立する範囲",
  rankComTitle:"コミュニティ（クリックでフォーカス）",
  rankTopSuffix:" — Top 10",
  topnAll:n=>`全 ${n} ノード`, topnTop:(k,n)=>`上位 ${k}/${n}`, catCount:n=>`${n} ノード表示中`,
  seedBadge:"シード", funcGroup:"機能群", systemSuffix:"系",
  badgeTip:{cutpoint:"切断点: 取り除くと他のノードが主要ネットワークから孤立する急所",bridge:"橋渡し型: 被依存数は低いが媒介中心性が高い、経路上の要衝",foundation:"土台型: 多数が直接依存する基盤（被依存数が上位）",isolated:"孤立: 収集範囲内に依存関係が観測されないノード",normal:"標準: 構造上の特異性が検出されないノード",seed:"シード: 分析の起点として選んだパッケージ",cat:"機能分類: 名前・説明に基づく決定論的な分類"},
  tIndeg:"被依存数（単純統計）", tIndegVal:(v,N,r)=>`${v}（全 ${N} 中 ${r}位）`,
  tReach:"影響範囲（推移的）", tReachVal:v=>`${v} パッケージ`,
  tBtw:"媒介中心性", tBtwVal:(v,r)=>`${v}（${r}位）`, tPr:"PageRank", tCom:"コミュニティ",
  cutMain:cl=>`この点をグラフから除くと、<b>${cl} パッケージ</b>が主要なつながりから分かれます。該当する範囲を図中に黄色で表示しています。`,
  cutList:(head,more)=>`<div class="diag-cut"><b>孤立する範囲:</b> ${head}${more?` 他 ${more} 件`:""}</div>`,
  cutReco:"<b>確認の手がかり:</b> この点を介してつながる範囲を表示しています。実際の障害や影響の大きさを示すものではありません。",
  bridgeMain:(rin,rbt,gap)=>`被依存数は <b>${rin}位</b>、媒介中心性は <b>${rbt}位</b>です。直接依存される数に比べ、依存経路を橋渡しする位置が目立ちます。`,
  bridgeReco:"<b>確認の手がかり:</b> 被依存数だけでは上位に現れにくい候補です。利用・支援の判断には保守状況などの確認が必要です。",
  foundMain:(indeg,rin,impact,N)=>`被依存数は <b>${indeg} 件（${rin}位）</b>です。依存関係をたどると、${impact} パッケージから到達できます。`,
  foundReco:"<b>確認の手がかり:</b> 収集した範囲で多くのパッケージが依存しています。採用の適否や安全性は別途確認が必要です。",
  isoMain:"このデータ範囲では他のパッケージとの依存関係が観測されない（依存先が収集範囲外、または独立したパッケージ）。",
  normMain:(rin,rbt)=>`被依存数は ${rin}位、媒介中心性は ${rbt}位です。本システムの分類条件には該当していません。`,
  evidence:'指標とルールに基づく確認候補の提示です。判断への有用性を実証したものではありません。対象範囲・取得時点に依存します。分類規則は README を参照。',
  comTitle:cid=>`コミュニティ ${cid}`, comNodes:"ノード数", comInEdges:"内部エッジ数", comDensity:"内部密度", comAvgIn:"平均被依存数",
  comTop:"<b>代表ノード（PageRank 上位）:</b> ",
  comDesc:"コミュニティは、依存関係が相対的に密な<b>ノードのまとまり</b>です。",
  comReco:"<b>確認の手がかり:</b> まとまりの中の依存関係を確認できます。同じ機能や代替可能性を意味するものではありません。",
  comEvidence:"解釈規則の根拠と規則表は README を参照。", comNone:"コミュニティ情報なし",
  eigNote:'<b>※ 参考値</b>: 依存ネットワークはほぼ非巡回（ループのない一方向の構造・DAG）であり、固有ベクトル中心性の反復計算は依存の終端（外向きの依存を持たない「行き止まり」のノード）に値が集中し、うまく順位が付かなくなりやすい（順位が大きく断絶するのはこのため）。診断には被依存数・媒介・PageRank を用いる。<b>「この指標は依存ネットワーク向きではない」こと自体も、本分析で得られた知見の一つである</b>。',
  spearman:sp=>`順位の一致度（Spearman 順位相関 ρ）— 被依存×媒介=${sp.indeg_vs_btw} ／ ×PageRank=${sp.indeg_vs_pagerank} ／ ×固有ベクトル=${sp.indeg_vs_eigenvector}（1 に近いほど順位が一致）`,
  divBridge:(id,rin,rbt,indeg,btw)=>`<b>${id}</b> — 被依存 ${rin}位 → 媒介 <b>${rbt}位</b> <span class="muted">(被依存 ${indeg}・媒介 ${btw}) 橋渡し型</span>`,
  divFound:(id,rin,impact)=>`<b style="color:#2C5F94">${id}</b> — 被依存 ${rin}位・影響範囲 ${impact} <span class="muted">土台型（単純統計でも見える）</span>`,
  divNone:"この領域では顕著な乖離ノードなし", comRowNote:top=>top?`(${top}系)`:"",
  scX:"被依存数（単純統計）→", scY:"媒介中心性（SNA）→", scHint:"← 左上 = 被依存は少ないが媒介が高い（単純統計では見えない要衝）",
  tipClick:" — クリックで診断とフォーカス表示", tipCat:"分類", tipCom:"コミュニティ", tipIndeg:"被依存", tipOut:"依存先", tipReach:"影響範囲", tipBtw:"媒介",
  metaTitle:l=>`再現性情報（${l}）`, metaFetch:"取得日", metaSrc:"データソース", metaRate:"シード成功率", metaScale:"規模",
  metaNode:"ノード", metaEdge:"エッジ", metaDensity:"密度", metaComp:"弱連結成分", metaMod:"モジュラリティ", metaCom:"コミュニティ",
  metaSeed:"乱数 seed", metaSeedUse:"（レイアウト・コミュニティ検出に使用）", metaTime:"指標処理時間", metaBtw:"媒介", metaTotal:"全体", metaGen:"生成日時",
  metaDet:"診断は決定論的ルールにより生成（AI 不使用） ／ 表示レイアウトは表示集合に応じて決定論的に再計算（初期値＝事前計算座標・反復固定・乱数不使用）",
 },
 en: {
  h1main:"OSS Dependency Network Analysis Demo",
  h1sub:"— A decision-support (DSS) style analysis-support system",
  headerHint:{edge:"dependent → dependency", size:"size / color = selected metric", cut:"cut point (removal isolates others)", click:"click a node for a diagnosis", zoom:"scroll to zoom, drag to pan (⟲ resets)"},
  gDomain:"Domain", gView:"View", gMetric:"Metric", gSearch:"Search / category", gTopn:"Shown", gLang:"Language",
  comBtn:"Community color", comBtnTitle:"Color by community detected with the Louvain method", zoomResetTitle:"Reset view",
  vNet:"Network", vScatter:"Scatter (in-degree × betweenness)",
  qPlaceholder:"search by name…", catAll:"Category: all",
  diagTitle:"Diagnosis — what this means",
  diagHint:'Click a node (or a community row in community-color mode) to see its metrics and what they mean for decision-making.<br>Diagnoses are generated by a deterministic rule + template table (node type × decision context). No LLM at runtime; fully reproducible.',
  divTitle:'Rank divergence — bottlenecks invisible to simple stats',
  legNormal:"node", legSeed:"seed (analysis root)", legCut:"cut point ⚠ (click to show what it isolates)", legIso:"isolated if removed",
  rankComTitle:"Communities (click to focus)",
  rankTopSuffix:" — Top 10",
  topnAll:n=>`all ${n} nodes`, topnTop:(k,n)=>`top ${k}/${n}`, catCount:n=>`${n} nodes shown`,
  seedBadge:"seed", funcGroup:"functional group", systemSuffix:"",
  badgeTip:{cutpoint:"Cut point: a choke point whose removal isolates other nodes from the main network",bridge:"Bridge: low in-degree but high betweenness — a path bottleneck",foundation:"Foundation: a base that many packages depend on directly (high in-degree)",isolated:"Isolated: no dependency relation observed within the collected scope",normal:"Standard: no structural peculiarity detected",seed:"Seed: a package chosen as an analysis starting point",cat:"Functional category: deterministic classification by name / description"},
  tIndeg:"In-degree (simple stat)", tIndegVal:(v,N,r)=>`${v} (rank ${r} of ${N})`,
  tReach:"Reach (transitive)", tReachVal:v=>`${v} packages`,
  tBtw:"Betweenness", tBtwVal:(v,r)=>`${v} (rank ${r})`, tPr:"PageRank", tCom:"Community",
  cutMain:cl=>{const p=cl>=10?`<b>${cl} packages</b> would be cut off from the main network at once — an especially wide-reaching impact`:cl>=3?`<b>${cl} packages</b> would be cut off from the main network`:`only <b>${cl} package(s)</b> would be isolated — a local effect, but still a structural choke point`;return `This is a <b>cut point</b>. If this package became unavailable, ${p} (highlighted in yellow on the graph).`;},
  cutList:(head,more)=>`<div class="diag-cut"><b>Isolated set:</b> ${head}${more?` +${more} more`:""}</div>`,
  cutReco:"<b>Concentration risk:</b> a structural chokepoint — a candidate for closer monitoring and review. <b>Adoption / support:</b> check for alternative paths in advance.",
  bridgeMain:(rin,rbt,gap)=>{const g=gap>=100?`The rank gap reaches ${gap} — an exceptionally large divergence. `:gap>=30?`The rank gap of ${gap} is large. `:"";return `Compared with its in-degree (rank ${rin}), its betweenness is clearly higher (<b>rank ${rbt}</b>). ${g}It sits at a path bottleneck (<b>bridge</b>); a failure could sever dependency paths between groups of packages. This type is hard to detect with simple stats.`;},
  bridgeReco:"<b>Adoption:</b> check maintenance and update cadence. <b>Support:</b> an easily overlooked candidate for support work.",
  foundMain:(indeg,rin,impact,N)=>{const sh=impact/N;const reach=sh>=0.25?`about ${Math.round(sh*100)}% of the analyzed network (${impact} packages)`:`${impact} packages transitively`;return `A <b>foundation</b> package with in-degree ${indeg} (rank ${rin} overall). An outage or vulnerability would propagate to ${reach}. This type is visible even with simple stats.`;},
  foundReco:"<b>Adoption:</b> a widely-used, standard choice. <b>Concentration risk:</b> a textbook single point of failure for the ecosystem — watch maintenance continuity.",
  isoMain:"No dependency relations are observed within this data range (its dependencies are outside the collected scope, or it is an independent package).",
  normMain:(rin,rbt)=>`No structural peculiarity detected (in-degree rank ${rin}, betweenness rank ${rbt}). It sits in a standard structural position, so reviewing individual metrics should be sufficient.`,
  evidence:'The metric interpretations draw on standard readings of SNA metrics (as synthesized in Chen et al. 2022) and findings on dependency networks (Decan et al. 2019); the type-classification rules are the design of this system. See the README for the full rule table. Diagnoses are <b>candidate flags</b> derived from structural metrics; actual adoption, support, or monitoring decisions require separate verification of each project\'s circumstances (maintenance, substitutability).',
  comTitle:cid=>`Community ${cid}`, comNodes:"Nodes", comInEdges:"Internal edges", comDensity:"Internal density", comAvgIn:"Mean in-degree",
  comTop:"<b>Representative nodes (top PageRank):</b> ",
  comDesc:"A community corresponds to a relatively dense <b>functional group</b>.",
  comReco:"<b>Adoption:</b> look for alternatives within the same community first. <b>Concentration risk:</b> a rough scope of how failures could propagate.",
  comEvidence:"See the README for the basis of the interpretation rules and the rule table.", comNone:"No community data",
  eigNote:'<b>※ Reference only</b>: dependency networks are nearly acyclic (DAG — one-directional, no loops), so eigenvector centrality’s power iteration tends to break down by concentrating its value at dependency sinks (nodes with no outgoing dependency) — hence the large rank gap. Use in-degree, betweenness, and PageRank for diagnosis. <b>That this metric does not suit dependency networks is itself one of the findings of this analysis.</b>',
  spearman:sp=>`Rank agreement (Spearman ρ) — in-degree×betweenness=${sp.indeg_vs_btw} / ×PageRank=${sp.indeg_vs_pagerank} / ×eigenvector=${sp.indeg_vs_eigenvector} (the farther from 1.0, the more SNA-specific information)`,
  divBridge:(id,rin,rbt,indeg,btw)=>`<b>${id}</b> — in-deg ${rin} → betw <b>${rbt}</b> <span class="muted">(in-deg ${indeg}, betw ${btw}) bridge</span>`,
  divFound:(id,rin,impact)=>`<b style="color:#2C5F94">${id}</b> — in-deg ${rin} · reach ${impact} <span class="muted">foundation (visible to simple stats)</span>`,
  divNone:"No prominent divergence nodes in this domain", comRowNote:top=>top?`(${top})`:"",
  scX:"In-degree (simple stat) →", scY:"Betweenness (SNA) →", scHint:"← top-left = low in-degree but high betweenness (bottlenecks invisible to simple stats)",
  tipClick:" — click for diagnosis & focus", tipCat:"Category", tipCom:"Community", tipIndeg:"In-deg", tipOut:"Out-deg", tipReach:"Reach", tipBtw:"Betw",
  metaTitle:l=>`Reproducibility (${l})`, metaFetch:"Fetched", metaSrc:"Source", metaRate:"Seed success", metaScale:"Scale",
  metaNode:"nodes", metaEdge:"edges", metaDensity:"density", metaComp:"weak components", metaMod:"modularity", metaCom:"communities",
  metaSeed:"random seed", metaSeedUse:"(layout & community detection)", metaTime:"metric time", metaBtw:"betweenness", metaTotal:"total", metaGen:"generated",
  metaDet:"Diagnoses are generated by deterministic rules (no LLM); layout is recomputed deterministically per visible set (seeded from precomputed coordinates, fixed iterations, no randomness)",
 },
 zhHant: {
  h1main:"OSS 依賴網路分析展示",
  h1sub:"— 決策支援（DSS）型分析支援系統",
  headerHint:{edge:"依賴方 → 被依賴方", size:"大小・顏色 = 所選指標", cut:"切斷點（移除會造成孤立）", click:"點擊節點顯示診斷", zoom:"滾輪縮放・拖曳平移（⟲ 還原）"},
  gDomain:"領域", gView:"檢視", gMetric:"指標", gSearch:"搜尋·分類", gTopn:"顯示數", gLang:"語言",
  comBtn:"社群著色", comBtnTitle:"依 Louvain 法偵測的社群著色", zoomResetTitle:"重設檢視",
  vNet:"網路圖", vScatter:"散佈圖（被依賴×中介）",
  qPlaceholder:"以名稱搜尋…", catAll:"分類：全部",
  diagTitle:"診斷 — 這代表什麼",
  diagHint:'點擊節點（或社群著色時的社群列），顯示指標數據與「在決策上代表什麼」的診斷。<br>診斷由節點類型 × 決策情境的對應表確定性生成（不使用 AI·可重現）。',
  divTitle:'排名乖離 — 簡單統計看不見的「要衝」',
  legNormal:"一般節點", legSeed:"種子（分析起點）", legCut:"切斷點 ⚠（點擊顯示其孤立範圍）", legIso:"移除時孤立的範圍",
  rankComTitle:"社群（點擊聚焦）",
  rankTopSuffix:" — Top 10",
  topnAll:n=>`全部 ${n} 節點`, topnTop:(k,n)=>`前 ${k}/${n}`, catCount:n=>`顯示 ${n} 節點`,
  seedBadge:"種子", funcGroup:"功能群", systemSuffix:"",
  badgeTip:{cutpoint:"切斷點: 移除後會使其他節點從主網路孤立的要害",bridge:"橋接型: 被依賴數低但中介中心性高，位於路徑要衝",foundation:"基礎型: 多數套件直接依賴的基礎（被依賴數居前）",isolated:"孤立: 收集範圍內未觀測到依賴關係的節點",normal:"標準: 未偵測到結構上特異性的節點",seed:"種子: 作為分析起點選定的套件",cat:"功能分類: 依名稱·說明的確定性分類"},
  tIndeg:"被依賴數（簡單統計）", tIndegVal:(v,N,r)=>`${v}（共 ${N} 中第 ${r} 位）`,
  tReach:"影響範圍（遞移）", tReachVal:v=>`${v} 個套件`,
  tBtw:"中介中心性", tBtwVal:(v,r)=>`${v}（第 ${r} 位）`, tPr:"PageRank", tCom:"社群",
  cutMain:cl=>{const p=cl>=10?`<b>${cl} 個</b>套件將一併從主網路中孤立，影響範圍尤其廣`:cl>=3?`<b>${cl} 個</b>套件將從主網路中孤立`:`孤立範圍僅 <b>${cl} 個</b>套件，屬局部影響，但仍是結構上的要害`;return `這是網路的<b>切斷點</b>。若此套件無法使用，${p}（圖中以黃色標示）。`;},
  cutList:(head,more)=>`<div class="diag-cut"><b>孤立範圍：</b> ${head}${more?` 其他 ${more} 項`:""}</div>`,
  cutReco:"<b>集中風險評估：</b> 結構上的要害，監控・精查的候選。<b>採用·支援決策：</b> 建議事先確認是否有替代路徑。",
  bridgeMain:(rin,rbt,gap)=>{const g=gap>=100?`兩指標的排名差達 ${gap}，排名乖離尤為顯著。`:gap>=30?`兩指標的排名差 ${gap} 較大。`:"";return `相較於被依賴數（第 ${rin} 位），其中介中心性明顯較高（<b>第 ${rbt} 位</b>）。${g}它位於依賴路徑的要衝（<b>橋接</b>），故障時可能切斷多個套件群之間的依賴路徑。此類型以簡單統計難以發現。`;},
  bridgeReco:"<b>採用決策：</b> 建議確認維護狀況與更新頻率。<b>支援決策：</b> 容易被忽略的支援對象候選。",
  foundMain:(indeg,rin,impact,N)=>{const sh=impact/N;const reach=sh>=0.25?`波及分析對象網路整體約 ${Math.round(sh*100)}%（${impact} 個套件）`:`遞移波及 ${impact} 個套件`;return `被依賴數 ${indeg}（整體第 ${rin} 位）的<b>基礎型</b>套件。若停止維護或出現漏洞，影響會${reach}。此類型以簡單統計也能發現。`;},
  foundReco:"<b>採用決策：</b> 廣泛使用的標準選項。<b>集中風險評估：</b> 依賴集中於單點的典型案例，須留意維護的延續性。",
  isoMain:"在此資料範圍內未觀測到與其他套件的依賴關係（其依賴在收集範圍外，或為獨立套件）。",
  normMain:(rin,rbt)=>`未偵測到結構上的特異性（被依賴第 ${rin} 位·中介第 ${rbt} 位）。在依賴結構上處於標準位置，確認各項指標即可。`,
  evidence:'各指標的解讀參考 SNA 的標準讀法（整理於 Chen et al. 2022 的綜述）與依賴網路研究的成果（Decan et al. 2019）；型分類規則本身為本系統的設計（規則表見 README）。本診斷為基於結構指標的<b>確認候選提示</b>；實際的採用、支援或監控決策，仍需另行確認專案實情（維護體制・可替代性等）。',
  comTitle:cid=>`社群 ${cid}`, comNodes:"節點數", comInEdges:"內部邊數", comDensity:"內部密度", comAvgIn:"平均被依賴數",
  comTop:"<b>代表節點（PageRank 前列）：</b> ",
  comDesc:"社群對應依賴相對密集的<b>功能群</b>。",
  comReco:"<b>採用決策：</b> 替代候選優先在同一社群內尋找。<b>集中風險評估：</b> 故障可能波及範圍的參考。",
  comEvidence:"解釋規則的依據與規則表見 README。", comNone:"無社群資訊",
  eigNote:'<b>※ 參考值</b>：依賴網路近乎無環（沒有迴圈的單向結構・DAG），特徵向量中心性的迭代計算容易失準（數值集中到「沒有對外依賴的終端」節點），排名大幅斷裂即因此。診斷請使用被依賴數·中介·PageRank。<b>「此指標不適合依賴網路」本身也是本分析所得的發現之一</b>。',
  spearman:sp=>`順位一致度（Spearman 等級相關 ρ）— 被依賴×中介=${sp.indeg_vs_btw} / ×PageRank=${sp.indeg_vs_pagerank} / ×特徵向量=${sp.indeg_vs_eigenvector}（越遠離 1.0，SNA 獨有的資訊越多）`,
  divBridge:(id,rin,rbt,indeg,btw)=>`<b>${id}</b> — 被依賴第 ${rin} 位 → 中介第 <b>${rbt}</b> 位 <span class="muted">(被依賴 ${indeg}・中介 ${btw}) 橋接型</span>`,
  divFound:(id,rin,impact)=>`<b style="color:#2C5F94">${id}</b> — 被依賴第 ${rin} 位·影響範圍 ${impact} <span class="muted">基礎型（簡單統計也可見）</span>`,
  divNone:"此領域無顯著的乖離節點", comRowNote:top=>top?`(${top})`:"",
  scX:"被依賴數（簡單統計）→", scY:"中介中心性（SNA）→", scHint:"← 左上 = 被依賴少但中介高（簡單統計看不見的要衝）",
  tipClick:" — 點擊顯示診斷與聚焦", tipCat:"分類", tipCom:"社群", tipIndeg:"被依賴", tipOut:"依賴", tipReach:"影響範圍", tipBtw:"中介",
  metaTitle:l=>`可重現資訊（${l}）`, metaFetch:"取得日", metaSrc:"資料來源", metaRate:"種子成功率", metaScale:"規模",
  metaNode:"節點", metaEdge:"邊", metaDensity:"密度", metaComp:"弱連通分量", metaMod:"模組度", metaCom:"社群",
  metaSeed:"隨機 seed", metaSeedUse:"（用於佈局·社群偵測）", metaTime:"指標處理時間", metaBtw:"中介", metaTotal:"總計", metaGen:"生成時間",
  metaDet:"診斷由確定性規則生成（不使用 AI） / 顯示佈局依顯示集合確定性重算（初值＝預計算座標·迭代固定·無隨機）",
 },
 zhHans: {
  h1main:"OSS 依赖网络分析演示",
  h1sub:"— 决策支持（DSS）型分析支持系统",
  headerHint:{edge:"依赖方 → 被依赖方", size:"大小・颜色 = 所选指标", cut:"切断点（移除会造成孤立）", click:"点击节点显示诊断", zoom:"滚轮缩放・拖动平移（⟲ 还原）"},
  gDomain:"领域", gView:"视图", gMetric:"指标", gSearch:"搜索·分类", gTopn:"显示数", gLang:"语言",
  comBtn:"社群着色", comBtnTitle:"按 Louvain 法检测的社群着色", zoomResetTitle:"重置视图",
  vNet:"网络图", vScatter:"散点图（被依赖×中介）",
  qPlaceholder:"按名称搜索…", catAll:"分类：全部",
  diagTitle:"诊断 — 这意味着什么",
  diagHint:'点击节点（或社群着色时的社群行），显示指标数据与「在决策上意味着什么」的诊断。<br>诊断由节点类型 × 决策场景的对应表确定性生成（不使用 AI·可复现）。',
  divTitle:'排名乖离 — 简单统计看不见的「要冲」',
  legNormal:"普通节点", legSeed:"种子（分析起点）", legCut:"切断点 ⚠（点击显示其孤立范围）", legIso:"移除时孤立的范围",
  rankComTitle:"社群（点击聚焦）",
  rankTopSuffix:" — Top 10",
  topnAll:n=>`全部 ${n} 节点`, topnTop:(k,n)=>`前 ${k}/${n}`, catCount:n=>`显示 ${n} 节点`,
  seedBadge:"种子", funcGroup:"功能群", systemSuffix:"",
  badgeTip:{cutpoint:"切断点: 移除后会使其他节点从主网络孤立的要害",bridge:"桥接型: 被依赖数低但中介中心性高，位于路径要冲",foundation:"基础型: 多数软件包直接依赖的基础（被依赖数靠前）",isolated:"孤立: 收集范围内未观测到依赖关系的节点",normal:"标准: 未检测到结构上特异性的节点",seed:"种子: 作为分析起点选定的软件包",cat:"功能分类: 按名称·说明的确定性分类"},
  tIndeg:"被依赖数（简单统计）", tIndegVal:(v,N,r)=>`${v}（共 ${N} 中第 ${r} 位）`,
  tReach:"影响范围（传递）", tReachVal:v=>`${v} 个软件包`,
  tBtw:"中介中心性", tBtwVal:(v,r)=>`${v}（第 ${r} 位）`, tPr:"PageRank", tCom:"社群",
  cutMain:cl=>{const p=cl>=10?`<b>${cl} 个</b>软件包将一并从主网络中孤立，影响范围尤其广`:cl>=3?`<b>${cl} 个</b>软件包将从主网络中孤立`:`孤立范围仅 <b>${cl} 个</b>软件包，属局部影响，但仍是结构上的要害`;return `这是网络的<b>切断点</b>。若此软件包不可用，${p}（图中以黄色高亮）。`;},
  cutList:(head,more)=>`<div class="diag-cut"><b>孤立范围：</b> ${head}${more?` 其他 ${more} 项`:""}</div>`,
  cutReco:"<b>集中风险评估：</b> 结构上的要害，监控・精查的候选。<b>采用·支持决策：</b> 建议事先确认是否有替代路径。",
  bridgeMain:(rin,rbt,gap)=>{const g=gap>=100?`两指标的排名差达 ${gap}，排名乖离尤为显著。`:gap>=30?`两指标的排名差 ${gap} 较大。`:"";return `相比被依赖数（第 ${rin} 位），其中介中心性明显更高（<b>第 ${rbt} 位</b>）。${g}它位于依赖路径的要冲（<b>桥接</b>），故障时可能切断多个软件包群之间的依赖路径。此类型用简单统计难以发现。`;},
  bridgeReco:"<b>采用决策：</b> 建议确认维护状况与更新频率。<b>支持决策：</b> 容易被忽略的支持对象候选。",
  foundMain:(indeg,rin,impact,N)=>{const sh=impact/N;const reach=sh>=0.25?`波及分析对象网络整体约 ${Math.round(sh*100)}%（${impact} 个软件包）`:`传递波及 ${impact} 个软件包`;return `被依赖数 ${indeg}（整体第 ${rin} 位）的<b>基础型</b>软件包。若停止维护或出现漏洞，影响会${reach}。此类型用简单统计也能发现。`;},
  foundReco:"<b>采用决策：</b> 广泛使用的标准选项。<b>集中风险评估：</b> 依赖集中于单点的典型案例，需留意维护的延续性。",
  isoMain:"在此数据范围内未观测到与其他软件包的依赖关系（其依赖在收集范围外，或为独立软件包）。",
  normMain:(rin,rbt)=>`未检测到结构上的特异性（被依赖第 ${rin} 位·中介第 ${rbt} 位）。在依赖结构上处于标准位置，确认各项指标即可。`,
  evidence:'各指标的解读参考 SNA 的标准读法（整理于 Chen et al. 2022 的综述）与依赖网络研究的成果（Decan et al. 2019）；型分类规则本身为本系统的设计（规则表见 README）。本诊断为基于结构指标的<b>确认候选提示</b>；实际的采用、支持或监控决策，仍需另行确认项目实情（维护体制・可替代性等）。',
  comTitle:cid=>`社群 ${cid}`, comNodes:"节点数", comInEdges:"内部边数", comDensity:"内部密度", comAvgIn:"平均被依赖数",
  comTop:"<b>代表节点（PageRank 前列）：</b> ",
  comDesc:"社群对应依赖相对密集的<b>功能群</b>。",
  comReco:"<b>采用决策：</b> 替代候选优先在同一社群内寻找。<b>集中风险评估：</b> 故障可能波及范围的参考。",
  comEvidence:"解释规则的依据与规则表见 README。", comNone:"无社群信息",
  eigNote:'<b>※ 参考值</b>：依赖网络近乎无环（没有回环的单向结构・DAG），特征向量中心性的迭代计算容易失准（数值集中到「没有对外依赖的终端」节点），排名大幅断裂即因此。诊断请使用被依赖数·中介·PageRank。<b>「该指标不适合依赖网络」本身也是本分析得到的发现之一</b>。',
  spearman:sp=>`顺位一致度（Spearman 等级相关 ρ）— 被依赖×中介=${sp.indeg_vs_btw} / ×PageRank=${sp.indeg_vs_pagerank} / ×特征向量=${sp.indeg_vs_eigenvector}（越远离 1.0，SNA 独有的信息越多）`,
  divBridge:(id,rin,rbt,indeg,btw)=>`<b>${id}</b> — 被依赖第 ${rin} 位 → 中介第 <b>${rbt}</b> 位 <span class="muted">(被依赖 ${indeg}・中介 ${btw}) 桥接型</span>`,
  divFound:(id,rin,impact)=>`<b style="color:#2C5F94">${id}</b> — 被依赖第 ${rin} 位·影响范围 ${impact} <span class="muted">基础型（简单统计也可见）</span>`,
  divNone:"该领域无显著的乖离节点", comRowNote:top=>top?`(${top})`:"",
  scX:"被依赖数（简单统计）→", scY:"中介中心性（SNA）→", scHint:"← 左上 = 被依赖少但中介高（简单统计看不见的要冲）",
  tipClick:" — 点击显示诊断与聚焦", tipCat:"分类", tipCom:"社群", tipIndeg:"被依赖", tipOut:"依赖", tipReach:"影响范围", tipBtw:"中介",
  metaTitle:l=>`可复现信息（${l}）`, metaFetch:"取得日", metaSrc:"数据来源", metaRate:"种子成功率", metaScale:"规模",
  metaNode:"节点", metaEdge:"边", metaDensity:"密度", metaComp:"弱连通分量", metaMod:"模块度", metaCom:"社群",
  metaSeed:"随机 seed", metaSeedUse:"（用于布局·社群检测）", metaTime:"指标处理时间", metaBtw:"中介", metaTotal:"总计", metaGen:"生成时间",
  metaDet:"诊断由确定性规则生成（不使用 AI） / 显示布局按显示集合确定性重算（初值＝预计算坐标·迭代固定·无随机）",
 },
};
function T(){ return STR[lang]; }

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
// ノード名を、そのノードを焦点（エゴネットワーク）にするリンクとして描画する。
// クリックは renderSide で #diag 内の .nodelink に束縛する。
function nodeLinks(ids, sep){
  return ids.map(id=>`<a class="nodelink" data-goto="${esc(id)}">${esc(id)}</a>`).join(sep);
}
// 推奨文を項目（各 <b>ラベル:</b>）ごとに改行する
function splitReco(s){ let i=0; return s.replace(/<b>/g, () => (i++ === 0) ? "<b>" : "<br><b>"); }
// README リンク: 日本語は日本語版の規則表、他言語は英語版の規則表アンカーへ
const REPO = "https://github.com/shiameyeung/oss-dependency-sna";
function readmeUrl(){ return REPO + (lang==="ja" ? "#rules-ja" : "#rules-en"); }
function linkifyReadme(s){
  return s.replace("README", `<a class="extlink" href="${readmeUrl()}" target="_blank" rel="noopener">README</a>`);
}
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
  const S = T(), N = g.nodes.length, CUT = g.cut_impact || {};
  const sep = lang==="ja" ? "、" : ", ";
  const types = nodeTypes(n);
  let badges = types.map(t=>`<span class="badge" data-tip="${esc(S.badgeTip[t]||"")}" style="background:${TYPE_INFO[t].color}">${TYPE_INFO[t][lang]}</span>`).join("");
  if (n.seed) badges += `<span class="badge" data-tip="${esc(S.badgeTip.seed)}" style="background:#5DA8E8">${S.seedBadge}</span>`;
  if (n.cat) badges += `<span class="badge" data-tip="${esc(S.badgeTip.cat)}" style="background:#8FA8C0">${esc(catLabel(n.cat))}</span>`;
  const d = descOf(n);
  const descHtml = `<section class="diag-purpose"><h3>${PURPOSE_LABEL[lang]}</h3><p class="diag-desc">${esc(d || PURPOSE_MISSING[lang])}</p></section>`;
  const table = `<table class="diag-table">
    <tr><td>${S.tIndeg}</td><td>${S.tIndegVal(n.indeg, N, n.r_in)}</td></tr>
    <tr><td>${S.tReach}</td><td>${S.tReachVal(n.impact)}</td></tr>
    <tr><td>${S.tBtw}</td><td>${S.tBtwVal(n.btw, n.r_bt)}</td></tr>
    <tr><td>${S.tPr}</td><td>${n.pr}</td></tr>
    <tr><td>${S.tCom}</td><td>${n.com}</td></tr></table>`;
  const texts = [], recos = [];
  for (const t of types){
    if (t === "cutpoint"){
      const cut = CUT[n.id] || [];
      texts.push(S.cutMain(cut.length));
      recos.push(S.cutReco);
      if (cut.length) texts.push(S.cutList(nodeLinks(cut.slice(0,8), sep), cut.length>8 ? cut.length-8 : 0));
    } else if (t === "bridge"){
      texts.push(S.bridgeMain(n.r_in, n.r_bt, n.r_in - n.r_bt));
      recos.push(S.bridgeReco);
    } else if (t === "foundation"){
      texts.push(S.foundMain(n.indeg, n.r_in, n.impact, N));
      recos.push(S.foundReco);
    } else if (t === "isolated"){
      texts.push(S.isoMain);
    } else {
      texts.push(S.normMain(n.r_in, n.r_bt));
    }
  }
  return `<div class="diag-name">${esc(n.label)}</div>${descHtml}${badges}${table}
    ${texts.slice(0, types.includes("cutpoint") ? 2 : 1).map(t=>`<div class="diag-text">${t}</div>`).join("")}
    ${recos.length?`<div class="diag-reco">${recos.slice(0,1).map(splitReco).join("<br>")}</div>`:""}
    <details class="method-detail"><summary>${({ja:"説明の根拠・注意点",en:"Method and limitations",zhHant:"說明依據與限制",zhHans:"说明依据与限制"})[lang]}</summary>${texts.slice(types.includes("cutpoint") ? 2 : 1).join("<br>")}${recos.slice(1).map(splitReco).join("<br>")}${linkifyReadme(S.evidence)}</details>`;
}
function diagnoseCom(cid, g){
  const S = T();
  const st = (g.communities||[]).find(c=>c.id===cid);
  if (!st) return `<div class="hint">${S.comNone}</div>`;
  const member = g.nodes.filter(n=>n.com===cid);
  const avgIn = member.length ? (member.reduce((a,n)=>a+n.indeg,0)/member.length).toFixed(1) : 0;
  const sep = lang==="ja" ? "、" : ", ";
  const rep = esc((st.top[0]||"?").split("/").pop()), sfx = S.systemSuffix;
  return `<div class="diag-name">${rep}${sfx} <span style="font-weight:400;color:#5C6B7A;font-size:12px">${S.comTitle(cid)}</span></div>
    <span class="badge" data-tip="${esc(S.badgeTip.cat)}" style="background:${COLORS[cid%COLORS.length]}; color:#1F2D40">${S.funcGroup}</span>
    <table class="diag-table">
      <tr><td>${S.comNodes}</td><td>${st.n}</td></tr>
      <tr><td>${S.comInEdges}</td><td>${st.m_in}</td></tr>
      <tr><td>${S.comDensity}</td><td>${st.density}</td></tr>
      <tr><td>${S.comAvgIn}</td><td>${avgIn}</td></tr></table>
    <div class="diag-text">${S.comTop}${nodeLinks(st.top, sep)}</div>
    <div class="diag-text">${S.comDesc}</div>
    <div class="diag-reco">${splitReco(S.comReco)}</div>
    <div class="muted" style="margin-top:7px">${linkifyReadme(S.comEvidence)}</div>`;
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
function applyStaticText(){
  const S = T();
  $("#h1main").textContent = S.h1main;
  $("#h1sub").textContent = S.h1sub;
  $("#hintbar").innerHTML = HINT_ORDER.map(k =>
    `<span class="hint-item">${HINT_ICONS[k]}<span>${esc(S.headerHint[k])}</span></span>`).join("");
  $("#lblDomain").textContent = S.gDomain; $("#lblView").textContent = S.gView;
  $("#lblMetric").textContent = S.gMetric; $("#lblSearch").textContent = S.gSearch;
  $("#lblTopn").textContent = S.gTopn;
  $("#comBtn").textContent = S.comBtn; $("#comBtn").title = S.comBtnTitle;
  $("#zoomReset").title = S.zoomResetTitle;
  $("#zoomReset").textContent = "⟲ " + S.zoomResetTitle;
  $("#q").setAttribute("aria-label", S.qPlaceholder);
  $("#catSel").setAttribute("aria-label", S.gSearch);
  $("#topn").setAttribute("aria-label", S.gTopn);
  $("#q").placeholder = S.qPlaceholder;
  $("#diagTitle").textContent = S.diagTitle;
  $("#divTitle").textContent = S.divTitle;
  $("#legNormal").textContent = S.legNormal; $("#legSeed").textContent = S.legSeed;
  $("#legCut").textContent = S.legCut; $("#legIso").textContent = S.legIso;
  document.documentElement.lang = HTMLLANG[lang] || lang;
  const portfolioLang = lang.startsWith('zh') ? 'zh' : lang;
  const portfolioLabels = {ja:['ホーム','プロジェクト','仕事での取り組み','職務経歴書'],en:['Home','Projects','Work','Resume'],zhHans:['首页','个人项目','工作实践','简历'],zhHant:['首頁','個人專案','工作實踐','履歷']}[lang];
  $("#portfolio-home").href = 'https://yotenra.com/index.html?lang=' + portfolioLang;
  $("#portfolio-header").setAttribute('aria-label', {ja:'メニュー',en:'Menu',zhHans:'导航',zhHant:'導覽'}[lang]);
  $("#portfolio-links").innerHTML = ['index.html','apps.html','work.html','resume.html'].map((page,i) => `<a href="https://yotenra.com/${page}?lang=${portfolioLang}">${portfolioLabels[i]}</a>`).join('');
  // 言語切替ボタン（地球アイコン横）を生成・現在の言語をハイライト・クリックを束縛
  $("#langs").innerHTML = LANGS.map(([code,label]) =>
    `<button data-lang="${code}" class="${code===lang?'on':''}">${label}</button>`).join("");
  document.querySelectorAll("#langs [data-lang]").forEach(b => b.onclick = () => setLang(b.dataset.lang));
}
function drawButtons(){
  $("#domains").innerHTML = Object.entries(DATA).map(([k,g]) =>
    `<button data-d="${k}" class="${k===curD?'on':''}">${esc(domLabel(g))}</button>`).join(" ");
  $("#views").innerHTML =
    `<button data-v="net" class="${view==='net'?'on':''}">${T().vNet}</button> ` +
    `<button data-v="scatter" class="${view==='scatter'?'on':''}">${T().vScatter}</button>`;
  const dis = view==="scatter" ? " dis" : "";
  $("#metrics").innerHTML = Object.keys(MLAB).map(m =>
    `<button data-m="${m}" data-tip="${esc(mlab(m))}" class="${m===curM&&!comMode?'on':''}${dis}">${esc(mshort(m))}</button>`).join(" ");
  $("#comBtn").className = (comMode ? "on" : "") + dis;
  document.querySelectorAll("[data-d]").forEach(b => b.onclick = () => {
    curD=b.dataset.d; selected=null; selectedCom=null; topN=0; catFilter="";
    resetZoom(); initSlider(); initSearch(); render(); });
  document.querySelectorAll("[data-v]").forEach(b => b.onclick = () => { view=b.dataset.v; resetZoom(); render(); });
  document.querySelectorAll("[data-m]").forEach(b => b.onclick = () => { curM=b.dataset.m; comMode=false; selectedCom=null; render(); });
  $("#comBtn").onclick = () => { comMode=!comMode; if(!comMode) selectedCom=null; render(); };
}
function setLang(l){
  if (l===lang) return;
  lang = l;
  applyStaticText(); initSearch(); render();
}
function initSlider(){
  const g = DATA[curD], el = $("#topn");
  el.min = 10; el.step = 10;
  el.max = Math.ceil(g.nodes.length / 10) * 10;   // step 非整合のノード数でも「全表示」へ戻せるよう切り上げ
  el.value = topN && topN < g.nodes.length ? topN : el.max;
  el.oninput = () => { topN = (+el.value >= g.nodes.length) ? 0 : +el.value; render(); };
}
function sliderLabel(g){
  const S = T(), vis = visibleIds(g);
  if (catFilter) $("#topnVal").textContent = S.catCount(vis ? vis.size : 0);
  else $("#topnVal").textContent = topN ? S.topnTop(topN, g.nodes.length) : S.topnAll(g.nodes.length);
}
function initSearch(){
  const g = DATA[curD];
  $("#qlist").innerHTML = g.nodes.map(n=>`<option value="${esc(n.id)}">`).join("");
  const open = lang==="ja" ? "（" : " (", close = lang==="ja" ? "）" : ")";
  $("#catSel").innerHTML = `<option value="">${T().catAll}</option>` +
    (g.categories||[]).map(c=>`<option value="${esc(c.name)}"${c.name===catFilter?" selected":""}>${esc(catLabel(c.name))}${open}${c.n}${close}</option>`).join("");
  $("#q").value = "";
}
$("#catSel").addEventListener("change", () => {
  catFilter = $("#catSel").value;
  if (catFilter){ comMode=false; selectedCom=null; }
  render();
});
$("#q").addEventListener("keydown", e => {
  if(e.key==="Enter"){ e.preventDefault(); $("#q").dispatchEvent(new Event("change")); }
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
  const W=1000,H=660,L=80,R=40,TM=40,B=70;   // TM = top margin（グローバル関数 T() と名前が衝突しないよう改名）
  const pts = g.nodes.filter(shown);
  const xmax = Math.max(...pts.map(n=>n.indeg), 1);
  const ymax = Math.max(...pts.map(n=>n.btw), 1e-6);
  const xs = v => L + (W-L-R) * Math.sqrt(v/xmax);
  const ys = v => H-B - (H-TM-B) * Math.sqrt(v/ymax);
  const divIds = new Set((g.divergence||[]).map(d=>d.id));
  const fndIds = new Set((g.foundation||[]).map(d=>d.id));
  // 軸とグリッド（sqrt 標度。値は i/4 の二乗で決定的）
  let ax = `<line x1="${L}" y1="${H-B}" x2="${W-R}" y2="${H-B}" stroke="#9FB2C6" stroke-width="1"/>
            <line x1="${L}" y1="${TM}" x2="${L}" y2="${H-B}" stroke="#9FB2C6" stroke-width="1"/>`;
  for (let i=1;i<=4;i++){
    const fx = xmax*(i/4)**2, fy = ymax*(i/4)**2;
    ax += `<line x1="${xs(fx)}" y1="${TM}" x2="${xs(fx)}" y2="${H-B}" stroke="#E4ECF4" stroke-width="1"/>
           <text x="${xs(fx)}" y="${H-B+18}" font-size="10" fill="#5C6B7A" text-anchor="middle">${Math.round(fx)}</text>
           <line x1="${L}" y1="${ys(fy)}" x2="${W-R}" y2="${ys(fy)}" stroke="#E4ECF4" stroke-width="1"/>
           <text x="${L-8}" y="${ys(fy)+3}" font-size="10" fill="#5C6B7A" text-anchor="end">${fy.toFixed(4)}</text>`;
  }
  const S = T();
  ax += `<text x="${(L+W-R)/2}" y="${H-B+40}" font-size="12" fill="#1F2D40" text-anchor="middle" font-weight="bold">${esc(S.scX)}</text>
         <text x="22" y="${(TM+H-B)/2}" font-size="12" fill="#1F2D40" text-anchor="middle" font-weight="bold" transform="rotate(-90 22 ${(TM+H-B)/2})">${esc(S.scY)}</text>
         <text x="${L+14}" y="${TM+18}" font-size="11.5" fill="#A8761A" font-weight="bold">${esc(S.scHint)}</text>`;
  $("#edges").innerHTML = ax;
  // 重なり回避の決定論的ジッタ: 同一座標（btw≈0 のノードが大半）に重なる点を黄金角スパイラルで
  // 散らし、全ノードを可視化する。中心は真の (indeg, btw) 位置のまま＝構造（左上＝乖離）は保つ。
  const JX = id => jit.get(id)[0], JY = id => jit.get(id)[1];
  const jit = new Map();
  const groups = {};
  for (const n of pts){
    const k = Math.round(xs(n.indeg)) + "," + Math.round(ys(n.btw));
    (groups[k] = groups[k] || []).push(n.id);
  }
  for (const k in groups){
    const ids = groups[k].sort();   // 決定論的順序
    const cnt = ids.length;
    ids.forEach((id, j) => {
      if (cnt === 1){ jit.set(id, [xs(byId[id].indeg), ys(byId[id].btw)]); return; }
      const r = 2.1 * Math.sqrt(j), a = j * 2.399963229;   // ひまわり配置（均等分散）
      jit.set(id, [xs(byId[id].indeg) + r*Math.cos(a), ys(byId[id].btw) + r*Math.sin(a)]);
    });
  }
  const drawOrder = [...pts].sort((a,b)=> a.btw-b.btw || (a.id<b.id?-1:1));   // 高媒介が最前面
  $("#nodes").innerHTML = drawOrder.map(n => {
    let fill="#A9C9E8", stroke="#ffffff", sw=0.6, r=3.6, op=0.62;   // 通常点は小さめ半透明＝密度が見える
    if (divIds.has(n.id)){ fill="#F2C84B"; stroke="#A8761A"; sw=1.4; r=6; op=1; }
    else if (fndIds.has(n.id)){ fill="#2C5F94"; r=6; op=1; }
    const sel = n.id===selected ? `<circle cx="${JX(n.id)}" cy="${JY(n.id)}" r="${r+6}" fill="none" stroke="#1F2D40" stroke-dasharray="3 3" stroke-width="1.5"/>` : "";
    return `${sel}<circle data-id="${n.id}" cx="${JX(n.id)}" cy="${JY(n.id)}" r="${r}" fill="${fill}" fill-opacity="${op}" stroke="${stroke}" stroke-width="${sw}" style="cursor:pointer"/>`;
  }).join("");
  const lab = pts.filter(n=>divIds.has(n.id)).sort((a,b)=>a.r_bt-b.r_bt).slice(0,6)
    .concat(pts.sort((a,b)=>b.indeg-a.indeg).slice(0,3));
  $("#labels").innerHTML = lab.map(n =>
    `<text x="${JX(n.id)+8}" y="${JY(n.id)-7}" font-size="10.5" fill="#1F2D40" paint-order="stroke" stroke="#ffffff" stroke-width="3">${esc(n.label)}</text>`).join("");
  // 全ノード数の注記（底辺集中の説明）
  const note = lang==="ja" ? `全 ${pts.length} ノードを描画（媒介中心性は大半が 0 のため底辺付近に密集。重なりは微小に分散）`
    : lang==="en" ? `${pts.length} nodes shown (most have betweenness ≈ 0, so they cluster near the bottom; overlaps are slightly spread)`
    : lang==="zhHant" ? `共繪製 ${pts.length} 個節點（多數中介中心性≈0，集中於底部；重疊處微幅分散）`
    : `共绘制 ${pts.length} 个节点（多数中介中心性≈0，集中于底部；重叠处微幅分散）`;
  $("#labels").innerHTML += `<text x="${40}" y="650" font-size="11" fill="#5C6B7A">${note}</text>`;
}

// リストから選択した対象がフィルタの外にある場合も、図上で確認できるようにする。
function focusNode(id){
  const vis=visibleIds(DATA[curD]);
  if(vis && !vis.has(id)){ catFilter=""; topN=0; initSlider(); initSearch(); }
  selected=id; comMode=false; selectedCom=null; render();
}
function renderSide(g, byId){
  const S = T();
  // 対象を切り替えたら、用途の説明から読める位置に戻す。
  const side = document.querySelector(".side");
  const focusKey = `${curD}:${selected || ""}:${selectedCom ?? ""}`;
  if (side.dataset.focusKey !== focusKey) side.scrollTop = 0;
  side.dataset.focusKey = focusKey;
  const comActive = comMode && view==="net";   // 散布図ではコミュニティフォーカスを適用しない
  // 診断カード
  if (comActive && selectedCom!=null){
    $("#diag").innerHTML = diagnoseCom(selectedCom, g);
  } else if (selected && byId[selected]){
    $("#diag").innerHTML = diagnoseNode(byId[selected], g);
  } else {
    $("#diag").innerHTML = `<div class="hint">${S.diagHint}</div>`;
  }
  // 診断カード内のノードリンク → そのノードを焦点（エゴネットワーク）にして表示
  document.querySelectorAll("#diag .nodelink").forEach(a => a.onclick = () => {
    catFilter=""; topN=0; comMode=false; selectedCom=null; view="net"; selected=a.dataset.goto;
    initSlider(); initSearch(); render();
  });
  // ランキング / コミュニティ一覧
  if (comActive){
    $("#rankTitle").textContent = S.rankComTitle;
    const cs = g.communities || [];
    const sfx = S.systemSuffix;   // 代表ノードの短縮名＋言語別の接尾辞を主表示、番号は補助
    $("#rankList").innerHTML = cs.slice(0,10).map(c => {
      const rep = esc((c.top[0]||"?").split("/").pop());
      return `<div class="rank-row${selectedCom===c.id?' sel':''}" data-com="${c.id}">
        <span class="dot" style="background:${COLORS[c.id%COLORS.length]}"></span>
        <span class="nm"><b>${rep}${sfx}</b> <span class="muted">#${c.id}</span></span>
        <span class="bar-bg"><span class="bar-fg" style="width:${100*c.n/g.nodes.length}%"></span></span>
        <span class="val">${c.n}</span></div>`; }).join("");
    document.querySelectorAll(".rank-row[data-com]").forEach(r => r.onclick = () => {
      const cid = +r.dataset.com;
      selectedCom = (selectedCom===cid) ? null : cid; selected=null; render(); });
  } else {
    $("#rankTitle").textContent = mshort(curM) + S.rankTopSuffix;
    const mx2 = Math.max(...g.nodes.map(n=>n[curM])) || 1;
    const rows = [...g.nodes].sort((a,b)=>b[curM]-a[curM]).slice(0,10);
    const eigNote = curM==="eig"
      ? `<div class="diag-cut" style="background:var(--warnbg);border-left:3px solid #F2C84B;margin:0 0 8px">${S.eigNote}</div>`
      : "";
    $("#rankList").innerHTML = eigNote + rows.map(n =>
      `<div class="rank-row${n.id===selected?' sel':''}" data-id="${n.id}">
        <span class="nm" title="${esc(n.id)}">${n.art?"⚠ ":""}${esc(n.label)}</span>
        <span class="bar-bg"><span class="bar-fg" style="width:${100*n[curM]/mx2}%"></span></span>
        <span class="val">${(+n[curM]).toLocaleString(undefined,{maximumFractionDigits:4})}</span></div>`).join("");
    document.querySelectorAll(".rank-row[data-id]").forEach(r => r.onclick = () => focusNode(r.dataset.id));
  }
  // 乖離パネル
  const dv = (g.divergence||[]).slice(0,6);
  const fd = (g.foundation||[]).slice(0,3);
  $("#divList").innerHTML =
    (dv.length ? dv.map(d =>
      `<div class="div-row" data-id="${d.id}">${S.divBridge(esc(d.id), d.rank_indeg, d.rank_btw, d.indeg, d.btw)}</div>`).join("") :
      `<div class="muted">${S.divNone}</div>`) +
    fd.map(d =>
      `<div class="div-row" data-id="${d.id}" style="border-left-color:#2C5F94; background:#EAF4FF">${S.divFound(esc(d.id), d.rank_indeg, d.impact)}</div>`).join("");
  document.querySelectorAll(".div-row[data-id]").forEach(r => r.onclick = () => focusNode(r.dataset.id));
  $("#spearman").textContent = S.spearman(g.spearman||{});
}

function render(){
  const g = DATA[curD], byId = Object.fromEntries(g.nodes.map(n=>[n.id,n]));
  drawButtons();
  sliderLabel(g);
  if (view === "scatter") renderScatter(g, byId); else renderNet(g, byId);
  renderSide(g, byId);
  // 既存の選択操作をキーボードでも利用できるようにする。
  document.querySelectorAll(".rank-row, .div-row, #diag .nodelink").forEach(el => {
    el.setAttribute("role", "button"); el.tabIndex=0;
    el.onkeydown=e=>{ if(e.key==="Enter" || e.key===" "){ e.preventDefault(); el.click(); } };
  });
  document.querySelectorAll("button[data-d], button[data-v], button[data-m], #comBtn, button[data-lang]").forEach(el=>{
    el.setAttribute("aria-pressed", String(el.classList.contains("on")));
    el.disabled=el.classList.contains("dis");
  });
  // メタ情報
  const S = T(), c=g.collect||{}, rp=g.repro||{}, sl=lang==="ja"?" ／ ":" / ";
  $("#meta").innerHTML =
    `<b>${S.metaTitle(domLabel(g))}</b> — ${S.metaFetch}: ${(c.fetched_dates||[]).join(", ")||"—"}${sl}${S.metaSrc}: deps.dev API v3${sl}` +
    `${S.metaRate}: ${c.n_seeds_ok??"—"}/${(c.n_seeds_ok??0)+(c.n_seeds_failed??0)} (${((c.success_rate??0)*100).toFixed(1)}%)${sl}` +
    `${S.metaScale}: ${g.n} ${S.metaNode} · ${g.m} ${S.metaEdge}${sl}${S.metaDensity} ${g.density}${sl}${S.metaComp} ${g.n_components}${sl}` +
    `${S.metaMod} ${g.modularity} (${S.metaCom} ${g.n_communities})<br>` +
    `${S.metaSeed}=${rp.random_seed} ${S.metaSeedUse}${sl}${S.metaTime}: ` +
    `${S.metaBtw} ${rp.durations_sec?.betweenness}s · ${S.metaTotal} ${rp.durations_sec?.total}s${sl}${S.metaGen}: ${g.generated_at}<br>` +
    `${S.metaDet}`;
  // ツールチップ + クリック
  const tip = $("#tip");
  document.querySelectorAll("circle[data-id]").forEach(cc => {
    cc.onmousemove = ev => {
      const n = byId[cc.dataset.id], d = descOf(n), sl=lang==="ja"?" ／ ":" / ";
      tip.innerHTML = `<b>${esc(n.label)}</b>${n.seed?" 🌱"+S.seedBadge:""}${n.art?" ⚠"+TYPE_INFO.cutpoint[lang]:""}<br>` +
        (d?`<span style="color:#5C6B7A;font-style:italic">${esc(d.slice(0,70))}${d.length>70?"…":""}</span><br>`:"") +
        `${S.tipCat}: ${esc(catLabel(n.cat)||"—")}${sl}${S.tipCom} ${n.com}<br>` +
        `${S.tipIndeg} ${n.indeg}（${n.r_in}）${sl}${S.tipOut} ${n.outdeg}${sl}${S.tipReach} ${n.impact}<br>` +
        `${S.tipBtw} ${n.btw}（${n.r_bt}）${S.tipClick}`;
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
      if (zMoved) return;   // ドラッグ（パン）直後のクリックは選択しない
      const id = cc.dataset.id;
      if (comMode && view==="net"){ selectedCom = (selectedCom===byId[id].com)?null:byId[id].com; selected=null; }
      else { selected = id===selected ? null : id; selectedCom = null; }
      render();
    };
  });
}
// 主ビューのズーム／パン（#viewport を transform。SVG は render で置換されないため一度だけ束縛）。
let zk=1, ztx=0, zty=0, zPan=false, zMoved=false, zsx=0, zsy=0, ztx0=0, zty0=0;
const svgEl = $("#svg"), vpEl = $("#viewport");
function applyZoom(){ vpEl.setAttribute("transform", `translate(${ztx} ${zty}) scale(${zk})`); }
function resetZoom(){ zk=1; ztx=0; zty=0; applyZoom(); }
svgEl.addEventListener("wheel", e => {
  e.preventDefault();
  const r = svgEl.getBoundingClientRect();
  const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(svgEl.getScreenCTM().inverse());
  const sx = pt.x, sy = pt.y;  // 余白を含む可変サイズの SVG 座標
  const f = e.deltaY < 0 ? 1.18 : 1/1.18;
  const nk = Math.min(8, Math.max(1, zk*f));
  ztx = sx - (sx-ztx)*(nk/zk); zty = sy - (sy-zty)*(nk/zk); zk = nk;   // カーソル位置を固定して拡縮
  if (zk === 1){ ztx = 0; zty = 0; }
  applyZoom();
}, {passive:false});
svgEl.addEventListener("pointerdown", e => { zPan=true; zMoved=false; zsx=e.clientX; zsy=e.clientY; ztx0=ztx; zty0=zty; });
window.addEventListener("pointermove", e => {
  if (!zPan) return;
  if (Math.abs(e.clientX-zsx)+Math.abs(e.clientY-zsy) > 4) zMoved=true;
  const r = svgEl.getBoundingClientRect();
  const matrix = svgEl.getScreenCTM();
  ztx = ztx0 + (e.clientX-zsx)/matrix.a; zty = zty0 + (e.clientY-zsy)/matrix.d;
  applyZoom();
});
window.addEventListener("pointerup", () => { zPan=false; });
$("#zoomReset").onclick = resetZoom;
// 空白クリックでフォーカス解除（ノード自身のクリック／ドラッグ直後は除く）。
$("#svg").addEventListener("click", e => {
  if (zMoved) return;
  const t = e.target;
  if (t && t.tagName === "circle" && t.getAttribute("data-id")) return;  // ノードクリックは無視
  if (selected !== null || selectedCom !== null){ selected = null; selectedCom = null; render(); }
});
applyStaticText();
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

    # 用途説明は表示用の注釈。保存済みのネットワーク・指標は変更しない。
    purposes = json.loads(pathlib.Path(__file__).with_name("plain_descriptions.json").read_text(encoding="utf-8"))["entries"]
    data = {}
    for p in args.inputs:
        d = json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
        for node in d["nodes"]:
            if node["id"] in purposes:
                node["purpose"] = purposes[node["id"]]
        data[d["domain"]] = d
    html = TEMPLATE.replace("__DATA_JSON__", json.dumps(data, ensure_ascii=False))
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"-> {out} ({out.stat().st_size//1024} KB, 領域: {list(data)})")


if __name__ == "__main__":
    main()
