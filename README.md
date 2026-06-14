<a name="english"></a>

# OSS Dependency Network SNA — analysis-support system

> **🔗 Live demo: https://shiameyeung.github.io/oss-dependency-sna/**

**English** ｜ [日本語](#日本語) ｜ [繁體中文](#繁體中文) ｜ [简体中文](#简体中文)

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
| `seeds_pypi.json` | ≈183 data-science seeds (community-driven domain) |
| `seeds_go.json` | ≈202 cloud-native seeds (foundation-governed domain) |
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

- **Dataset (latest build · deps.dev API v3 · fetched 2026-06-12–13)**: data-science (PyPI) — **709 nodes / 2,150 edges** from 172/183 seeds resolved (94.0%), 14 weakly-connected components (largest 694), 31 communities, modularity 0.51, density 0.0043; cloud-native (Go) — **591 nodes / 5,922 edges** from 161/201 seeds resolved (80.1%), 1 component, 8 communities, modularity 0.31, density 0.017.
- **Scope cutoff**: ≈180–200 seeds per domain merged with their resolved dependency graphs (seeds + 1-hop resolved deps); no transitive full expansion.
- **Reproducibility**: fetch timestamp, API, resolved versions, random seed (42), and metric timings are recorded
  in every output. `sna_core.py` is deterministic (same input → same output). `run_all.py` also pins
  `PYTHONHASHSEED=0` for child processes (set-iteration order would otherwise shift floating-point summation
  order and move near-tied betweenness ranks by ±1). When running `build_metrics.py` standalone, use
  `PYTHONHASHSEED=0 python3 build_metrics.py ...`.
- **Metrics**: in-degree (simple stat) / reach / betweenness (Brandes) / PageRank / eigenvector /
  density / weakly-connected components / articulation points (cut points) / Louvain communities & modularity.
- **Decision-support output**: the output JSON includes the rank divergence between simple stats and SNA
  (Spearman ρ, bridge nodes, foundation nodes).

## Algorithm validation

Every metric in `sna_core.py` was checked against a networkx implementation on identical input
(2026-05-22 POC, real data embedded in `oss_sna_demo.html`); outputs matched exactly.

<a name="rules-en"></a>

## Diagnosis-card interpretation rules (DSS feature)

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
| Node descriptions | One-line description per node (`collect_desc.py` collects registry originals in English; success rate PyPI 99.6% / Go 94.1%. The Japanese version is fixed data prepared from the originals) | Answer "what is this project" instantly; held as fixed data, not generated at runtime (keeps determinism) |
| Language switch (4 languages) | The 🌐 control (top-right) switches all UI, diagnosis templates, category names, and descriptions across Japanese / English / Traditional Chinese / Simplified Chinese (descriptions: JA = fixed translation / others = registry original). Data and metric values are unchanged | For academic / international venues (e.g. Traditional-Chinese-speaking audiences). Deterministic (no LLM at runtime) |
| Category & search | Incremental name search + functional-category filter (8 per domain). Categories follow deterministic rules by name prefix / name set / description keywords (`CATEGORY_RULES` in `build_metrics.py`) | Explore along a "function" axis orthogonal to structural metrics |
| Focus view | Keep only the selected node + its direct dependencies, fade the rest (ego network); for cut points, highlight the isolated set in yellow | **Fade (opacity 0.07), not hide**: removes irrelevant nodes visually while keeping the node's position in the overall map |
| Static / interactive split | The operation-independent panel (rank divergence) sits as a full-width band at the bottom | Separate interactive info (right) from static info (bottom) |
| Scale adaptation | Top-N filter + deterministic layout recomputation per visible set (FR re-applied, seeded from precomputed coordinates, no randomness) + automatic node-radius adjustment | Keep readability regardless of node count |
| Z-order & collision relaxation | Draw high-metric nodes on top; push the smaller-metric side away on overlap | Keep important nodes always clickable |

## Methodological notes on metrics

- **Eigenvector centrality is treated as reference-only on dependency graphs.** Dependency networks are
  nearly acyclic (DAG); on a DAG the power iteration does not converge uniquely and values depend on the
  iteration count (same in networkx 3.x). A compatible implementation is provided but not used for
  interpretation. → This becomes a metric-selection finding: "in-degree / betweenness / PageRank
  suit dependency-network diagnosis; eigenvector centrality suits networks with cyclic structure."
- **Spearman ρ uses the standard tie-aware definition** (average ranks). Betweenness is 0 for most nodes,
  producing many ties, so ρ changes greatly with tie handling (naive POC ≈0.75 → standard definition ≈0.28–0.31 on the current data: PyPI 0.31, Go 0.28). The
  standard value is the one reported throughout.

## Notes

- Some environments restrict access to deps.dev (proxy / network limits). In that case run `collect.py`
  where access is available, bring the `cache/` over, and continue with `--offline`.
- Uppercase Go module paths (e.g. `github.com/VictoriaMetrics/...`) are accepted by deps.dev as-is.
  Failed fetches are recorded with error details in the cache and aggregated into the success rate
  (useful for assessing collection quality).

---

<a name="日本語"></a>

# OSS 依存ネットワーク分析 ― DSS 型分析支援システム

> **🔗 オンラインデモ: https://shiameyeung.github.io/oss-dependency-sna/**

[English](#english) ｜ **日本語** ｜ [繁體中文](#繁體中文) ｜ [简体中文](#简体中文)

修士研究「社会ネットワーク分析を用いた OSS エコシステム分析支援システムの開発と評価」の
DSS 型分析支援システムの実装。**収集 → ネットワーク生成 → 指標計算 → 可視化** を一括実行する。
解析パイプラインは**決定論的（実行時 LLM 不使用）**で、同一入力からは常に同一出力が得られる。
デモは右上の 🌐 で **4 言語（日本語・English・繁體中文・简体中文）**の切替に対応する。

## 構成

| ファイル | 役割 |
| --- | --- |
| `run_all.py` | 一括実行（オーケストレーター）。`--offline` でキャッシュのみ実行 |
| `collect.py` | deps.dev API v3 から解決済み依存グラフを収集（再開可能・成功率記録） |
| `collect_desc.py` | ノードごとの 1 行説明を収集（PyPI summary／Go はモジュール→GitHub プロジェクト） |
| `seeds_pypi.json` | データサイエンス系シード 約183 件（コミュニティ主導の対照領域） |
| `seeds_go.json` | クラウドネイティブ系シード 約202 件（財団ガバナンスの対照領域） |
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

## 設計上の約束

- **データセット（最新ビルド・deps.dev API v3・取得 2026-06-12〜13）**: データサイエンス系（PyPI）— **709 ノード / 2,150 エッジ**（シード 172/183 解決・94.0%）、弱連結成分 14（最大 694）、コミュニティ 31、モジュラリティ 0.51、密度 0.0043。クラウドネイティブ系（Go）— **591 ノード / 5,922 エッジ**（シード 161/201 解決・80.1%）、成分 1、コミュニティ 8、モジュラリティ 0.31、密度 0.017。
- **規模の打ち切り**: シード各領域 約180〜200 件 + deps.dev の解決済み依存グラフ（シード＋1 ホップ）の合併。推移的全展開はしない。
- **再現性**: 取得日時・API・解決バージョン・乱数 seed（42）・指標処理時間を全出力に記録。
  `sna_core.py` は乱数に依存しない決定論的実装（同一入力 → 同一出力）。
  さらに `run_all.py` は子プロセスに `PYTHONHASHSEED=0` を固定する（set 走査順による
  浮動小数点合算順序の揺れで、媒介中心性の近接同値ノードの順位が ±1 変動するのを防ぐ。
  `build_metrics.py` を単独実行する場合は `PYTHONHASHSEED=0 python3 build_metrics.py ...` とする）。
- **指標**: 被依存数（単純統計）／影響範囲／媒介中心性（Brandes）／PageRank／固有ベクトル／
  密度／弱連結成分／関節点（切断点）／Louvain コミュニティ・モジュラリティ。
- **意思決定支援の出力**: 出力 JSON に「単純統計 vs SNA の順位乖離」（Spearman ρ・橋渡し型ノード・土台型ノード）を含む。

## 算法検証

`sna_core.py` の各指標は、2026-05-22 POC（networkx 実装・`oss_sna_demo.html` に埋込の実データ）と
同一入力での出力一致を確認済み。

<a name="rules-ja"></a>

## 診断カードの解釈ルール（DSS 機能）

デモの診断カードは、ノードの構造型と意思決定場面（利用判断・支援判断・集中リスク把握）の
対応表から**決定論的に**文を生成する（AI 不使用・同一入力 → 同一出力）。
解釈ルール自体が DSS アーティファクト設計の一部である。

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
| ノード説明文 | 全ノードに 1 行説明を付与（`collect_desc.py` でレジストリ原文〔英語〕を収集、取得率 PyPI 99.6%・Go 94.1%。日本語版は原文を基に一括作成した固定データ） | 「このプロジェクトは何か」を即答できるように。実行時の生成はせず固定データとして保持（決定論性の維持） |
| 言語切替（4 言語） | 右上の 🌐 で全 UI・診断テンプレート・分類名・説明文を 日本語／English／繁體中文／简体中文 に切替（説明文: 日=固定翻訳／他言語=レジストリ原文）。データ・指標値は不変、表示文字列のみ切替 | 学会・国際会議（繁体字圏など）での提示に対応。切替は決定論的（実行時 LLM 不使用） |
| 機能分類と検索 | 名前のインクリメンタル検索＋機能分類フィルタ（各領域 8 分類）。分類は名前接頭辞・名称集合・説明文キーワードによる決定論的規則（`build_metrics.py` の `CATEGORY_RULES`） | 構造指標と直交する「機能」の軸で探索できるように |
| フォーカス表示 | 選択ノード＋直接の依存関係のみ残し、他を淡化（エゴネットワーク）。切断点選択時は孤立範囲を黄色表示 | **完全非表示ではなく淡化（opacity 0.07）**: 全体地図内の位置という文脈を保ちつつ無関係なノードを視覚的に排除 |
| 固定情報の分離 | 操作に依存しない順位乖離パネルは下部の全幅バンドに常設 | 対話的情報（右側）と静的情報（下部）の住み分け |
| 規模への適応 | Top-N フィルタ＋表示集合への決定論的レイアウト再計算（FR 再適用・初期値＝事前計算座標・乱数不使用）＋ノード径の自動調整 | 表示数によらず可読性を維持（規模対策） |
| Z オーダーと衝突緩和 | 高指標ノードを最前面に描画し、重なりは指標の小さい側を押し離す | 重要なノードを常にクリック可能に |

## 指標に関する方法論的注意

- **固有ベクトル中心性は依存グラフでは参考値扱いとする**。依存ネットワークはほぼ非巡回（DAG）であり、
  DAG 上では固有ベクトル中心性の power iteration が一意に収束せず、値が反復回数に依存する
  （networkx 3.x も同様）。本パイプラインでは互換実装を提供するが、解釈には用いない。
  → これは「依存ネットワークの診断には次数・媒介・PageRank が適し、固有ベクトル中心性は
  循環構造を持つネットワーク向き」という指標選定の知見として整理できる。
- **Spearman ρ は同値を平均順位で処理する標準的定義**で計算する。媒介中心性は大半のノードで 0 になり
  同値が大量発生するため、同値処理の有無で ρ が大きく変わる（POC の簡易式 ≈0.75 → 標準定義で現データは概ね 0.28〜0.31: PyPI 0.31・Go 0.28）。
  本パイプラインでは標準定義の値を用いる。

## 注意

- 実行環境によっては deps.dev への接続にプロキシ・ネットワーク制限がある。
  その場合は接続可能な環境で `collect.py` のみ実行し、`cache/` を持ち込んで `--offline` で続行する。
- Go モジュールパスの大文字（例: `github.com/VictoriaMetrics/...`）は deps.dev 側でそのまま受理される。
  取得失敗はエラー内容つきで cache に記録され、成功率として集計される（収集品質の確認に利用）。

---

<a name="繁體中文"></a>

# OSS 依賴網路分析 ― DSS 型分析支援系統

> **🔗 線上展示: https://shiameyeung.github.io/oss-dependency-sna/**

[English](#english) ｜ [日本語](#日本語) ｜ **繁體中文** ｜ [简体中文](#简体中文)

碩士研究「運用社會網路分析的 OSS 生態系分析支援系統之開發與評估」的 DSS 型分析支援系統實作。
從公開資料（deps.dev／PyPI）建構 **OSS 依賴網路**，計算社會網路分析（SNA）指標，
並提供自我完備、可重現的 **DSS 型診斷展示**。**收集 → 生成網路 → 計算指標 → 視覺化** 四個階段以單一指令一次執行。
分析流程為**確定性（執行時不使用 LLM）**，相同輸入必得相同輸出。
展示介面以右上角的 🌐 支援 **四語言（日本語・English・繁體中文・简体中文）**切換。

## 組成

| 檔案 | 角色 |
| --- | --- |
| `run_all.py` | 一次執行（協調器）。`--offline` 僅以快取重算 |
| `collect.py` | 從 deps.dev API v3 收集已解析的依賴圖（可中斷續傳・記錄成功率） |
| `collect_desc.py` | 收集每個節點的一行說明（PyPI summary／Go 為模組→GitHub 專案） |
| `seeds_pypi.json` | 資料科學類種子 約183 件（社群主導的對照領域） |
| `seeds_go.json` | 雲原生類種子 約202 件（基金會治理的對照領域） |
| `sna_core.py` | SNA 指標的純 Python + numpy 實作（無外部相依・全為確定性） |
| `build_metrics.py` | 快取 → 有向網路 → 計算指標 → 分析 JSON |
| `make_demo.py` | 產生自我完備的 HTML 展示（離線可用・不依賴 CDN） |

## 執行方法

```bash
# 一般執行（需網路。需可存取 deps.dev API）
python3 run_all.py

# 僅以快取重算（用於確認指標・視覺化的可重現性）
python3 run_all.py --offline
```

執行環境需求: Python 3.9+ / numpy / requests（皆為常見環境既有）。

## 設計上的約束

- **資料集（最新建置・deps.dev API v3・取得 2026-06-12〜13）**: 資料科學類（PyPI）— **709 節點 / 2,150 邊**（種子 172/183 解析・94.0%）、弱連通分量 14（最大 694）、社群 31、模組度 0.51、密度 0.0043。雲原生類（Go）— **591 節點 / 5,922 邊**（種子 161/201 解析・80.1%）、分量 1、社群 8、模組度 0.31、密度 0.017。
- **規模的截斷**: 各領域種子 約180〜200 件 + deps.dev 已解析依賴圖（種子＋1 跳）的合併。不做遞移式全展開。
- **可重現性**: 取得時間・API・解析版本・亂數 seed（42）・指標處理時間皆記錄於所有輸出。
  `sna_core.py` 為不依賴亂數的確定性實作（相同輸入 → 相同輸出）。此外 `run_all.py` 對子行程
  固定 `PYTHONHASHSEED=0`（避免 set 走訪順序造成浮點加總順序變動、使中介中心性近乎同值的節點
  排名出現 ±1 的位移。單獨執行 `build_metrics.py` 時請用 `PYTHONHASHSEED=0 python3 build_metrics.py ...`）。
- **指標**: 被依賴數（簡單統計）／影響範圍／中介中心性（Brandes）／PageRank／特徵向量／
  密度／弱連通分量／關節點（切斷點）／Louvain 社群・模組度。
- **決策支援的輸出**: 輸出 JSON 含「簡單統計 vs SNA 的排名乖離」（Spearman ρ・橋接型節點・基礎型節點）。

## 演算法驗證

`sna_core.py` 的各指標已與 networkx 實作在相同輸入下確認輸出一致（2026-05-22 POC・實資料內嵌於
`oss_sna_demo.html`）。

<a name="rules-zhHant"></a>

## 診斷卡的解釋規則（DSS 功能）

展示的診斷卡，依「節點結構型 × 決策情境（採用判斷・支援判斷・集中風險評估）」的對應表，
**確定性地**生成文字（不使用 AI・相同輸入 → 相同輸出）。解釋規則本身即 DSR 人工物設計的一部分。

| 結構型 | 判定條件 | 決策上的含意（範本要旨） | 解釋依據 |
| --- | --- | --- | --- |
| 切斷點 | 關節點 且 被依賴>0 且 影響範圍>1 | 提示移除時孤立的範圍（預計算 `cut_impact`）；就集中風險評估的觀點建議優先監控 | 圖論中關節點＝移除後連通性喪失的頂點，此標準含意 |
| 橋接型 | btw>0 且 被依賴排名−中介排名 ≥ 5 | 簡單統計看不見的路徑要衝。建議確認維護狀況・容易被忽略的支援對象 | 中介中心性的「路徑控制・仲介」解讀（整理於 Chen et al. 2022 的綜述） |
| 基礎型 | 被依賴前 10 名 且 btw≈0 且 indeg≥3 | 簡單統計也看得見的基礎。標準選擇，但屬單點集中風險的典型 | 次數中心性的直接含意＋依賴網路的遞移影響（Decan et al. 2019） |
| 孤立 | indeg=0 且 outdeg=0 | 收集範圍內無依賴關係 | —（資料範圍的說明） |
| 標準 | 以上皆非 | 無結構上的特異點。確認個別指標即足夠 | —（明示未偵測到特異性） |

**定位**: 本對應規則並非新的理論主張，而是**將既有的 SNA 指標解讀，對應到 OSS 決策情境
（採用判斷・支援判斷・集中風險評估）的設計要素**（DSR 人工物設計的一部分）。
「所提供資訊之品質」此評估觀點，對應 DeLone & McLean (2003) 的資訊品質概念。
範本會依數值（孤立規模・排名差・波及比例）將措辭分級，但生成完全是確定性的。
**置換為 LLM 自然語言生成（措辭的彈性化）列為未來課題**，本研究優先重現性與可解釋性。

## 展示的操作設計模式（DSS 的互動設計・皆為確定性）

| 模式 | 內容 | 設計判斷的理由 |
| --- | --- | --- |
| 診斷卡 | 將點選對象的「說明＋指標數據＋意義＋建議＋依據」集中於右上 | 把決策所需資訊集中於一處（DSS 的核心） |
| 節點說明 | 為所有節點附上一行說明（`collect_desc.py` 收集登錄原文〔英文〕，取得率 PyPI 99.6%・Go 94.1%。日文版為依原文一次製作的固定資料） | 讓人立即得知「這個專案是什麼」；以固定資料保存而非執行時生成（維持確定性） |
| 語言切換（4 語言） | 右上 🌐 將全部 UI・診斷範本・分類名・說明切換為 日本語／English／繁體中文／简体中文（說明文: 日＝固定翻譯／其他＝登錄原文）。資料・指標值不變，僅切換顯示文字 | 對應學會・國際會議（繁體字地區等）的展示。切換為確定性（執行時不使用 LLM） |
| 功能分類與搜尋 | 名稱的漸進式搜尋＋功能分類篩選（各領域 8 類）。分類依名稱前綴・名稱集合・說明關鍵字的確定性規則（`build_metrics.py` 的 `CATEGORY_RULES`） | 可沿著與結構指標正交的「功能」軸探索 |
| 聚焦顯示 | 僅保留所選節點＋其直接依賴關係，其餘淡化（自我網路）。選到切斷點時以黃色顯示孤立範圍 | **非完全隱藏而是淡化（opacity 0.07）**: 在保留整體地圖中位置脈絡的同時，視覺上排除無關節點 |
| 固定資訊的分離 | 與操作無關的排名乖離面板常設於下方的全寬橫條 | 互動式資訊（右側）與靜態資訊（下方）的分工 |
| 規模的適應 | Top-N 篩選＋對顯示集合的確定性版面重算（重新套用 FR・初值＝預計算座標・不使用亂數）＋節點半徑自動調整 | 不論顯示數量皆維持可讀性（規模對策） |
| Z 序與重疊緩解 | 將高指標節點繪於最上層，重疊時推開指標較小的一側 | 讓重要節點始終可點選 |

## 指標的方法論注意

- **特徵向量中心性在依賴圖中視為參考值**。依賴網路近乎無環（DAG），在 DAG 上特徵向量中心性的
  power iteration 不會唯一收斂，數值依迭代次數而變（networkx 3.x 亦同）。本流程提供相容實作，
  但不用於解釋。→ 可整理為指標選擇的見解:「依賴網路的診斷適用次數・中介・PageRank，
  特徵向量中心性則適用具循環結構的網路」。
- **Spearman ρ 採用以平均排名處理同名次的標準定義**計算。中介中心性在多數節點為 0、同名次大量發生，
  故同名次處理的有無會使 ρ 大幅變動（POC 的簡易式 ≈0.75 → 標準定義下現有資料約 0.28〜0.31: PyPI 0.31・Go 0.28）。本流程採用標準定義之值。

## 注意

- 部分執行環境對 deps.dev 的連線有代理・網路限制。此時請於可連線的環境僅執行 `collect.py`，
  將 `cache/` 帶入後以 `--offline` 續行。
- Go 模組路徑的大寫（例: `github.com/VictoriaMetrics/...`）會被 deps.dev 直接接受。
  取得失敗會連同錯誤內容記錄於 cache，並彙整為成功率（用於確認收集品質）。

---

<a name="简体中文"></a>

# OSS 依赖网络分析 ― DSS 型分析支持系统

> **🔗 在线演示: https://shiameyeung.github.io/oss-dependency-sna/**

[English](#english) ｜ [日本語](#日本語) ｜ [繁體中文](#繁體中文) ｜ **简体中文**

硕士研究「运用社会网络分析的 OSS 生态系分析支持系统的开发与评估」的 DSS 型分析支持系统实现。
从公开数据（deps.dev／PyPI）构建 **OSS 依赖网络**，计算社会网络分析（SNA）指标，
并提供自包含、可复现的 **DSS 型诊断演示**。**收集 → 生成网络 → 计算指标 → 可视化** 四个阶段以单条命令一次执行。
分析流程是**确定性的（运行时不使用 LLM）**，相同输入必得相同输出。
演示界面通过右上角的 🌐 支持 **四语言（日本語・English・繁體中文・简体中文）**切换。

## 组成

| 文件 | 角色 |
| --- | --- |
| `run_all.py` | 一次执行（编排器）。`--offline` 仅用缓存重算 |
| `collect.py` | 从 deps.dev API v3 收集已解析的依赖图（可中断续传・记录成功率） |
| `collect_desc.py` | 收集每个节点的一行说明（PyPI summary／Go 为模块→GitHub 项目） |
| `seeds_pypi.json` | 数据科学系种子 约183 件（社区主导的对照领域） |
| `seeds_go.json` | 云原生系种子 约202 件（基金会治理的对照领域） |
| `sna_core.py` | SNA 指标的纯 Python + numpy 实现（无外部依赖・全为确定性） |
| `build_metrics.py` | 缓存 → 有向网络 → 计算指标 → 分析 JSON |
| `make_demo.py` | 生成自包含的 HTML 演示（离线可用・不依赖 CDN） |

## 执行方法

```bash
# 常规执行（需联网。需可访问 deps.dev API）
python3 run_all.py

# 仅用缓存重算（用于确认指标・可视化的可复现性）
python3 run_all.py --offline
```

运行环境需求: Python 3.9+ / numpy / requests（均为常见环境已有）。

## 设计上的约束

- **数据集（最新构建・deps.dev API v3・取得 2026-06-12〜13）**: 数据科学系（PyPI）— **709 节点 / 2,150 边**（种子 172/183 解析・94.0%）、弱连通分量 14（最大 694）、社群 31、模块度 0.51、密度 0.0043。云原生系（Go）— **591 节点 / 5,922 边**（种子 161/201 解析・80.1%）、分量 1、社群 8、模块度 0.31、密度 0.017。
- **规模的截断**: 各领域种子 约180〜200 件 + deps.dev 已解析依赖图（种子＋1 跳）的合并。不做传递式全展开。
- **可复现性**: 取得时间・API・解析版本・随机 seed（42）・指标处理时间均记录于所有输出。
  `sna_core.py` 是不依赖随机数的确定性实现（相同输入 → 相同输出）。此外 `run_all.py` 对子进程
  固定 `PYTHONHASHSEED=0`（避免 set 遍历顺序导致浮点加总顺序变动、使中介中心性近乎同值的节点
  排名出现 ±1 的位移。单独执行 `build_metrics.py` 时请用 `PYTHONHASHSEED=0 python3 build_metrics.py ...`）。
- **指标**: 被依赖数（简单统计）／影响范围／中介中心性（Brandes）／PageRank／特征向量／
  密度／弱连通分量／关节点（切断点）／Louvain 社群・模块度。
- **决策支持的输出**: 输出 JSON 含「简单统计 vs SNA 的排名乖离」（Spearman ρ・桥接型节点・基础型节点）。

## 算法验证

`sna_core.py` 的各指标已与 networkx 实现在相同输入下确认输出一致（2026-05-22 POC・实数据内嵌于
`oss_sna_demo.html`）。

<a name="rules-zhHans"></a>

## 诊断卡的解释规则（DSS 功能）

演示的诊断卡，按「节点结构型 × 决策场景（采用判断・支持判断・集中风险评估）」的对应表，
**确定性地**生成文字（不使用 AI・相同输入 → 相同输出）。解释规则本身即 DSR 人工物设计的一部分。

| 结构型 | 判定条件 | 决策上的含义（模板要旨） | 解释依据 |
| --- | --- | --- | --- |
| 切断点 | 关节点 且 被依赖>0 且 影响范围>1 | 提示移除时孤立的范围（预计算 `cut_impact`）；就集中风险评估的观点建议优先监控 | 图论中关节点＝移除后连通性丧失的顶点，此标准含义 |
| 桥接型 | btw>0 且 被依赖排名−中介排名 ≥ 5 | 简单统计看不见的路径要冲。建议确认维护状况・容易被忽略的支持对象 | 中介中心性的「路径控制・中介」解读（整理于 Chen et al. 2022 的综述） |
| 基础型 | 被依赖前 10 名 且 btw≈0 且 indeg≥3 | 简单统计也看得见的基础。标准选择，但属单点集中风险的典型 | 度中心性的直接含义＋依赖网络的传递影响（Decan et al. 2019） |
| 孤立 | indeg=0 且 outdeg=0 | 收集范围内无依赖关系 | —（数据范围的说明） |
| 标准 | 以上皆非 | 无结构上的特异点。确认各项指标即足够 | —（明示未检测到特异性） |

**定位**: 本对应规则并非新的理论主张，而是**将既有的 SNA 指标解读，对应到 OSS 决策场景
（采用判断・支持判断・集中风险评估）的设计要素**（DSR 人工物设计的一部分）。
「所提供信息的质量」这一评估观点，对应 DeLone & McLean (2003) 的信息质量概念。
模板会按数值（孤立规模・排名差・波及比例）将措辞分级，但生成完全是确定性的。
**置换为 LLM 自然语言生成（措辞的灵活化）列为未来课题**，本研究优先复现性与可解释性。

## 演示的操作设计模式（DSS 的交互设计・皆为确定性）

| 模式 | 内容 | 设计判断的理由 |
| --- | --- | --- |
| 诊断卡 | 将点选对象的「说明＋指标数据＋意义＋建议＋依据」集中于右上 | 把决策所需信息集中于一处（DSS 的核心） |
| 节点说明 | 为所有节点附上一行说明（`collect_desc.py` 收集登记原文〔英文〕，取得率 PyPI 99.6%・Go 94.1%。日文版为依原文一次制作的固定数据） | 让人立即得知「这个项目是什么」；以固定数据保存而非运行时生成（维持确定性） |
| 语言切换（4 语言） | 右上 🌐 将全部 UI・诊断模板・分类名・说明切换为 日本語／English／繁體中文／简体中文（说明文: 日＝固定翻译／其他＝登记原文）。数据・指标值不变，仅切换显示文字 | 对应学会・国际会议（繁体字地区等）的展示。切换为确定性（运行时不使用 LLM） |
| 功能分类与搜索 | 名称的增量搜索＋功能分类筛选（各领域 8 类）。分类按名称前缀・名称集合・说明关键字的确定性规则（`build_metrics.py` 的 `CATEGORY_RULES`） | 可沿着与结构指标正交的「功能」轴探索 |
| 聚焦显示 | 仅保留所选节点＋其直接依赖关系，其余淡化（自我网络）。选到切断点时以黄色显示孤立范围 | **非完全隐藏而是淡化（opacity 0.07）**: 在保留整体地图中位置脉络的同时，视觉上排除无关节点 |
| 固定信息的分离 | 与操作无关的排名乖离面板常设于下方的全宽横条 | 交互式信息（右侧）与静态信息（下方）的分工 |
| 规模的适应 | Top-N 筛选＋对显示集合的确定性布局重算（重新应用 FR・初值＝预计算坐标・不使用随机数）＋节点半径自动调整 | 不论显示数量皆维持可读性（规模对策） |
| Z 序与重叠缓解 | 将高指标节点绘于最上层，重叠时推开指标较小的一侧 | 让重要节点始终可点选 |

## 指标的方法论注意

- **特征向量中心性在依赖图中视为参考值**。依赖网络近乎无环（DAG），在 DAG 上特征向量中心性的
  power iteration 不会唯一收敛，数值依迭代次数而变（networkx 3.x 亦同）。本流程提供兼容实现，
  但不用于解释。→ 可整理为指标选择的见解:「依赖网络的诊断适用度数・中介・PageRank，
  特征向量中心性则适用具循环结构的网络」。
- **Spearman ρ 采用以平均排名处理同名次的标准定义**计算。中介中心性在多数节点为 0、同名次大量发生，
  故同名次处理的有无会使 ρ 大幅变动（POC 的简易式 ≈0.75 → 标准定义下现有数据约 0.28〜0.31: PyPI 0.31・Go 0.28）。本流程采用标准定义之值。

## 注意

- 部分运行环境对 deps.dev 的连接有代理・网络限制。此时请在可连接的环境仅执行 `collect.py`，
  将 `cache/` 带入后以 `--offline` 续行。
- Go 模块路径的大写（例: `github.com/VictoriaMetrics/...`）会被 deps.dev 直接接受。
  取得失败会连同错误内容记录于 cache，并汇总为成功率（用于确认收集质量）。

---

License: MIT (see `LICENSE`).
