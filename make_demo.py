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
  header { padding:14px 20px 10px; border-bottom:1px solid var(--line); position:relative; }
  #langbar { position:absolute; top:12px; right:18px; display:flex; align-items:center; gap:7px; }
  #langbar .globe { font-size:15px; opacity:.65; }
  #langbar button { padding:3px 9px; font-size:11.5px; border-radius:5px; }
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
  svg circle[fill="none"] { pointer-events:none; }  /* 装飾リング（切断点/選択）がクリックを奪わないように */
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
  <div id="langbar"><span class="globe" aria-hidden="true">🌐</span><span id="langs"></span></div>
  <h1><span id="h1main"></span> <span class="sub" id="h1sub"></span></h1>
  <div class="sub" id="headerHint"></div>
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
      <g id="edges"></g><g id="nodes"></g><g id="labels"></g>
    </svg>
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
let lang = "ja";   // 表示言語（ja / en）。データ・指標値は不変、表示文字列のみ切替。
const COLORS = ["#5DA8E8","#F2C84B","#81c784","#ba68c8","#ff8a65","#4dd0e1","#f06292","#a1887f","#90a4ae","#dce775"];
const LANGS = [["ja","日本語"],["en","English"],["zhHant","繁體"],["zhHans","简体"]];
const HTMLLANG = {ja:"ja", en:"en", zhHant:"zh-Hant", zhHans:"zh-Hans"};
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
// 説明文: 日本語のみ固定翻訳（desc_ja）。他言語はレジストリ原文（英語 desc_en）を用いる。
function descOf(n){ return lang==="ja" ? (n.desc_ja || n.desc_en || "") : (n.desc_en || n.desc_ja || ""); }

// UI 文字列・診断テンプレート（日/英）。データ準備段階で固定（実行時 LLM 不使用）。
const STR = {
 ja: {
  h1main:"OSS 依存ネットワーク分析デモ v2",
  h1sub:"— DSS 型分析支援システム（研究用プロトタイプ）",
  headerHint:'エッジの向き: 依存元 → 依存先。ノードの大きさ・色 = 選択中の指標。⚠ = 切断点（除去すると孤立が生じるノード）。ノードをクリックすると右上に診断を表示。',
  gDomain:"領域", gView:"ビュー", gMetric:"指標", gSearch:"検索・分類", gTopn:"表示数", gLang:"言語",
  comBtn:"コミュニティ着色", comBtnTitle:"Louvain 法で検出したコミュニティごとに着色",
  vNet:"ネットワーク図", vScatter:"散布図（被依存×媒介）",
  qPlaceholder:"名前で検索…", catAll:"分類: すべて",
  diagTitle:"診断 — これは何を意味するか",
  diagHint:'ノード（またはコミュニティ着色時のコミュニティ行）をクリックすると、指標データと「意思決定上何を意味するか」の診断を表示します。<br>診断はノード型 × 意思決定場面の対応表に基づく決定論的なルール＋テンプレートで生成（AI 不使用・再現可能）。',
  divTitle:'順位の乖離 — 単純統計では見えない「要衝」（RQ3）',
  legNormal:"通常ノード", legSeed:"シード（分析起点）", legCut:"切断点 ⚠（クリックで孤立する範囲を表示）", legIso:"切断時に孤立する範囲",
  rankComTitle:"コミュニティ（クリックでフォーカス）",
  rankTopSuffix:" — Top 10",
  topnAll:n=>`全 ${n} ノード`, topnTop:(k,n)=>`上位 ${k}/${n}`, catCount:n=>`${n} ノード表示中`,
  seedBadge:"シード", funcGroup:"機能群", systemSuffix:"系",
  tIndeg:"被依存数（単純統計）", tIndegVal:(v,N,r)=>`${v}（全 ${N} 中 ${r}位）`,
  tReach:"影響範囲（推移的）", tReachVal:v=>`${v} パッケージ`,
  tBtw:"媒介中心性", tBtwVal:(v,r)=>`${v}（${r}位）`, tPr:"PageRank", tCom:"コミュニティ",
  cutMain:cl=>{const p=cl>=10?`<b>${cl} 個</b>のパッケージが一斉に主要ネットワークから孤立し、影響が特に広範に及ぶ`:cl>=3?`<b>${cl} 個</b>のパッケージが主要ネットワークから孤立する`:`孤立する範囲は <b>${cl} パッケージ</b>と局所的にとどまるが、構造上の急所であることに変わりはない`;return `ネットワークの<b>切断点</b>にあたる。仮にこのパッケージが利用不能になると、${p}（図中に黄色でハイライト表示）。`;},
  cutList:(head,more)=>`<div class="diag-cut"><b>孤立する範囲:</b> ${head}${more?` 他 ${more} 件`:""}</div>`,
  cutReco:"<b>集中リスク把握:</b> 最優先での監視を推奨。<b>利用・支援判断:</b> 代替経路の有無の事前確認を推奨。",
  bridgeMain:(rin,rbt,gap)=>{const g=gap>=100?`両指標の順位差は ${gap} に達し、順位の乖離が際立って大きい。`:gap>=30?`両指標の順位差は ${gap} と大きい。`:"";return `被依存数（${rin}位）に比べ、媒介中心性は <b>${rbt}位</b>と明確に高い。${g}依存経路の要衝（<b>橋渡し</b>）に位置し、障害時には複数のパッケージ群の間の依存経路が分断されるおそれがある。単純統計では検出しにくい型。`;},
  bridgeReco:"<b>利用判断:</b> 保守体制・更新頻度の確認を推奨。<b>支援判断:</b> 見落とされやすい支援先候補。",
  foundMain:(indeg,rin,impact,N)=>{const sh=impact/N;const reach=sh>=0.25?`分析対象ネットワーク全体の約 ${Math.round(sh*100)}%（${impact} パッケージ）へ波及する`:`推移的に ${impact} パッケージへ波及する`;return `被依存数 ${indeg}（全体 ${rin}位）の<b>基盤（土台型）</b>パッケージ。停止・脆弱性の影響は${reach}。単純統計でも検出できる型。`;},
  foundReco:"<b>利用判断:</b> 広く利用されている標準的な選択肢。<b>集中リスク把握:</b> 依存が一点に集中する典型例。保守の継続性に注意。",
  isoMain:"このデータ範囲では他のパッケージとの依存関係が観測されない（依存先が収集範囲外、または独立したパッケージ）。",
  normMain:(rin,rbt)=>`構造上の特異性は検出されない（被依存 ${rin}位・媒介 ${rbt}位）。依存構造上は標準的な位置にあり、個別指標の確認で十分と考えられる。`,
  evidence:'解釈規則は、SNA 指標の標準的解釈（Chen et al. 2022 のレビューに整理されている）および依存ネットワーク研究の知見（Decan et al. 2019）に基づく（規則表は README を参照）。',
  comTitle:cid=>`コミュニティ ${cid}`, comNodes:"ノード数", comInEdges:"内部エッジ数", comDensity:"内部密度", comAvgIn:"平均被依存数",
  comTop:"<b>代表ノード（PageRank 上位）:</b> ",
  comDesc:"コミュニティは依存が相対的に密な<b>機能群</b>に対応する。",
  comReco:"<b>利用判断:</b> 代替候補はまず同一コミュニティ内から探索するのが有効。<b>集中リスク把握:</b> 障害が伝播しうる範囲の目安。",
  comEvidence:"解釈規則の根拠と規則表は README を参照。", comNone:"コミュニティ情報なし",
  eigNote:'<b>※ 参考値</b>: 依存ネットワークはほぼ非巡回（DAG）であり、固有ベクトル中心性の反復計算は依存の終端（sink）に値が集中して退化しやすい（順位が大きく断絶するのはこのため）。診断には次数・媒介・PageRank を用いる。<b>「この指標は依存ネットワーク向きではない」こと自体が RQ2 の知見</b>。',
  spearman:sp=>`Spearman ρ: 被依存×媒介=${sp.indeg_vs_btw} ／ ×PageRank=${sp.indeg_vs_pagerank} ／ ×固有ベクトル=${sp.indeg_vs_eigenvector}（1.0 から離れるほど SNA 独自の情報が多い）`,
  divBridge:(id,rin,rbt,indeg,btw)=>`<b>${id}</b> — 被依存 ${rin}位 → 媒介 <b>${rbt}位</b> <span class="muted">(indeg=${indeg}, btw=${btw}) 橋渡し型</span>`,
  divFound:(id,rin,impact)=>`<b style="color:#2C5F94">${id}</b> — 被依存 ${rin}位・影響範囲 ${impact} <span class="muted">土台型（単純統計でも見える）</span>`,
  divNone:"この領域では顕著な乖離ノードなし", comRowNote:top=>top?`(${top}系)`:"",
  scX:"被依存数（単純統計）→", scY:"媒介中心性（SNA）→", scHint:"← 左上 = 被依存は少ないが媒介が高い（単純統計では見えない要衝・RQ3）",
  tipClick:" — クリックで診断とフォーカス表示", tipCat:"分類", tipCom:"コミュニティ", tipIndeg:"被依存", tipOut:"依存先", tipReach:"影響範囲", tipBtw:"媒介",
  metaTitle:l=>`再現性情報（${l}）`, metaFetch:"取得日", metaSrc:"データソース", metaRate:"シード成功率", metaScale:"規模",
  metaNode:"ノード", metaEdge:"エッジ", metaDensity:"密度", metaComp:"弱連結成分", metaMod:"モジュラリティ", metaCom:"コミュニティ",
  metaSeed:"乱数 seed", metaSeedUse:"（レイアウト・コミュニティ検出に使用）", metaTime:"指標処理時間", metaBtw:"媒介", metaTotal:"全体", metaGen:"生成日時",
  metaDet:"診断は決定論的ルールにより生成（AI 不使用） ／ 表示レイアウトは表示集合に応じて決定論的に再計算（初期値＝事前計算座標・反復固定・乱数不使用）",
 },
 en: {
  h1main:"OSS Dependency Network Analysis Demo v2",
  h1sub:"— DSS-style analysis-support prototype (research use)",
  headerHint:'Edge direction: dependent → dependency. Node size/color = selected metric. ⚠ = cut point (its removal isolates other nodes). Click a node for a diagnosis on the right.',
  gDomain:"Domain", gView:"View", gMetric:"Metric", gSearch:"Search / category", gTopn:"Shown", gLang:"Language",
  comBtn:"Community color", comBtnTitle:"Color by community detected with the Louvain method",
  vNet:"Network", vScatter:"Scatter (in-degree × betweenness)",
  qPlaceholder:"search by name…", catAll:"Category: all",
  diagTitle:"Diagnosis — what this means",
  diagHint:'Click a node (or a community row in community-color mode) to see its metrics and what they mean for decision-making.<br>Diagnoses are generated by a deterministic rule + template table (node type × decision context). No LLM at runtime; fully reproducible.',
  divTitle:'Rank divergence — bottlenecks invisible to simple stats (RQ3)',
  legNormal:"node", legSeed:"seed (analysis root)", legCut:"cut point ⚠ (click to show what it isolates)", legIso:"isolated if removed",
  rankComTitle:"Communities (click to focus)",
  rankTopSuffix:" — Top 10",
  topnAll:n=>`all ${n} nodes`, topnTop:(k,n)=>`top ${k}/${n}`, catCount:n=>`${n} nodes shown`,
  seedBadge:"seed", funcGroup:"functional group", systemSuffix:"",
  tIndeg:"In-degree (simple stat)", tIndegVal:(v,N,r)=>`${v} (rank ${r} of ${N})`,
  tReach:"Reach (transitive)", tReachVal:v=>`${v} packages`,
  tBtw:"Betweenness", tBtwVal:(v,r)=>`${v} (rank ${r})`, tPr:"PageRank", tCom:"Community",
  cutMain:cl=>{const p=cl>=10?`<b>${cl} packages</b> would be cut off from the main network at once — an especially wide-reaching impact`:cl>=3?`<b>${cl} packages</b> would be cut off from the main network`:`only <b>${cl} package(s)</b> would be isolated — a local effect, but still a structural choke point`;return `This is a <b>cut point</b>. If this package became unavailable, ${p} (highlighted in yellow on the graph).`;},
  cutList:(head,more)=>`<div class="diag-cut"><b>Isolated set:</b> ${head}${more?` +${more} more`:""}</div>`,
  cutReco:"<b>Concentration risk:</b> a top priority to monitor. <b>Adoption / support:</b> check for alternative paths in advance.",
  bridgeMain:(rin,rbt,gap)=>{const g=gap>=100?`The rank gap reaches ${gap} — an exceptionally large divergence. `:gap>=30?`The rank gap of ${gap} is large. `:"";return `Compared with its in-degree (rank ${rin}), its betweenness is clearly higher (<b>rank ${rbt}</b>). ${g}It sits at a path bottleneck (<b>bridge</b>); a failure could sever dependency paths between groups of packages. This type is hard to detect with simple stats.`;},
  bridgeReco:"<b>Adoption:</b> check maintenance and update cadence. <b>Support:</b> an easily overlooked candidate for support work.",
  foundMain:(indeg,rin,impact,N)=>{const sh=impact/N;const reach=sh>=0.25?`about ${Math.round(sh*100)}% of the analyzed network (${impact} packages)`:`${impact} packages transitively`;return `A <b>foundation</b> package with in-degree ${indeg} (rank ${rin} overall). An outage or vulnerability would propagate to ${reach}. This type is visible even with simple stats.`;},
  foundReco:"<b>Adoption:</b> a widely-used, standard choice. <b>Concentration risk:</b> a textbook single point of failure for the ecosystem — watch maintenance continuity.",
  isoMain:"No dependency relations are observed within this data range (its dependencies are outside the collected scope, or it is an independent package).",
  normMain:(rin,rbt)=>`No structural peculiarity detected (in-degree rank ${rin}, betweenness rank ${rbt}). It sits in a standard structural position, so reviewing individual metrics should be sufficient.`,
  evidence:'Interpretation rules follow standard readings of SNA metrics (organized in the review by Chen et al. 2022) and findings on dependency networks (Decan et al. 2019). See the README for the full rule table.',
  comTitle:cid=>`Community ${cid}`, comNodes:"Nodes", comInEdges:"Internal edges", comDensity:"Internal density", comAvgIn:"Mean in-degree",
  comTop:"<b>Representative nodes (top PageRank):</b> ",
  comDesc:"A community corresponds to a relatively dense <b>functional group</b>.",
  comReco:"<b>Adoption:</b> look for alternatives within the same community first. <b>Concentration risk:</b> a rough scope of how failures could propagate.",
  comEvidence:"See the README for the basis of the interpretation rules and the rule table.", comNone:"No community data",
  eigNote:'<b>※ Reference only</b>: dependency networks are nearly acyclic (DAG), so eigenvector centrality’s power iteration tends to degenerate by concentrating mass at dependency sinks (hence the large rank gap). Use in-degree, betweenness, and PageRank for diagnosis. <b>That this metric does not suit dependency networks is itself an RQ2 finding.</b>',
  spearman:sp=>`Spearman ρ: in-degree×betweenness=${sp.indeg_vs_btw} / ×PageRank=${sp.indeg_vs_pagerank} / ×eigenvector=${sp.indeg_vs_eigenvector} (the farther from 1.0, the more SNA-specific information)`,
  divBridge:(id,rin,rbt,indeg,btw)=>`<b>${id}</b> — in-deg ${rin} → betw <b>${rbt}</b> <span class="muted">(indeg=${indeg}, btw=${btw}) bridge</span>`,
  divFound:(id,rin,impact)=>`<b style="color:#2C5F94">${id}</b> — in-deg ${rin} · reach ${impact} <span class="muted">foundation (visible to simple stats)</span>`,
  divNone:"No prominent divergence nodes in this domain", comRowNote:top=>top?`(${top})`:"",
  scX:"In-degree (simple stat) →", scY:"Betweenness (SNA) →", scHint:"← top-left = low in-degree but high betweenness (bottlenecks invisible to simple stats · RQ3)",
  tipClick:" — click for diagnosis & focus", tipCat:"Category", tipCom:"Community", tipIndeg:"In-deg", tipOut:"Out-deg", tipReach:"Reach", tipBtw:"Betw",
  metaTitle:l=>`Reproducibility (${l})`, metaFetch:"Fetched", metaSrc:"Source", metaRate:"Seed success", metaScale:"Scale",
  metaNode:"nodes", metaEdge:"edges", metaDensity:"density", metaComp:"weak components", metaMod:"modularity", metaCom:"communities",
  metaSeed:"random seed", metaSeedUse:"(layout & community detection)", metaTime:"metric time", metaBtw:"betweenness", metaTotal:"total", metaGen:"generated",
  metaDet:"Diagnoses are generated by deterministic rules (no LLM); layout is recomputed deterministically per visible set (seeded from precomputed coordinates, fixed iterations, no randomness)",
 },
 zhHant: {
  h1main:"OSS 依賴網路分析展示 v2",
  h1sub:"— DSS 型分析支援系統（研究用原型）",
  headerHint:'邊的方向：依賴方 → 被依賴方。節點大小·顏色 = 所選指標。⚠ = 切斷點（移除會導致其他節點孤立）。點擊節點即在右上顯示診斷。',
  gDomain:"領域", gView:"檢視", gMetric:"指標", gSearch:"搜尋·分類", gTopn:"顯示數", gLang:"語言",
  comBtn:"社群著色", comBtnTitle:"依 Louvain 法偵測的社群著色",
  vNet:"網路圖", vScatter:"散佈圖（被依賴×中介）",
  qPlaceholder:"以名稱搜尋…", catAll:"分類：全部",
  diagTitle:"診斷 — 這代表什麼",
  diagHint:'點擊節點（或社群著色時的社群列），顯示指標數據與「在決策上代表什麼」的診斷。<br>診斷由節點類型 × 決策情境的對應表確定性生成（不使用 AI·可重現）。',
  divTitle:'排名乖離 — 簡單統計看不見的「要衝」（RQ3）',
  legNormal:"一般節點", legSeed:"種子（分析起點）", legCut:"切斷點 ⚠（點擊顯示其孤立範圍）", legIso:"移除時孤立的範圍",
  rankComTitle:"社群（點擊聚焦）",
  rankTopSuffix:" — Top 10",
  topnAll:n=>`全部 ${n} 節點`, topnTop:(k,n)=>`前 ${k}/${n}`, catCount:n=>`顯示 ${n} 節點`,
  seedBadge:"種子", funcGroup:"功能群", systemSuffix:"",
  tIndeg:"被依賴數（簡單統計）", tIndegVal:(v,N,r)=>`${v}（共 ${N} 中第 ${r} 位）`,
  tReach:"影響範圍（遞移）", tReachVal:v=>`${v} 個套件`,
  tBtw:"中介中心性", tBtwVal:(v,r)=>`${v}（第 ${r} 位）`, tPr:"PageRank", tCom:"社群",
  cutMain:cl=>{const p=cl>=10?`<b>${cl} 個</b>套件將一併從主網路中孤立，影響範圍尤其廣`:cl>=3?`<b>${cl} 個</b>套件將從主網路中孤立`:`孤立範圍僅 <b>${cl} 個</b>套件，屬局部影響，但仍是結構上的要害`;return `這是網路的<b>切斷點</b>。若此套件無法使用，${p}（圖中以黃色標示）。`;},
  cutList:(head,more)=>`<div class="diag-cut"><b>孤立範圍：</b> ${head}${more?` 其他 ${more} 項`:""}</div>`,
  cutReco:"<b>集中風險評估：</b> 建議優先監控。<b>採用·支援決策：</b> 建議事先確認是否有替代路徑。",
  bridgeMain:(rin,rbt,gap)=>{const g=gap>=100?`兩指標的排名差達 ${gap}，排名乖離尤為顯著。`:gap>=30?`兩指標的排名差 ${gap} 較大。`:"";return `相較於被依賴數（第 ${rin} 位），其中介中心性明顯較高（<b>第 ${rbt} 位</b>）。${g}它位於依賴路徑的要衝（<b>橋接</b>），故障時可能切斷多個套件群之間的依賴路徑。此類型以簡單統計難以發現。`;},
  bridgeReco:"<b>採用決策：</b> 建議確認維護狀況與更新頻率。<b>支援決策：</b> 容易被忽略的支援對象候選。",
  foundMain:(indeg,rin,impact,N)=>{const sh=impact/N;const reach=sh>=0.25?`波及分析對象網路整體約 ${Math.round(sh*100)}%（${impact} 個套件）`:`遞移波及 ${impact} 個套件`;return `被依賴數 ${indeg}（整體第 ${rin} 位）的<b>基礎型</b>套件。若停止維護或出現漏洞，影響會${reach}。此類型以簡單統計也能發現。`;},
  foundReco:"<b>採用決策：</b> 廣泛使用的標準選項。<b>集中風險評估：</b> 依賴集中於單點的典型案例，須留意維護的延續性。",
  isoMain:"在此資料範圍內未觀測到與其他套件的依賴關係（其依賴在收集範圍外，或為獨立套件）。",
  normMain:(rin,rbt)=>`未偵測到結構上的特異性（被依賴第 ${rin} 位·中介第 ${rbt} 位）。在依賴結構上處於標準位置，確認各項指標即可。`,
  evidence:'解釋規則基於 SNA 指標的標準解讀（整理於 Chen et al. 2022 的綜述）與依賴網路研究的成果（Decan et al. 2019）（規則表見 README）。',
  comTitle:cid=>`社群 ${cid}`, comNodes:"節點數", comInEdges:"內部邊數", comDensity:"內部密度", comAvgIn:"平均被依賴數",
  comTop:"<b>代表節點（PageRank 前列）：</b> ",
  comDesc:"社群對應依賴相對密集的<b>功能群</b>。",
  comReco:"<b>採用決策：</b> 替代候選優先在同一社群內尋找。<b>集中風險評估：</b> 故障可能波及範圍的參考。",
  comEvidence:"解釋規則的依據與規則表見 README。", comNone:"無社群資訊",
  eigNote:'<b>※ 參考值</b>：依賴網路近乎無環（DAG），特徵向量中心性的迭代計算容易退化（值集中至依賴終端 sink），排名大幅斷裂即因此。診斷請使用被依賴數·中介·PageRank。<b>「此指標不適合依賴網路」本身就是 RQ2 的發現</b>。',
  spearman:sp=>`Spearman ρ: 被依賴×中介=${sp.indeg_vs_btw} / ×PageRank=${sp.indeg_vs_pagerank} / ×特徵向量=${sp.indeg_vs_eigenvector}（越遠離 1.0，SNA 獨有的資訊越多）`,
  divBridge:(id,rin,rbt,indeg,btw)=>`<b>${id}</b> — 被依賴第 ${rin} 位 → 中介第 <b>${rbt}</b> 位 <span class="muted">(indeg=${indeg}, btw=${btw}) 橋接型</span>`,
  divFound:(id,rin,impact)=>`<b style="color:#2C5F94">${id}</b> — 被依賴第 ${rin} 位·影響範圍 ${impact} <span class="muted">基礎型（簡單統計也可見）</span>`,
  divNone:"此領域無顯著的乖離節點", comRowNote:top=>top?`(${top})`:"",
  scX:"被依賴數（簡單統計）→", scY:"中介中心性（SNA）→", scHint:"← 左上 = 被依賴少但中介高（簡單統計看不見的要衝·RQ3）",
  tipClick:" — 點擊顯示診斷與聚焦", tipCat:"分類", tipCom:"社群", tipIndeg:"被依賴", tipOut:"依賴", tipReach:"影響範圍", tipBtw:"中介",
  metaTitle:l=>`可重現資訊（${l}）`, metaFetch:"取得日", metaSrc:"資料來源", metaRate:"種子成功率", metaScale:"規模",
  metaNode:"節點", metaEdge:"邊", metaDensity:"密度", metaComp:"弱連通分量", metaMod:"模組度", metaCom:"社群",
  metaSeed:"隨機 seed", metaSeedUse:"（用於佈局·社群偵測）", metaTime:"指標處理時間", metaBtw:"中介", metaTotal:"總計", metaGen:"生成時間",
  metaDet:"診斷由確定性規則生成（不使用 AI） / 顯示佈局依顯示集合確定性重算（初值＝預計算座標·迭代固定·無隨機）",
 },
 zhHans: {
  h1main:"OSS 依赖网络分析演示 v2",
  h1sub:"— DSS 型分析支持系统（研究用原型）",
  headerHint:'边的方向：依赖方 → 被依赖方。节点大小·颜色 = 所选指标。⚠ = 切断点（移除会导致其他节点孤立）。点击节点即在右上显示诊断。',
  gDomain:"领域", gView:"视图", gMetric:"指标", gSearch:"搜索·分类", gTopn:"显示数", gLang:"语言",
  comBtn:"社群着色", comBtnTitle:"按 Louvain 法检测的社群着色",
  vNet:"网络图", vScatter:"散点图（被依赖×中介）",
  qPlaceholder:"按名称搜索…", catAll:"分类：全部",
  diagTitle:"诊断 — 这意味着什么",
  diagHint:'点击节点（或社群着色时的社群行），显示指标数据与「在决策上意味着什么」的诊断。<br>诊断由节点类型 × 决策场景的对应表确定性生成（不使用 AI·可复现）。',
  divTitle:'排名乖离 — 简单统计看不见的「要冲」（RQ3）',
  legNormal:"普通节点", legSeed:"种子（分析起点）", legCut:"切断点 ⚠（点击显示其孤立范围）", legIso:"移除时孤立的范围",
  rankComTitle:"社群（点击聚焦）",
  rankTopSuffix:" — Top 10",
  topnAll:n=>`全部 ${n} 节点`, topnTop:(k,n)=>`前 ${k}/${n}`, catCount:n=>`显示 ${n} 节点`,
  seedBadge:"种子", funcGroup:"功能群", systemSuffix:"",
  tIndeg:"被依赖数（简单统计）", tIndegVal:(v,N,r)=>`${v}（共 ${N} 中第 ${r} 位）`,
  tReach:"影响范围（传递）", tReachVal:v=>`${v} 个软件包`,
  tBtw:"中介中心性", tBtwVal:(v,r)=>`${v}（第 ${r} 位）`, tPr:"PageRank", tCom:"社群",
  cutMain:cl=>{const p=cl>=10?`<b>${cl} 个</b>软件包将一并从主网络中孤立，影响范围尤其广`:cl>=3?`<b>${cl} 个</b>软件包将从主网络中孤立`:`孤立范围仅 <b>${cl} 个</b>软件包，属局部影响，但仍是结构上的要害`;return `这是网络的<b>切断点</b>。若此软件包不可用，${p}（图中以黄色高亮）。`;},
  cutList:(head,more)=>`<div class="diag-cut"><b>孤立范围：</b> ${head}${more?` 其他 ${more} 项`:""}</div>`,
  cutReco:"<b>集中风险评估：</b> 建议优先监控。<b>采用·支持决策：</b> 建议事先确认是否有替代路径。",
  bridgeMain:(rin,rbt,gap)=>{const g=gap>=100?`两指标的排名差达 ${gap}，排名乖离尤为显著。`:gap>=30?`两指标的排名差 ${gap} 较大。`:"";return `相比被依赖数（第 ${rin} 位），其中介中心性明显更高（<b>第 ${rbt} 位</b>）。${g}它位于依赖路径的要冲（<b>桥接</b>），故障时可能切断多个软件包群之间的依赖路径。此类型用简单统计难以发现。`;},
  bridgeReco:"<b>采用决策：</b> 建议确认维护状况与更新频率。<b>支持决策：</b> 容易被忽略的支持对象候选。",
  foundMain:(indeg,rin,impact,N)=>{const sh=impact/N;const reach=sh>=0.25?`波及分析对象网络整体约 ${Math.round(sh*100)}%（${impact} 个软件包）`:`传递波及 ${impact} 个软件包`;return `被依赖数 ${indeg}（整体第 ${rin} 位）的<b>基础型</b>软件包。若停止维护或出现漏洞，影响会${reach}。此类型用简单统计也能发现。`;},
  foundReco:"<b>采用决策：</b> 广泛使用的标准选项。<b>集中风险评估：</b> 依赖集中于单点的典型案例，需留意维护的延续性。",
  isoMain:"在此数据范围内未观测到与其他软件包的依赖关系（其依赖在收集范围外，或为独立软件包）。",
  normMain:(rin,rbt)=>`未检测到结构上的特异性（被依赖第 ${rin} 位·中介第 ${rbt} 位）。在依赖结构上处于标准位置，确认各项指标即可。`,
  evidence:'解释规则基于 SNA 指标的标准解读（整理于 Chen et al. 2022 的综述）与依赖网络研究的成果（Decan et al. 2019）（规则表见 README）。',
  comTitle:cid=>`社群 ${cid}`, comNodes:"节点数", comInEdges:"内部边数", comDensity:"内部密度", comAvgIn:"平均被依赖数",
  comTop:"<b>代表节点（PageRank 前列）：</b> ",
  comDesc:"社群对应依赖相对密集的<b>功能群</b>。",
  comReco:"<b>采用决策：</b> 替代候选优先在同一社群内寻找。<b>集中风险评估：</b> 故障可能波及范围的参考。",
  comEvidence:"解释规则的依据与规则表见 README。", comNone:"无社群信息",
  eigNote:'<b>※ 参考值</b>：依赖网络近乎无环（DAG），特征向量中心性的迭代计算容易退化（值集中到依赖终端 sink），排名大幅断裂即因此。诊断请使用被依赖数·中介·PageRank。<b>「该指标不适合依赖网络」本身就是 RQ2 的发现</b>。',
  spearman:sp=>`Spearman ρ: 被依赖×中介=${sp.indeg_vs_btw} / ×PageRank=${sp.indeg_vs_pagerank} / ×特征向量=${sp.indeg_vs_eigenvector}（越远离 1.0，SNA 独有的信息越多）`,
  divBridge:(id,rin,rbt,indeg,btw)=>`<b>${id}</b> — 被依赖第 ${rin} 位 → 中介第 <b>${rbt}</b> 位 <span class="muted">(indeg=${indeg}, btw=${btw}) 桥接型</span>`,
  divFound:(id,rin,impact)=>`<b style="color:#2C5F94">${id}</b> — 被依赖第 ${rin} 位·影响范围 ${impact} <span class="muted">基础型（简单统计也可见）</span>`,
  divNone:"该领域无显著的乖离节点", comRowNote:top=>top?`(${top})`:"",
  scX:"被依赖数（简单统计）→", scY:"中介中心性（SNA）→", scHint:"← 左上 = 被依赖少但中介高（简单统计看不见的要冲·RQ3）",
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
  let badges = types.map(t=>`<span class="badge" style="background:${TYPE_INFO[t].color}">${TYPE_INFO[t][lang]}</span>`).join("");
  if (n.seed) badges += `<span class="badge" style="background:#5DA8E8">${S.seedBadge}</span>`;
  if (n.cat) badges += `<span class="badge" style="background:#8FA8C0">${esc(catLabel(n.cat))}</span>`;
  const d = descOf(n);
  const descHtml = d ? `<div class="diag-desc">${esc(d)}</div>` : "";
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
      if (cut.length) texts.push(S.cutList(cut.slice(0,8).map(esc).join(sep), cut.length>8 ? cut.length-8 : 0));
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
  return `<div class="diag-name">${esc(n.label)}</div>${badges}${descHtml}${table}
    ${texts.map(t=>`<div class="diag-text">${t}</div>`).join("")}
    ${recos.length?`<div class="diag-reco">${recos.join("<br>")}</div>`:""}
    <div class="muted" style="margin-top:7px">${S.evidence}</div>`;
}
function diagnoseCom(cid, g){
  const S = T();
  const st = (g.communities||[]).find(c=>c.id===cid);
  if (!st) return `<div class="hint">${S.comNone}</div>`;
  const member = g.nodes.filter(n=>n.com===cid);
  const avgIn = member.length ? (member.reduce((a,n)=>a+n.indeg,0)/member.length).toFixed(1) : 0;
  const sep = lang==="ja" ? "、" : ", ";
  return `<div class="diag-name">${S.comTitle(cid)}</div>
    <span class="badge" style="background:${COLORS[cid%COLORS.length]}; color:#1F2D40">${S.funcGroup}</span>
    <table class="diag-table">
      <tr><td>${S.comNodes}</td><td>${st.n}</td></tr>
      <tr><td>${S.comInEdges}</td><td>${st.m_in}</td></tr>
      <tr><td>${S.comDensity}</td><td>${st.density}</td></tr>
      <tr><td>${S.comAvgIn}</td><td>${avgIn}</td></tr></table>
    <div class="diag-text">${S.comTop}${st.top.map(esc).join(sep)}</div>
    <div class="diag-text">${S.comDesc}</div>
    <div class="diag-reco">${S.comReco}</div>
    <div class="muted" style="margin-top:7px">${S.comEvidence}</div>`;
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
  $("#headerHint").textContent = S.headerHint;
  $("#lblDomain").textContent = S.gDomain; $("#lblView").textContent = S.gView;
  $("#lblMetric").textContent = S.gMetric; $("#lblSearch").textContent = S.gSearch;
  $("#lblTopn").textContent = S.gTopn;
  $("#comBtn").textContent = S.comBtn; $("#comBtn").title = S.comBtnTitle;
  $("#q").placeholder = S.qPlaceholder;
  $("#diagTitle").textContent = S.diagTitle;
  $("#divTitle").textContent = S.divTitle;
  $("#legNormal").textContent = S.legNormal; $("#legSeed").textContent = S.legSeed;
  $("#legCut").textContent = S.legCut; $("#legIso").textContent = S.legIso;
  document.documentElement.lang = HTMLLANG[lang] || lang;
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
    `<button data-m="${m}" class="${m===curM&&!comMode?'on':''}${dis}">${esc(mshort(m))}</button>`).join(" ");
  $("#comBtn").className = (comMode ? "on" : "") + dis;
  document.querySelectorAll("[data-d]").forEach(b => b.onclick = () => {
    curD=b.dataset.d; selected=null; selectedCom=null; topN=0; catFilter="";
    initSlider(); initSearch(); render(); });
  document.querySelectorAll("[data-v]").forEach(b => b.onclick = () => { view=b.dataset.v; render(); });
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
  const W=1000,H=660,L=80,R=40,TM=40,B=70;   // TM = top margin（全局 T() と衝突しないよう改名）
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

function renderSide(g, byId){
  const S = T();
  const comActive = comMode && view==="net";   // 散布図ではコミュニティフォーカスを適用しない
  // 診断カード
  if (comActive && selectedCom!=null){
    $("#diag").innerHTML = diagnoseCom(selectedCom, g);
  } else if (selected && byId[selected]){
    $("#diag").innerHTML = diagnoseNode(byId[selected], g);
  } else {
    $("#diag").innerHTML = `<div class="hint">${S.diagHint}</div>`;
  }
  // ランキング / コミュニティ一覧
  if (comActive){
    $("#rankTitle").textContent = S.rankComTitle;
    const cs = g.communities || [];
    $("#rankList").innerHTML = cs.slice(0,10).map(c =>
      `<div class="rank-row${selectedCom===c.id?' sel':''}" data-com="${c.id}">
        <span class="dot" style="background:${COLORS[c.id%COLORS.length]}"></span>
        <span class="nm">${S.comTitle(c.id)} <span class="muted">${S.comRowNote(esc(c.top[0]||""))}</span></span>
        <span class="bar-bg"><span class="bar-fg" style="width:${100*c.n/g.nodes.length}%"></span></span>
        <span class="val">${c.n}</span></div>`).join("");
    document.querySelectorAll(".rank-row[data-com]").forEach(r => r.onclick = () => {
      const cid = +r.dataset.com;
      selectedCom = (selectedCom===cid) ? null : cid; selected=null; render(); });
  } else {
    $("#rankTitle").textContent = mlab(curM) + S.rankTopSuffix;
    const mx2 = Math.max(...g.nodes.map(n=>n[curM])) || 1;
    const rows = [...g.nodes].sort((a,b)=>b[curM]-a[curM]).slice(0,10);
    const eigNote = curM==="eig"
      ? `<div class="diag-cut" style="background:var(--warnbg);border-left:3px solid #F2C84B;margin:0 0 8px">${S.eigNote}</div>`
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
      `<div class="div-row" data-id="${d.id}">${S.divBridge(esc(d.id), d.rank_indeg, d.rank_btw, d.indeg, d.btw)}</div>`).join("") :
      `<div class="muted">${S.divNone}</div>`) +
    fd.map(d =>
      `<div class="div-row" data-id="${d.id}" style="border-left-color:#2C5F94; background:#EAF4FF">${S.divFound(esc(d.id), d.rank_indeg, d.impact)}</div>`).join("");
  document.querySelectorAll(".div-row[data-id]").forEach(r => r.onclick = () => { selected=r.dataset.id; comMode=false; selectedCom=null; render(); });
  $("#spearman").textContent = S.spearman(g.spearman||{});
}

function render(){
  const g = DATA[curD], byId = Object.fromEntries(g.nodes.map(n=>[n.id,n]));
  drawButtons();
  sliderLabel(g);
  if (view === "scatter") renderScatter(g, byId); else renderNet(g, byId);
  renderSide(g, byId);
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
      const id = cc.dataset.id;
      if (comMode && view==="net"){ selectedCom = (selectedCom===byId[id].com)?null:byId[id].com; selected=null; }
      else { selected = id===selected ? null : id; selectedCom = null; }
      render();
    };
  });
}
// 空白クリックでフォーカス解除（ノード自身のクリックは各ノードのハンドラに任せる）。
// #svg 要素は render で置換されないため一度だけ束縛すれば持続する。
$("#svg").addEventListener("click", e => {
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
