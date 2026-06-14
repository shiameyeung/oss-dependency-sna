# -*- coding: utf-8 -*-
"""
sna_core.py — 純 Python + numpy による SNA 指標計算ライブラリ（研究用プロトタイプ）

設計方針:
  - 外部依存は numpy のみ（networkx / scipy 不要）。実行環境を選ばず、再現性を確保しやすい。
  - アルゴリズムは networkx と同一の定義・正規化に揃え、数値が一致することを確認済み。
  - すべて決定的（deterministic）: 同じ入力と seed から常に同じ出力を返す。
    （再現性を保証するため、乱数は明示 seed 以外使用しない）

グラフ表現:
  - 有向グラフ。エッジ (a, b) は「a が b に依存する」を意味する。
  - したがって in-degree(b) = b に直接依存するプロジェクト数（被依存数）。

実装指標:
  - in/out degree, 影響範囲（逆向き到達可能集合）, 媒介中心性（Brandes 2001）,
    PageRank, 固有ベクトル中心性, 密度, 弱連結成分, 関節点（Tarjan）,
    コミュニティ検出（Louvain・決定的版）とモジュラリティ, Spearman 順位相関,
    ばねレイアウト（Fruchterman–Reingold）
"""

import math
import random
from collections import deque

import numpy as np


# ---------------------------------------------------------------------------
# グラフ構築ユーティリティ
# ---------------------------------------------------------------------------

class DiGraph:
    """最小限の有向グラフ。succ: 依存先, pred: 依存元。"""

    def __init__(self):
        self.succ = {}   # node -> set(後続 = 依存先)
        self.pred = {}   # node -> set(先行 = 依存元)

    def add_node(self, n):
        self.succ.setdefault(n, set())
        self.pred.setdefault(n, set())

    def add_edge(self, a, b):
        if a == b:
            return
        self.add_node(a)
        self.add_node(b)
        self.succ[a].add(b)
        self.pred[b].add(a)

    @property
    def nodes(self):
        return sorted(self.succ.keys())

    def edges(self):
        for a in sorted(self.succ):
            for b in sorted(self.succ[a]):
                yield (a, b)

    def n(self):
        return len(self.succ)

    def m(self):
        return sum(len(s) for s in self.succ.values())


# ---------------------------------------------------------------------------
# 基本指標
# ---------------------------------------------------------------------------

def in_degree(g):
    """被依存数（直接依存元の数）= 単純統計側の代表指標。"""
    return {v: len(g.pred[v]) for v in g.succ}


def out_degree(g):
    return {v: len(g.succ[v]) for v in g.succ}


def impact(g):
    """影響範囲: v が停止した場合に（推移的に）波及する依存元プロジェクト数。
    依存エッジを逆向きに辿った到達可能集合のサイズ（自身は含めない）。"""
    res = {}
    for v in g.succ:
        seen = {v}
        q = deque([v])
        while q:
            c = q.popleft()
            for p in g.pred[c]:
                if p not in seen:
                    seen.add(p)
                    q.append(p)
        res[v] = len(seen) - 1
    return res


def density(g):
    """有向グラフ密度 m / (n(n-1))。"""
    n = g.n()
    return g.m() / (n * (n - 1)) if n > 1 else 0.0


def weakly_connected_components(g):
    """弱連結成分（向きを無視した連結成分）。大きい順に返す。"""
    seen = set()
    comps = []
    for s in g.nodes:
        if s in seen:
            continue
        comp = {s}
        seen.add(s)
        q = deque([s])
        while q:
            c = q.popleft()
            for nb in g.succ[c] | g.pred[c]:
                if nb not in seen:
                    seen.add(nb)
                    comp.add(nb)
                    q.append(nb)
        comps.append(sorted(comp))
    comps.sort(key=len, reverse=True)
    return comps


# ---------------------------------------------------------------------------
# 媒介中心性（Brandes 2001・無重み・有向・正規化は networkx と同一）
# ---------------------------------------------------------------------------

def betweenness_centrality(g, normalized=True):
    nodes = g.nodes
    bc = dict.fromkeys(nodes, 0.0)
    for s in nodes:
        # 単一始点最短経路（BFS）
        S = []
        P = {v: [] for v in nodes}            # 先行リスト
        sigma = dict.fromkeys(nodes, 0.0)     # 最短経路本数
        sigma[s] = 1.0
        D = {s: 0}
        q = deque([s])
        while q:
            v = q.popleft()
            S.append(v)
            for w in g.succ[v]:
                if w not in D:
                    D[w] = D[v] + 1
                    q.append(w)
                if D[w] == D[v] + 1:
                    sigma[w] += sigma[v]
                    P[w].append(v)
        # 依存度の逆順集計
        delta = dict.fromkeys(nodes, 0.0)
        while S:
            w = S.pop()
            for v in P[w]:
                delta[v] += sigma[v] / sigma[w] * (1 + delta[w])
            if w != s:
                bc[w] += delta[w]
        # 有向グラフでは順序対 (s,t) を 1 回ずつ数えるため、無向のような 1/2 補正は不要
    if normalized:
        n = len(nodes)
        scale = 1.0 / ((n - 1) * (n - 2)) if n > 2 else 1.0
        bc = {v: c * scale for v, c in bc.items()}
    return bc


# ---------------------------------------------------------------------------
# PageRank（power iteration・networkx と同一の定義: α=0.85, L1 正規化）
# ---------------------------------------------------------------------------

def pagerank(g, alpha=0.85, max_iter=200, tol=1e-08):
    nodes = g.nodes
    n = len(nodes)
    if n == 0:
        return {}
    idx = {v: i for i, v in enumerate(nodes)}
    x = np.full(n, 1.0 / n)
    p = np.full(n, 1.0 / n)
    outdeg = np.array([len(g.succ[v]) for v in nodes], dtype=float)
    dangling = outdeg == 0
    # エッジ配列（依存元 -> 依存先 に沿って PR が流れる）
    src = []
    dst = []
    for a in nodes:
        for b in g.succ[a]:
            src.append(idx[a])
            dst.append(idx[b])
    src = np.array(src, dtype=int) if src else np.zeros(0, dtype=int)
    dst = np.array(dst, dtype=int) if dst else np.zeros(0, dtype=int)
    for _ in range(max_iter):
        xlast = x
        contrib = np.where(outdeg > 0, xlast / np.maximum(outdeg, 1), 0.0)
        x = np.zeros(n)
        if len(src):
            np.add.at(x, dst, contrib[src])
        x = alpha * (x + xlast[dangling].sum() * p) + (1 - alpha) * p
        if np.abs(x - xlast).sum() < n * tol:
            break
    return {v: float(x[idx[v]]) for v in nodes}


# ---------------------------------------------------------------------------
# 固有ベクトル中心性（networkx 3.x と同一: (I + A^T) の power iteration, L2 正規化）
#   依存される側（in-link）に中心性が蓄積する。
# ---------------------------------------------------------------------------

def eigenvector_centrality(g, max_iter=1000, tol=1e-06):
    nodes = g.nodes
    n = len(nodes)
    idx = {v: i for i, v in enumerate(nodes)}
    x = np.full(n, 1.0 / n)
    src = []
    dst = []
    for a in nodes:
        for b in g.succ[a]:
            src.append(idx[a])
            dst.append(idx[b])
    src = np.array(src, dtype=int) if src else np.zeros(0, dtype=int)
    dst = np.array(dst, dtype=int) if dst else np.zeros(0, dtype=int)
    for _ in range(max_iter):
        xlast = x.copy()
        x = xlast.copy()               # I の項（networkx 3.x と同じ）
        if len(src):
            np.add.at(x, dst, xlast[src])
        norm = np.linalg.norm(x) or 1.0
        x = x / norm
        if np.abs(x - xlast).sum() < n * tol:
            break
    return {v: float(x[idx[v]]) for v in nodes}


# ---------------------------------------------------------------------------
# 関節点（articulation points・無向化したグラフに対する Tarjan・反復版）
# ---------------------------------------------------------------------------

def articulation_points(g):
    adj = {v: sorted((g.succ[v] | g.pred[v]) - {v}) for v in g.succ}
    visited = set()
    aps = set()
    disc = {}
    low = {}
    for root in sorted(adj):
        if root in visited:
            continue
        # 反復 DFS
        timer = [0]
        stack = [(root, None, iter(adj[root]))]
        visited.add(root)
        disc[root] = low[root] = timer[0]
        timer[0] += 1
        root_children = 0
        while stack:
            v, parent, it = stack[-1]
            advanced = False
            for w in it:
                if w == parent:
                    continue
                if w not in visited:
                    visited.add(w)
                    disc[w] = low[w] = timer[0]
                    timer[0] += 1
                    if v == root:
                        root_children += 1
                    stack.append((w, v, iter(adj[w])))
                    advanced = True
                    break
                else:
                    low[v] = min(low[v], disc[w])
            if not advanced:
                stack.pop()
                if stack:
                    pv = stack[-1][0]
                    low[pv] = min(low[pv], low[v])
                    if pv != root and low[v] >= disc[pv]:
                        aps.add(pv)
        if root_children >= 2:
            aps.add(root)
    return aps


# ---------------------------------------------------------------------------
# コミュニティ検出（Louvain・決定的版）とモジュラリティ
#   - 無向化して計算。ノードは常にソート順に走査し、乱数を使わない（再現性のため）。
# ---------------------------------------------------------------------------

def _louvain_one_level(adj, node2com, com_tot, deg, m2):
    """第1フェーズ: 局所移動。改善があったか返す。"""
    improved = False
    moved = True
    while moved:
        moved = False
        for v in sorted(adj):
            c0 = node2com[v]
            com_tot[c0] -= deg[v]
            nbw = {}
            for w, wt in adj[v].items():
                if w == v:
                    continue
                cw = node2com[w]
                nbw[cw] = nbw.get(cw, 0.0) + wt
            base = nbw.get(c0, 0.0) - com_tot[c0] * deg[v] / m2
            best_c, best_gain = c0, base
            for c in sorted(nbw):
                gain = nbw[c] - com_tot[c] * deg[v] / m2
                if gain > best_gain + 1e-12:
                    best_gain, best_c = gain, c
            node2com[v] = best_c
            com_tot[best_c] += deg[v]
            if best_c != c0:
                moved = True
                improved = True
    return improved


def louvain_communities(g):
    """Louvain 法（決定的）。{node: community_id}（id はサイズ降順で振り直し）を返す。"""
    # 無向重み付き隣接（自己ループなし・重複辺は重み加算）
    adj = {}
    for a, b in g.edges():
        adj.setdefault(a, {})[b] = adj.setdefault(a, {}).get(b, 0.0) + 1.0
        adj.setdefault(b, {})[a] = adj.setdefault(b, {}).get(a, 0.0) + 1.0
    for v in g.succ:
        adj.setdefault(v, {})

    mapping = {v: v for v in adj}          # 元ノード -> 現レベルのスーパーノード
    final = {}
    while True:
        deg = {v: sum(adj[v].values()) + adj[v].get(v, 0.0) for v in adj}
        m2 = sum(deg.values()) or 1.0
        node2com = {v: v for v in adj}
        com_tot = {v: deg[v] for v in adj}
        improved = _louvain_one_level(adj, node2com, com_tot, deg, m2)
        # 元ノードの割当を更新
        mapping = {orig: node2com[sn] for orig, sn in mapping.items()}
        if not improved:
            final = mapping
            break
        # 第2フェーズ: 集約グラフ構築
        new_adj = {}
        for v, nbrs in adj.items():
            cv = node2com[v]
            new_adj.setdefault(cv, {})
            for w, wt in nbrs.items():
                cw = node2com[w]
                new_adj[cv][cw] = new_adj[cv].get(cw, 0.0) + wt
        adj = new_adj
    # コミュニティ id をサイズ降順で 0..k-1 に振り直す
    sizes = {}
    for v, c in final.items():
        sizes[c] = sizes.get(c, 0) + 1
    order = sorted(sizes, key=lambda c: (-sizes[c], str(c)))
    remap = {c: i for i, c in enumerate(order)}
    return {v: remap[c] for v, c in final.items()}


def modularity(g, part):
    """無向化グラフ上のモジュラリティ Q。part: {node: com}。"""
    # 無向辺（重複統合）
    und = set()
    for a, b in g.edges():
        und.add((a, b) if a <= b else (b, a))
    m = len(und)
    if m == 0:
        return 0.0
    deg = {v: 0 for v in g.succ}
    for a, b in und:
        deg[a] += 1
        deg[b] += 1
    lc = {}
    dc = {}
    for a, b in und:
        if part[a] == part[b]:
            lc[part[a]] = lc.get(part[a], 0) + 1
    for v, d in deg.items():
        dc[part[v]] = dc.get(part[v], 0) + d
    q = 0.0
    for c in dc:
        q += lc.get(c, 0) / m - (dc[c] / (2 * m)) ** 2
    return q


# ---------------------------------------------------------------------------
# 順位・順位相関
# ---------------------------------------------------------------------------

def ranks(values):
    """値が大きいほど上位（1位）。同値は平均順位（Spearman 用の標準的処理）。"""
    items = sorted(values.items(), key=lambda kv: (-kv[1], kv[0]))
    raw = {k: i + 1 for i, (k, _) in enumerate(items)}
    # 同値グループに平均順位を与える
    res = {}
    i = 0
    while i < len(items):
        j = i
        while j + 1 < len(items) and items[j + 1][1] == items[i][1]:
            j += 1
        avg = (raw[items[i][0]] + raw[items[j][0]]) / 2.0
        for k in range(i, j + 1):
            res[items[k][0]] = avg
        i = j + 1
    return res


def simple_ranks(values):
    """同値処理なしの単純順位（表示用・1位=最大値）。"""
    items = sorted(values.items(), key=lambda kv: (-kv[1], kv[0]))
    return {k: i + 1 for i, (k, _) in enumerate(items)}


def spearman(values_a, values_b):
    """Spearman 順位相関 ρ（同値は平均順位で処理）。"""
    keys = sorted(set(values_a) & set(values_b))
    if len(keys) < 3:
        return float("nan")
    ra = ranks({k: values_a[k] for k in keys})
    rb = ranks({k: values_b[k] for k in keys})
    va = np.array([ra[k] for k in keys])
    vb = np.array([rb[k] for k in keys])
    if va.std() == 0 or vb.std() == 0:
        return float("nan")
    return float(np.corrcoef(va, vb)[0, 1])


# ---------------------------------------------------------------------------
# ばねレイアウト（Fruchterman–Reingold・numpy 実装・seed 固定で決定的）
# ---------------------------------------------------------------------------

def spring_layout(g, seed=42, iterations=60):
    nodes = g.nodes
    n = len(nodes)
    if n == 0:
        return {}
    idx = {v: i for i, v in enumerate(nodes)}
    rng = np.random.RandomState(seed)
    pos = rng.rand(n, 2)
    E = np.array([[idx[a], idx[b]] for a, b in g.edges()], dtype=int)
    k = math.sqrt(1.0 / n)
    t = 0.1
    dt = t / (iterations + 1)
    for _ in range(iterations):
        disp = np.zeros((n, 2))
        # 反発力（全ペア・行チャンクでメモリ抑制）
        chunk = max(1, min(n, int(4e6 // max(n, 1))))
        for s in range(0, n, chunk):
            e = min(n, s + chunk)
            delta = pos[s:e, None, :] - pos[None, :, :]
            dist = np.sqrt((delta ** 2).sum(axis=-1))
            np.clip(dist, 0.01, None, out=dist)
            force = (k * k) / (dist ** 2)
            for i in range(s, e):
                force[i - s, i] = 0.0
            disp[s:e] += (delta * force[..., None]).sum(axis=1)
        # 引力（エッジ上）
        if len(E):
            d = pos[E[:, 0]] - pos[E[:, 1]]
            dd = np.sqrt((d ** 2).sum(axis=1)).clip(0.01)
            f = (dd ** 2) / k
            att = d * (f / dd)[:, None]
            np.add.at(disp, E[:, 0], -att)
            np.add.at(disp, E[:, 1], att)
        ln = np.sqrt((disp ** 2).sum(axis=1)).clip(0.01)
        pos += disp / ln[:, None] * np.minimum(ln, t)[:, None]
        t -= dt
    # [0.03, 0.97] に正規化
    mn = pos.min(axis=0)
    mx = pos.max(axis=0)
    span = np.where((mx - mn) > 1e-9, mx - mn, 1.0)
    pos = 0.03 + 0.94 * (pos - mn) / span
    return {v: (float(pos[idx[v], 0]), float(pos[idx[v], 1])) for v in nodes}
