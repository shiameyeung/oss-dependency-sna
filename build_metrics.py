# -*- coding: utf-8 -*-
"""
build_metrics.py — キャッシュからネットワーク生成・SNA 指標計算・分析 JSON 出力

処理内容:
  1. cache/<system>/*.json（collect.py の出力）を合併して有向依存ネットワークを構築
  2. 指標計算: 被依存数 / 影響範囲 / 媒介中心性 / PageRank / 固有ベクトル中心性 /
     密度 / 弱連結成分 / 関節点 / コミュニティ（Louvain）・モジュラリティ
  3. 順位乖離の分析: 単純統計（被依存数）と SNA 指標の順位相関（Spearman）、
     「人気では目立たないが構造上は要」のノード抽出（順位乖離）
  4. レイアウト座標（seed 固定）を付与して output/<system>_metrics.json に保存

再現性: 乱数 seed（レイアウト・コミュニティ検出）と全パラメータを出力 JSON に記録する。
"""

import argparse
import datetime
import json
import pathlib
import time
from collections import deque

import sna_core as sc

HERE = pathlib.Path(__file__).resolve().parent
SEED = 42  # レイアウト・コミュニティ検出の乱数 seed（再現性のため固定）


def load_cache(cache_dir, system):
    """キャッシュからグラフと収集メタ情報を構築する。"""
    cdir = pathlib.Path(cache_dir) / system
    files = sorted(p for p in cdir.glob("*.json") if not p.name.startswith("_"))
    g = sc.DiGraph()
    seeds_ok = []
    seeds_err = []
    fetched_dates = set()
    versions = {}
    for p in files:
        rec = json.loads(p.read_text(encoding="utf-8"))
        if rec.get("status") != "ok":
            seeds_err.append({"package": rec.get("package", p.stem), "error": rec.get("error", "?")})
            continue
        seeds_ok.append(rec["package"].lower())
        versions[rec["package"].lower()] = rec.get("version", "?")
        if rec.get("fetched_at"):
            fetched_dates.add(rec["fetched_at"][:10])
        for n in rec.get("nodes", []):
            g.add_node(n.lower())
        for a, b in rec.get("edges", []):
            g.add_edge(a.lower(), b.lower())
    meta = {
        "seeds_ok": sorted(set(seeds_ok)),
        "seeds_failed": seeds_err,
        "n_seeds_ok": len(set(seeds_ok)),
        "n_seeds_failed": len(seeds_err),
        "success_rate": round(len(set(seeds_ok)) / max(len(set(seeds_ok)) + len(seeds_err), 1), 3),
        "fetched_dates": sorted(fetched_dates),
        "seed_versions": versions,
    }
    return g, meta


def layout_by_components(g, comps, seed):
    """弱連結成分ごとに spring_layout を実行し、キャンバスに詰めて配置する。

    全体を一括でレイアウトすると、孤立成分が反発力で四隅へ飛び、正規化の結果
    主成分が中央に押し潰される（PyPI のように複数成分を持つ領域で顕著）。
    そのため最大成分を上部の主領域に、残りの小成分を下部の帯に並べる。
    sc.spring_layout 自体（検証済み）は変更せず、呼び出し方のみ工夫する。"""
    if len(comps) <= 1:
        return sc.spring_layout(g, seed=seed)

    def subgraph(nodes):
        sub = sc.DiGraph()
        ns = set(nodes)
        for v in nodes:
            sub.add_node(v)
        for a, b in g.edges():
            if a in ns and b in ns:
                sub.add_edge(a, b)
        return sub

    pos = {}
    # 最大成分: 上部の主領域（幅ほぼ全面 × 高さ 80%）
    for v, (x, y) in sc.spring_layout(subgraph(comps[0]), seed=seed).items():
        pos[v] = (0.02 + 0.96 * x, 0.02 + 0.78 * y)
    # 小成分: 下部の帯に等間隔で並べる
    rest = comps[1:]
    cell = 0.92 / len(rest)
    for i, comp in enumerate(rest):
        for v, (x, y) in sc.spring_layout(subgraph(comp), seed=seed).items():
            pos[v] = (0.04 + cell * i + cell * 0.78 * x, 0.875 + 0.105 * y)
    return pos


# --- 機能分類の規則（決定論的・上から順に最初に一致した分類を採用） -------------
# 述語は (名前小文字, 説明文小文字) を受け取る。最後の規則がフォールバック。
# 分類規則自体が DSS アーティファクト設計の一部（README 参照）。
CATEGORY_RULES = {
    "pypi": [
        ("Jupyter・開発環境", lambda n, d: n.startswith(("jupyter", "ipy", "nb")) or n in {
            "notebook", "traitlets", "jedi", "parso", "stack-data", "executing", "asttokens",
            "pure-eval", "decorator", "matplotlib-inline", "prompt-toolkit", "pygments",
            "pexpect", "ptyprocess", "comm", "debugpy", "tornado", "terminado", "send2trash",
            "websocket-client", "widgetsnbextension", "jupyterlab-widgets", "wcwidth"}),
        ("機械学習", lambda n, d: n in {
            "scikit-learn", "xgboost", "lightgbm", "catboost", "torch", "tensorflow", "keras",
            "jax", "jaxlib", "transformers", "optuna", "mlflow", "mlflow-skinny", "shap",
            "imbalanced-learn", "category-encoders", "umap-learn", "hdbscan", "sktime",
            "slicer", "huggingface-hub", "tokenizers", "safetensors", "scikit-base",
            "threadpoolctl", "joblib"} or "machine learning" in d or "deep learning" in d),
        ("統計・時系列", lambda n, d: n in {
            "statsmodels", "pymc", "arviz", "prophet", "pmdarima", "lifelines", "pingouin",
            "patsy", "pytensor", "cmdstanpy", "formulaic", "autograd", "autograd-gamma",
            "interface-meta", "stanio"} or "statistical" in d or "bayesian" in d),
        ("可視化", lambda n, d: n in {
            "matplotlib", "seaborn", "plotly", "bokeh", "altair", "contourpy", "cycler",
            "fonttools", "kiwisolver", "pillow", "imageio", "tifffile", "narwhals",
            "xyzservices", "graphviz"} or "visualization" in d or "plotting" in d),
        ("自然言語処理", lambda n, d: n in {
            "nltk", "spacy", "gensim", "regex", "langcodes", "sentencepiece", "blis", "thinc",
            "preshed", "murmurhash", "cymem", "wasabi", "srsly", "catalogue", "confection",
            "spacy-legacy", "spacy-loggers", "weasel", "cloudpathlib", "smart-open",
            "language-data", "marisa-trie"} or "natural language" in d or " nlp" in d),
        ("データ処理・数値計算", lambda n, d: n in {
            "numpy", "scipy", "pandas", "polars", "pyarrow", "dask", "duckdb", "numba",
            "llvmlite", "sympy", "mpmath", "networkx", "python-dateutil", "pytz", "tzdata",
            "bottleneck", "numexpr", "openpyxl", "h5py", "fsspec", "locket", "partd", "toolz",
            "cloudpickle", "scikit-image", "lazy-loader"} or "dataframe" in d or "array" in d),
        ("Web・通信", lambda n, d: n in {
            "requests", "urllib3", "certifi", "idna", "charset-normalizer", "flask", "jinja2",
            "werkzeug", "itsdangerous", "blinker", "click", "markupsafe", "httpx", "httpcore",
            "anyio", "sniffio", "h11", "websockets"} or "http" in d),
        ("基盤・ユーティリティ", lambda n, d: True),
    ],
    "go": [
        ("Kubernetes 関連", lambda n, d: n.startswith((
            "k8s.io/", "sigs.k8s.io/", "knative.dev/", "github.com/kubernetes",
            "github.com/karmada-io/", "github.com/volcano-sh/", "github.com/kedacore/",
            "github.com/crossplane/", "github.com/google/k8s-", "github.com/cilium/cilium"))),
        ("可観測性・監視", lambda n, d: n.startswith((
            "github.com/prometheus/", "go.opentelemetry.io/", "github.com/grafana/",
            "github.com/jaegertracing/", "github.com/thanos-io/", "github.com/cortexproject/",
            "github.com/victoriametrics/", "github.com/open-telemetry/", "go.opencensus.io",
            "contrib.go.opencensus.io", "github.com/uber/jaeger", "github.com/datadog/",
            "github.com/beorn7/perks", "github.com/cespare/xxhash"))),
        ("ネットワーク・メッシュ", lambda n, d: n.startswith((
            "istio.io/", "github.com/envoyproxy/", "github.com/linkerd/",
            "github.com/coredns/", "github.com/containernetworking/", "github.com/miekg/dns",
            "github.com/nats-io/", "github.com/gorilla/", "google.golang.org/grpc",
            "github.com/soheilhy/", "github.com/grpc-ecosystem/"))),
        ("ストレージ・データベース", lambda n, d: n.startswith((
            "go.etcd.io/", "github.com/rook/", "github.com/longhorn/", "github.com/minio/",
            "github.com/tikv/", "github.com/pingcap/", "github.com/cockroachdb/",
            "vitess.io/", "go.mongodb.org/", "github.com/lib/pq", "github.com/go-sql-driver/",
            "github.com/jackc/", "github.com/redis/", "github.com/dgraph-io/",
            "github.com/syndtr/goleveldb")) or "database" in d),
        ("コンテナ・デプロイ", lambda n, d: n.startswith((
            "github.com/argoproj/", "github.com/fluxcd/", "helm.sh/", "github.com/goharbor/",
            "oras.land/", "github.com/opencontainers/", "github.com/containerd/",
            "github.com/docker/", "github.com/moby/", "github.com/distribution/",
            "github.com/google/go-containerregistry", "github.com/cyphar/filepath-securejoin"))),
        ("クラウド SDK", lambda n, d: n.startswith((
            "github.com/aws/", "cloud.google.com/", "github.com/azure/",
            "google.golang.org/api", "github.com/googleapis/", "github.com/google/go-github",
            "github.com/google/s2a-go", "github.com/googlecloudplatform/"))),
        ("開発・テスト", lambda n, d: n.startswith((
            "github.com/stretchr/", "github.com/google/go-cmp", "github.com/onsi/",
            "go.uber.org/mock", "github.com/golang/mock", "github.com/davecgh/",
            "github.com/pmezard/", "github.com/spf13/", "github.com/golangci/"))),
        ("基盤ライブラリ", lambda n, d: True),
    ],
}


def load_descriptions(cache_dir, system):
    """collect_desc.py の出力（cache/<system>/_descriptions.json）を読み込む。

    各ノードについて日本語簡易説明（ja・原文 summary を基に一括作成した固定データ）と
    レジストリ原文（desc・英語）の両方を返す。デモの言語切替（日/英）で使い分ける。"""
    p = pathlib.Path(cache_dir) / system / "_descriptions.json"
    if not p.exists():
        return {}
    return {k: {"ja": v.get("ja", ""), "en": v.get("desc", "")} for k, v in
            json.loads(p.read_text(encoding="utf-8")).get("entries", {}).items()}


def categorize(system, name, desc):
    for cat, pred in CATEGORY_RULES[system]:
        if pred(name, (desc or "").lower()):
            return cat
    return CATEGORY_RULES[system][-1][0]


def articulation_impact(g, aps):
    """各切断点について「その点を除くと主要部分から孤立するノード集合」を求める。

    定義: 切断点 v が属する弱連結成分から v を除いたとき、最大の残存部分以外に
    属するノード全体（= v が失われた場合に主要ネットワークから切り離される側）。
    v の属する成分内だけで計算する（他の独立成分を誤って「切断された」と
    数えないため）。デモの切断点クリック時のハイライトと診断カードに使う。"""
    impact = {}
    for v in aps:
        comp_v = {v}
        q = deque([v])
        while q:
            c = q.popleft()
            for nb in g.succ[c] | g.pred[c]:
                if nb not in comp_v:
                    comp_v.add(nb)
                    q.append(nb)
        rest = comp_v - {v}
        seen = set()
        parts = []
        for s in rest:
            if s in seen:
                continue
            part_ = {s}
            seen.add(s)
            q = deque([s])
            while q:
                c = q.popleft()
                for nb in g.succ[c] | g.pred[c]:
                    if nb != v and nb in rest and nb not in seen:
                        seen.add(nb)
                        part_.add(nb)
                        q.append(nb)
            parts.append(part_)
        parts.sort(key=len, reverse=True)
        impact[v] = sorted(set().union(*parts[1:])) if len(parts) > 1 else []
    return impact


def community_stats(g, part, pr):
    """コミュニティごとの規模・内部密度・代表ノード（PageRank 上位）を集計する。"""
    stats = []
    for cid in sorted(set(part.values())):
        members = [v for v in g.nodes if part[v] == cid]
        mset = set(members)
        m_in = sum(1 for a, b in g.edges() if a in mset and b in mset)
        n_c = len(members)
        stats.append({
            "id": cid,
            "n": n_c,
            "m_in": m_in,
            "density": round(m_in / (n_c * (n_c - 1)), 4) if n_c > 1 else 0.0,
            "top": sorted(members, key=lambda v: (-pr[v], v))[:3],
        })
    stats.sort(key=lambda s: (-s["n"], s["id"]))
    return stats


def analyze(g, label, domain, collect_meta, system="pypi", descs=None):
    t0 = time.time()
    descs = descs or {}
    nodes = g.nodes
    indeg = sc.in_degree(g)
    outdeg = sc.out_degree(g)
    imp = sc.impact(g)
    t_basic = time.time()
    btw = sc.betweenness_centrality(g)
    t_btw = time.time()
    pr = sc.pagerank(g)
    eig = sc.eigenvector_centrality(g)
    t_cent = time.time()
    aps = sc.articulation_points(g)
    part = sc.louvain_communities(g)
    mod = sc.modularity(g, part)
    comps = sc.weakly_connected_components(g)
    t_comm = time.time()
    pos = layout_by_components(g, comps, seed=SEED)
    t_layout = time.time()

    # --- 順位の乖離分析（単純統計 vs SNA） ---
    r_indeg = sc.simple_ranks(indeg)
    r_btw = sc.simple_ranks(btw)
    r_eig = sc.simple_ranks(eig)
    spearman = {
        "indeg_vs_btw": round(sc.spearman(indeg, btw), 3),
        "indeg_vs_pagerank": round(sc.spearman(indeg, pr), 3),
        "indeg_vs_eigenvector": round(sc.spearman(indeg, eig), 3),
    }
    # 「人気では目立たないが構造上は要」: 媒介順位が被依存順位より 5 位以上上、かつ媒介 > 0
    divergence = []
    for v in nodes:
        if btw[v] > 0 and (r_indeg[v] - r_btw[v]) >= 5:
            divergence.append({
                "id": v, "type": "bridge",
                "rank_indeg": r_indeg[v], "rank_btw": r_btw[v],
                "indeg": indeg[v], "btw": round(btw[v], 4),
                "note": "被依存数では目立たないが、媒介中心性が高い（橋渡し・経路上の要）",
            })
    divergence.sort(key=lambda d: -(d["rank_indeg"] - d["rank_btw"]))
    # 土台型単一障害点: 被依存数上位かつ媒介がほぼゼロ（全員が直接依存する土台）
    foundation = []
    for v in sorted(nodes, key=lambda x: -indeg[x])[:10]:
        if indeg[v] >= 3 and btw[v] <= 1e-6:
            foundation.append({
                "id": v, "type": "foundation",
                "rank_indeg": r_indeg[v], "indeg": indeg[v], "impact": imp[v],
                "note": "多数のパッケージが直接依存する土台（単純統計でも見える単一障害点）",
            })

    # 意味のある切断点（関節点のうち、被依存>0 かつ影響範囲>1 のもの）
    meaningful_aps = sorted(
        v for v in aps if indeg[v] > 0 and imp[v] > 1
    )
    cut_impact = articulation_impact(g, meaningful_aps)
    communities = community_stats(g, part, pr)

    node_rows = []
    cat_count = {}
    for v in nodes:
        dv = descs.get(v, {})
        cat = categorize(system, v, dv.get("en", ""))   # 分類規則のキーワードは英語原文で照合
        cat_count[cat] = cat_count.get(cat, 0) + 1
        node_rows.append({
            "id": v, "label": v,
            "x": round(pos[v][0], 4), "y": round(pos[v][1], 4),
            "indeg": indeg[v], "outdeg": outdeg[v], "impact": imp[v],
            "btw": round(btw[v], 4), "pr": round(pr[v], 4), "eig": round(eig[v], 4),
            "r_in": r_indeg[v], "r_bt": r_btw[v],
            "com": part[v], "art": 1 if v in meaningful_aps else 0,
            "seed": 1 if v in set(collect_meta.get("seeds_ok", [])) else 0,
            "cat": cat, "desc_ja": dv.get("ja", ""), "desc_en": dv.get("en", ""),
        })
    categories = sorted(cat_count.items(), key=lambda kv: (-kv[1], kv[0]))

    def top(d, k=10):
        return [v for v, _ in sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))[:k]]

    return {
        "domain": domain,
        "label": label,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "collect": collect_meta,
        "n": g.n(), "m": g.m(),
        "density": round(sc.density(g), 5),
        "n_components": len(comps),
        "largest_component": len(comps[0]) if comps else 0,
        "modularity": round(mod, 4),
        "n_communities": len(set(part.values())),
        "spearman": spearman,
        "rankings": {
            "indeg": top(indeg), "impact": top(imp), "btw": top(btw),
            "pr": top(pr), "eig": top(eig),
        },
        "divergence": divergence,
        "foundation": foundation,
        "articulation_points": meaningful_aps,
        "cut_impact": cut_impact,
        "communities": communities,
        "categories": [{"name": c, "n": k} for c, k in categories],
        "nodes": node_rows,
        "edges": [{"s": a, "t": b} for a, b in g.edges()],
        "repro": {
            "random_seed": SEED,
            "layout": "fruchterman_reingold(iters=60, per-component packing)",
            "community": "louvain(deterministic)",
            "betweenness": "brandes(normalized, directed)",
            "durations_sec": {
                "basic": round(t_basic - t0, 2),
                "betweenness": round(t_btw - t_basic, 2),
                "pagerank_eigen": round(t_cent - t_btw, 2),
                "community_aps": round(t_comm - t_cent, 2),
                "layout": round(t_layout - t_comm, 2),
                "total": round(t_layout - t0, 2),
            },
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", required=True, choices=["pypi", "go"])
    ap.add_argument("--domain", required=True, help="ds / cn などの領域キー")
    ap.add_argument("--label", required=True)
    ap.add_argument("--cache", default=str(HERE / "cache"))
    ap.add_argument("--out", default=str(HERE / "output"))
    args = ap.parse_args()

    g, meta = load_cache(args.cache, args.system)
    if g.n() == 0:
        raise SystemExit(f"キャッシュが空です: {args.cache}/{args.system}（先に collect.py を実行してください）")
    descs = load_descriptions(args.cache, args.system)
    print(f"=== {args.system}: ノード {g.n()} / エッジ {g.m()} / シード成功 {meta['n_seeds_ok']} 失敗 {meta['n_seeds_failed']} ===")
    result = analyze(g, args.label, args.domain, meta, system=args.system, descs=descs)
    outdir = pathlib.Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    out_path = outdir / f"{args.system}_metrics.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"-> {out_path}")
    print(f"   density={result['density']} components={result['n_components']} "
          f"modularity={result['modularity']} spearman={result['spearman']}")
    print(f"   乖離ノード: {[d['id'] for d in result['divergence'][:5]]}")
    print(f"   処理時間: {result['repro']['durations_sec']}")


if __name__ == "__main__":
    main()
