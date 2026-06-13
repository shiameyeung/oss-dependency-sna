# OSS Dependency Network SNA — analysis-support prototype

> **🔗 Live demo: https://shiameyeung.github.io/oss-dependency-sna/**

**English** ｜ [日本語](#日本語)

A research prototype (master's thesis) that builds **OSS dependency networks** from public data
(deps.dev / PyPI), computes social-network-analysis (SNA) metrics, and provides a self-contained,
reproducible **DSS-style diagnosis demo** with a **4-language switch — Japanese / English / 繁體中文 / 简体中文** (🌐, top-right). It runs the four stages — **collect → build network → compute metrics → visualize** — in
one command. The analysis pipeline is **deterministic (no LLM at runtime)**: the same input always
yields the same output.

## Files

| File | Role |
| --- | --- |
| `run_all.py` | One-shot orchestrator. `--offline` recomputes from cache only |
| `collect.py` | Collect resolved dependency graphs from the deps.dev API v3 (resumable, records success rate) |
| `collect_desc.py` | Collect one-line descriptions per node (PyPI summary / Go → GitHub project) |
| `seeds_pypi.json` | 50 data-science seeds (community-driven domain) |
| `seeds_go.json` | 50 cloud-native seeds (foundation-governed domain) |
| `sna_core.py` | SNA metrics in pure Python + numpy (no external deps, fully deterministic) |
| `build_metrics.py` | cache → directed network → metrics → analysis JSON |
| `make_demo.py` | Generates the self-contained HTML demo (works offline, no CDN) |

## Usage

```bash
# Normal run (needs network access to the deps.dev API)
python3 run_all.py

# Recompute from cache only (to verify reproducibility of metrics / visualization)
python3 run_all.py --offline
```

Requirements: Python 3.9+ / numpy / requests.

## Design commitments

- **Scope cutoff**: 50 seeds per domain merged with their resolved dependency graphs; no transitive full expansion.
- **Reproducibility**: fetch timestamp, API, resolved versions, random seed (42), and metric timings are recorded
  in every output. `sna_core.py` is deterministic (same input → same output). `run_all.py` also pins
  `PYTHONHASHSEED=0` for child processes (set-iteration order would otherwise shift floating-point summation
  order and move near-tied betweenness ranks by ±1). When running `build_metrics.py` standalone, use
  `PYTHONHASHSEED=0 python3 build_metrics.py ...`.
- **Metrics**: in-degree (simple stat) / reach / betweenness (Brandes) / PageRank / eigenvector /
  density / weakly-connected components / articulation points (cut points) / Louvain communities & modularity.
- **RQ3 support**: the output JSON includes the rank divergence between simple stats and SNA
  (Spearman ρ, bridge nodes, foundation nodes).

## Algorithm validation

Every metric in `sna_core.py` was checked against a networkx implementation on identical input
(2026-05-22 POC, real data embedded in `oss_sna_demo.html`); outputs matched exactly.

## Diagnosis-card interpretation rules (DSS feature · RQ3 design element)

The demo's diagnosis card generates text **deterministically** from a table that maps a node's
structural type to decision contexts (adoption / support / concentration-risk). No LLM; same input →
same output. The rule table itself is part of the DSS-artifact design.

| Type | Condition | Decision implication (template gist) | Basis |
| --- | --- | --- | --- |
| Cut point | articulation point & in-degree>0 & reach>1 | shows the set isolated on removal (precomputed `cut_impact`); top priority to monitor for concentration risk | articulation point = vertex whose removal breaks connectivity (graph theory) |
| Bridge | btw>0 & (in-degree rank − betweenness rank) ≥ 5 | a path bottleneck invisible to simple stats; check maintenance, an overlooked support candidate | the "path-control / brokerage" reading of betweenness (organized in Chen et al. 2022) |
| Foundation | top-10 in-degree & btw≈0 & in-degree≥3 | a base visible even to simple stats; standard choice but a textbook concentration point | direct meaning of degree centrality + transitive impact in dependency networks (Decan et al. 2019) |
| Isolated | in-degree=0 & out-degree=0 | no dependency relation within the collected scope | — (scope note) |
| Standard | none of the above | no structural peculiarity; individual metrics suffice | — (absence of peculiarity) |

**Positioning**: these rules are not a new theoretical claim but a **design element that maps established
SNA-metric readings to OSS decision contexts** (part of DSR artifact design). The "quality of presented
information" evaluation lens corresponds to the information-quality concept of DeLone & McLean (2003).
Templates vary their wording by magnitude (isolated size, rank gap, propagation share) but generation is
fully deterministic. **Replacing this with LLM natural-language generation is future work**; this study
prioritizes reproducibility and explainability.

## Demo interaction-design patterns (DSS interaction design · all deterministic)

| Pattern | What | Rationale |
| --- | --- | --- |
| Diagnosis card | Aggregates description + metrics + meaning + recommendation + basis for the clicked target | Put decision-relevant information in one place (the DSS core) |
| Node descriptions | One-line description per node (`collect_desc.py` collects registry originals in English; success rate PyPI 98.9% / Go 95.4%. The Japanese version is fixed data prepared from the originals) | Answer "what is this project" instantly; held as fixed data, not generated at runtime (keeps determinism) |
| Language switch (4 languages) | The 🌐 control (top-right) switches all UI, diagnosis templates, category names, and descriptions across Japanese / English / Traditional Chinese / Simplified Chinese (descriptions: JA = fixed translation / others = registry original). Data and metric values are unchanged | For academic / international venues (e.g. Tamkang University, Taiwan = Traditional Chinese). Deterministic (no LLM at runtime) |
| Category & search | Incremental name search + functional-category filter (8 per domain). Categories follow deterministic rules by name prefix / name set / description keywords (`CATEGORY_RULES` in `build_metrics.py`) | Explore along a "function" axis orthogonal to structural metrics |
| Focus view | Keep only the selected node + its direct dependencies, fade the rest (ego network); for cut points, highlight the isolated set in yellow | **Fade (opacity 0.07), not hide**: removes irrelevant nodes visually while keeping the node's position in the overall map |
| Static / interactive split | The operation-independent RQ3 panel (rank divergence) sits as a full-width band at the bottom | Separate interactive info (right) from static info (bottom) |
| Scale adaptation | Top-N filter + deterministic layout recomputation per visible set (FR re-applied, seeded from precomputed coordinates, no randomness) + automatic node-radius adjustment | Keep readability regardless of node count |
| Z-order & collision relaxation | Draw high-metric nodes on top; push the smaller-metric side away on overlap | Keep important nodes always clickable |

## Methodological notes on metrics (RQ2 discussion)

- **Eigenvector centrality is treated as reference-only on dependency graphs.** Dependency networks are
  nearly acyclic (DAG); on a DAG the power iteration does not converge uniquely and values depend on the
  iteration count (same in networkx 3.x). A compatible implementation is provided but not used for
  interpretation. → For RQ2 this becomes a metric-selection finding: "in-degree / betweenness / PageRank
  suit dependency-network diagnosis; eigenvector centrality suits networks with cyclic structure."
- **Spearman ρ uses the standard tie-aware definition** (average ranks). Betweenness is 0 for most nodes,
  producing many ties, so ρ changes greatly with tie handling (naive POC ≈0.75 → standard 0.293). The
  standard value is used in talks and the paper.

## Notes

- Some environments restrict access to deps.dev (proxy / network limits). In that case run `collect.py`
  where access is available, bring the `cache/` over, and continue with `--offline`.
- Uppercase Go module paths (e.g. `github.com/VictoriaMetrics/...`) are accepted by deps.dev as-is.
  Failed fetches are recorded with error details in the cache and aggregated into the success rate
  (material for the technical evaluation).

---

<a name="日本語"></a>

# OSS 依存ネットワーク分析 最小パイプライン（研究用プロトタイプ）

> **🔗 オンラインデモ: https://shiameyeung.github.io/oss-dependency-sna/**

[English](#oss-dependency-network-sna--analysis-support-prototype) ｜ **日本語**

修士研究「社会ネットワーク分析を用いた OSS エコシステム分析支援システムの開発と評価」の
最小パイプライン実装。**収集 → ネットワーク生成 → 指標計算 → 可視化** を一括実行する。
解析パイプラインは**決定論的（実行時 LLM 不使用）**で、同一入力からは常に同一出力が得られる。
デモは右上の 🌐 で **4 言語（日本語・English・繁體中文・简体中文）**の切替に対応する。

## 構成

| ファイル | 役割 |
| --- | --- |
| `run_all.py` | 一括実行（オーケストレーター）。`--offline` でキャッシュのみ実行 |
| `collect.py` | deps.dev API v3 から解決済み依存グラフを収集（再開可能・成功率記録） |
| `collect_desc.py` | ノードごとの 1 行説明を収集（PyPI summary／Go はモジュール→GitHub プロジェクト） |
| `seeds_pypi.json` | データサイエンス系シード 50 件（コミュニティ主導の対照領域） |
| `seeds_go.json` | クラウドネイティブ系シード 50 件（財団ガバナンスの対照領域） |
| `sna_core.py` | SNA 指標の純 Python + numpy 実装（外部依存なし・全て決定論的） |
| `build_metrics.py` | キャッシュ → 有向ネットワーク → 指標計算 → 分析 JSON |
| `make_demo.py` | 自己完結型 HTML デモ生成（オフライン動作・CDN 依存なし） |

## 実行方法

```bash
# 通常実行（要ネットワーク。deps.dev API へのアクセスが必要）
python3 run_all.py

# キャッシュのみで再計算（指標・可視化の再現性確認に使用）
python3 run_all.py --offline
```

必要環境: Python 3.9+ / numpy / requests（いずれも一般的な環境に既存）。

## 設計上の約束（CLAUDE.md §3 と対応）

- **規模の打ち切り**: シード各領域 50 件 + deps.dev の解決済み依存グラフの合併。推移的全展開はしない。
- **再現性**: 取得日時・API・解決バージョン・乱数 seed（42）・指標処理時間を全出力に記録。
  `sna_core.py` は乱数に依存しない決定論的実装（同一入力 → 同一出力）。
  さらに `run_all.py` は子プロセスに `PYTHONHASHSEED=0` を固定する（set 走査順による
  浮動小数点合算順序の揺れで、媒介中心性の近接同値ノードの順位が ±1 変動するのを防ぐ。
  `build_metrics.py` を単独実行する場合は `PYTHONHASHSEED=0 python3 build_metrics.py ...` とする）。
- **指標**: 被依存数（単純統計）／影響範囲／媒介中心性（Brandes）／PageRank／固有ベクトル／
  密度／弱連結成分／関節点（切断点）／Louvain コミュニティ・モジュラリティ。
- **RQ3 対応**: 出力 JSON に「単純統計 vs SNA の順位乖離」（Spearman ρ・橋渡し型ノード・土台型ノード）を含む。

## 算法検証

`sna_core.py` の各指標は、2026-05-22 POC（networkx 実装・`oss_sna_demo.html` に埋込の実データ）と
同一入力での出力一致を確認済み（検証記録は `进程记录.md` 成果物ログを参照）。

## 診断カードの解釈ルール（DSS 機能・RQ3 の設計要素）

デモの診断カードは、ノードの構造型と意思決定場面（利用判断・支援判断・集中リスク把握）の
対応表から**決定論的に**文を生成する（AI 不使用・同一入力 → 同一出力）。
解釈ルール自体が DSS アーティファクト設計の一部であり、論文の設計章に記載する。

| 構造型 | 判定条件 | 意思決定上の含意（テンプレート要旨） | 解釈の根拠 |
| --- | --- | --- | --- |
| 切断点 | 関節点 かつ 被依存>0 かつ 影響範囲>1 | 喪失時に孤立する範囲（事前計算 `cut_impact`）を提示。集中リスク把握の観点で最優先での監視を推奨 | グラフ理論における関節点＝除去により連結が失われる頂点という標準的含意 |
| 橋渡し型 | btw>0 かつ 被依存順位−媒介順位 ≥ 5 | 単純統計では見えない経路の要衝。保守体制確認・見落とされやすい支援先候補 | 媒介中心性の「経路制御・仲介」解釈（Chen et al. 2022 のレビューに整理されている） |
| 土台型 | 被依存上位 10 位以内 かつ btw≈0 かつ indeg≥3 | 単純統計でも見える基盤。標準的選択だが一点集中リスクの典型例 | 次数中心性の直接的含意＋依存ネットワークの推移的影響（Decan et al. 2019） |
| 孤立 | indeg=0 かつ outdeg=0 | 収集範囲内に依存関係なし | —（データ範囲の説明） |
| 標準 | 上記いずれにも非該当 | 構造上の特異点なし。個別指標の確認で十分と考えられる | —（特異性の不検出を明示） |

**位置づけ**: 本対応規則は新しい理論主張ではなく、**確立された SNA 指標解釈を OSS の意思決定場面
（利用判断・支援判断・集中リスク把握）に対応づけた設計要素**である（DSR におけるアーティファクト設計の一部）。
提示情報の質という評価観点は DeLone & McLean (2003) の情報品質概念に対応する。
テンプレートは数値（孤立規模・順位差・波及割合）に応じて言い回しを段階化するが、生成は完全に決定論的である。
**LLM による自然言語生成への置換（表現の柔軟化）は今後の課題**とし、本研究では再現性と説明可能性を優先する。

## デモの操作設計パターン（DSS のインタラクション設計・いずれも決定論的）

| パターン | 内容 | 設計判断の理由 |
| --- | --- | --- |
| 診断カード | クリック対象の「説明文＋指標データ＋意味＋推奨＋根拠」を右上に集約 | 意思決定に必要な情報を 1 箇所に（DSS の中核） |
| ノード説明文 | 全ノードに 1 行説明を付与（`collect_desc.py` でレジストリ原文〔英語〕を収集、取得率 PyPI 98.9%・Go 95.4%。日本語版は原文を基に一括作成した固定データ） | 「このプロジェクトは何か」を即答できるように。実行時の生成はせず固定データとして保持（決定論性の維持） |
| 言語切替（4 言語） | 右上の 🌐 で全 UI・診断テンプレート・分類名・説明文を 日本語／English／繁體中文／简体中文 に切替（説明文: 日=固定翻訳／他言語=レジストリ原文）。データ・指標値は不変、表示文字列のみ切替 | 学会・国際会議（淡江大学＝繁体等）での提示に対応。切替は決定論的（実行時 LLM 不使用） |
| 機能分類と検索 | 名前のインクリメンタル検索＋機能分類フィルタ（各領域 8 分類）。分類は名前接頭辞・名称集合・説明文キーワードによる決定論的規則（`build_metrics.py` の `CATEGORY_RULES`） | 構造指標と直交する「機能」の軸で探索できるように |
| フォーカス表示 | 選択ノード＋直接の依存関係のみ残し、他を淡化（エゴネットワーク）。切断点選択時は孤立範囲を黄色表示 | **完全非表示ではなく淡化（opacity 0.07）**: 全体地図内の位置という文脈を保ちつつ無関係なノードを視覚的に排除 |
| 固定情報の分離 | 操作に依存しない RQ3 パネル（順位の乖離）は下部の全幅バンドに常設 | 対話的情報（右側）と静的情報（下部）の住み分け |
| 規模への適応 | Top-N フィルタ＋表示集合への決定論的レイアウト再計算（FR 再適用・初期値＝事前計算座標・乱数不使用）＋ノード径の自動調整 | 表示数によらず可読性を維持（規模対策） |
| Z オーダーと衝突緩和 | 高指標ノードを最前面に描画し、重なりは指標の小さい側を押し離す | 重要なノードを常にクリック可能に |

## 指標に関する方法論的注意（RQ2 の論点）

- **固有ベクトル中心性は依存グラフでは参考値扱いとする**。依存ネットワークはほぼ非巡回（DAG）であり、
  DAG 上では固有ベクトル中心性の power iteration が一意に収束せず、値が反復回数に依存する
  （networkx 3.x も同様）。本パイプラインでは互換実装を提供するが、解釈には用いない。
  → RQ2 では「依存ネットワークの診断には次数・媒介・PageRank が適し、固有ベクトル中心性は
  循環構造を持つネットワーク向き」という指標選定の知見として整理できる。
- **Spearman ρ は同値を平均順位で処理する標準的定義**で計算する。媒介中心性は大半のノードで 0 になり
  同値が大量発生するため、同値処理の有無で ρ が大きく変わる（POC の簡易式 ≈0.75 → 標準定義 0.293）。
  以後の発表・論文では標準定義の値を用いる。

## 注意

- 実行環境によっては deps.dev への接続にプロキシ・ネットワーク制限がある。
  その場合は接続可能な環境で `collect.py` のみ実行し、`cache/` を持ち込んで `--offline` で続行する。
- Go モジュールパスの大文字（例: `github.com/VictoriaMetrics/...`）は deps.dev 側でそのまま受理される。
  取得失敗はエラー内容つきで cache に記録され、成功率として集計される（技術評価の素材）。

---

License: MIT (see `LICENSE`).
