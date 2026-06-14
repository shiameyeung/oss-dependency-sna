# -*- coding: utf-8 -*-
"""
collect.py — deps.dev API からの依存データ収集（再開可能・再現性記録つき）

設計方針:
  - シードは各領域 50〜200 リポジトリ、依存グラフは「シードの解決済み依存グラフ」の
    合併で構成し、推移的な全展開はしない（規模の打ち切り）。
  - 取得結果はシード単位で cache/<system>/<pkg>.json に保存。再実行時は既存キャッシュを
    スキップする（--refresh で強制再取得）。中断・再開に強い。
  - 再現性のため、取得日時（UTC ISO8601）・API・解決バージョンを必ず記録する。
  - 取得成功率をデータ品質の指標として算出するため、失敗もエラー内容つきで
    cache に記録する。

使い方:
  python3 collect.py --system pypi --seeds seeds_pypi.json
  python3 collect.py --system go   --seeds seeds_go.json
"""

import argparse
import datetime
import json
import pathlib
import sys
import time
import urllib.parse

import requests

API = "https://api.deps.dev/v3"
HERE = pathlib.Path(__file__).resolve().parent

# Go の共有依存の打ち切り閾値: この数以上のシードが直接依存するモジュールのみ
# ネットワークに含める（「規模の打ち切り」。PyPI の解決済みグラフ規模
# n≈272 と整合させるための値。再現性のため _collect_meta.json に記録する）。
GO_SHARED_THRESHOLD = 3


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_default_version(session, system, pkg):
    """デフォルト（最新安定）バージョンを取得する。"""
    url = f"{API}/systems/{system}/packages/{urllib.parse.quote(pkg, safe='')}"
    r = session.get(url, timeout=30)
    if r.status_code != 200:
        return None, f"GetPackage HTTP {r.status_code}"
    vers = r.json().get("versions", [])
    for v in vers:
        if v.get("isDefault"):
            return v["versionKey"]["version"], None
    if vers:
        return vers[-1]["versionKey"]["version"], None
    return None, "no versions"


def get_dependency_graph(session, system, pkg, version):
    """解決済み依存グラフ（nodes/edges）を取得する。"""
    url = (f"{API}/systems/{system}/packages/{urllib.parse.quote(pkg, safe='')}"
           f"/versions/{urllib.parse.quote(version, safe='')}:dependencies")
    r = session.get(url, timeout=60)
    if r.status_code != 200:
        return None, f"GetDependencies HTTP {r.status_code}"
    return r.json(), None


def get_go_direct_requirements(session, pkg, version):
    """go.mod の直接要求依存（directDependencies）の名前リストを取得する。

    deps.dev は Go 生態に対し解決済み依存グラフ（:dependencies）を提供しない
    （v3 / v3alpha とも 404 "dependencies not found"）。そのため Go では宣言依存
    （:requirements）を用いて依存ネットワークを構築する。"""
    url = (f"{API}/systems/go/packages/{urllib.parse.quote(pkg, safe='')}"
           f"/versions/{urllib.parse.quote(version, safe='')}:requirements")
    r = session.get(url, timeout=60)
    if r.status_code != 200:
        return None, f"GetRequirements HTTP {r.status_code}"
    go = r.json().get("go") or {}
    direct = [d["name"].lower() for d in go.get("directDependencies", [])]
    return direct, None


def collect_go(seeds, cache_dir, refresh=False, sleep=0.15):
    """Go 依存ネットワーク収集（2 フェーズ・宣言依存ベース）。

    deps.dev は Go の解決済みグラフを提供しないため go.mod の宣言依存（:requirements）を用いる。
    規模の打ち切りとして、ノード集合 N = シード ∪ {GO_SHARED_THRESHOLD 個
    以上のシードが直接依存する共有モジュール} に限定する。各シードについて半径 1 の誘導部分
    グラフ（シード→依存、および依存同士の直接依存）を cache に保存し、build_metrics 側で合併
    する（DiGraph がエッジを集合で重複排除するため、ファイル間の重複エッジは問題ない）。
    PyPI の解決済みグラフとは構成が異なる点は方法上の注記として _collect_meta.json に記録する。"""
    cache = pathlib.Path(cache_dir) / "go"
    cache.mkdir(parents=True, exist_ok=True)
    seed_files = [(p, cache / (p.replace("/", "__") + ".json")) for p in seeds]
    if not refresh and all(f.exists() for _, f in seed_files):
        ok = failed = 0
        for _, f in seed_files:
            st = json.loads(f.read_text(encoding="utf-8")).get("status")
            ok += (st == "ok"); failed += (st != "ok")
        return {"ok": ok, "failed": failed, "skipped_cached": len(seeds), "total_seeds": len(seeds),
                "method": "requirements", "shared_threshold": GO_SHARED_THRESHOLD}

    session = requests.Session()
    session.headers["User-Agent"] = "oss-sna-pipeline (masters research prototype)"
    seedset = {p.lower() for p in seeds}

    # --- フェーズ A: 各シードの既定バージョンと直接依存を取得 ---
    seed_info = {}   # original pkg -> {version, direct(list|None), error}
    freq = {}        # 直接依存モジュール -> それを直接依存するシード数
    for pkg in seeds:
        ver, err = get_default_version(session, "go", pkg)
        if err:
            seed_info[pkg] = {"version": None, "direct": None, "error": err}
            time.sleep(sleep)
            continue
        direct, err2 = get_go_direct_requirements(session, pkg, ver)
        if err2:
            seed_info[pkg] = {"version": ver, "direct": None, "error": err2}
        elif not direct:
            seed_info[pkg] = {"version": ver, "direct": None,
                              "error": "empty requirements (+incompatible/main module; deps.dev に go.mod 依存データなし)"}
        else:
            seed_info[pkg] = {"version": ver, "direct": direct, "error": None}
            for d in set(direct):
                freq[d] = freq.get(d, 0) + 1
        time.sleep(sleep)

    # --- ノード集合 N の決定（規模の打ち切り） ---
    shared = sorted(d for d, c in freq.items() if c >= GO_SHARED_THRESHOLD and d not in seedset)
    N = seedset | set(shared)

    # --- フェーズ B（1 ホップ）: 共有モジュールの直接依存を取得し内部エッジを得る ---
    dep_direct = {pkg.lower(): info["direct"] for pkg, info in seed_info.items() if info["direct"]}
    for mod in shared:
        ver, err = get_default_version(session, "go", mod)
        if err or not ver:
            dep_direct[mod] = []
            time.sleep(sleep)
            continue
        direct, _ = get_go_direct_requirements(session, mod, ver)
        dep_direct[mod] = direct or []
        time.sleep(sleep)

    # --- 各シードの半径 1 誘導部分グラフを cache に保存 ---
    ok = failed = 0
    for pkg in seeds:
        info = seed_info[pkg]
        rec = {"package": pkg, "system": "go", "api": API, "fetched_at": now_utc()}
        if info["direct"] is None:
            rec["status"] = "error"
            if info["version"]:
                rec["version"] = info["version"]
            rec["error"] = info["error"]
            failed += 1
        else:
            plo = pkg.lower()
            sdeps = [d for d in info["direct"] if d in N]
            nodes = {plo} | set(sdeps)
            edges = [[plo, d] for d in sdeps]
            for d in sdeps:  # 内部エッジ（1 ホップ）: 依存同士の直接依存関係
                for d2 in dep_direct.get(d, []):
                    if d2 in nodes and d2 != d:
                        edges.append([d, d2])
            rec.update({"status": "ok", "version": info["version"],
                        "nodes": sorted(nodes), "edges": edges})
            ok += 1
        out = cache / (pkg.replace("/", "__") + ".json")
        out.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        tail = f" ({rec['error']})" if rec.get("error") else f" deps={len(rec.get('edges', []))}"
        print(f"  [{rec['status']:5s}] go:{pkg}{tail}")
    return {"ok": ok, "failed": failed, "skipped_cached": 0, "total_seeds": len(seeds),
            "method": "requirements (declared go.mod deps; deps.dev provides no resolved :dependencies graph for Go)",
            "shared_threshold": GO_SHARED_THRESHOLD, "n_shared_deps": len(shared)}


def collect(system, seeds, cache_dir, refresh=False, sleep=0.15):
    cache = pathlib.Path(cache_dir) / system
    cache.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = "oss-sna-pipeline (masters research prototype)"
    ok = 0
    failed = 0
    skipped = 0
    for pkg in seeds:
        safe_name = pkg.replace("/", "__")
        out = cache / f"{safe_name}.json"
        if out.exists() and not refresh:
            skipped += 1
            continue
        rec = {"package": pkg, "system": system, "api": API, "fetched_at": now_utc()}
        ver, err = get_default_version(session, system, pkg)
        if err:
            rec["status"] = "error"
            rec["error"] = err
            failed += 1
        else:
            graph, err2 = get_dependency_graph(session, system, pkg, ver)
            if err2:
                rec["status"] = "error"
                rec["version"] = ver
                rec["error"] = err2
                failed += 1
            else:
                names = [n["versionKey"]["name"].lower() for n in graph.get("nodes", [])]
                edges = []
                for e in graph.get("edges", []):
                    a = names[e["fromNode"]]
                    b = names[e["toNode"]]
                    if a != b:
                        edges.append([a, b])  # a が b に依存
                rec.update({
                    "status": "ok",
                    "version": ver,
                    "nodes": sorted(set(names)),
                    "edges": edges,
                })
                ok += 1
        out.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  [{rec['status']:5s}] {system}:{pkg}" + (f" ({rec.get('error')})" if rec.get("error") else ""))
        time.sleep(sleep)
    return {"ok": ok, "failed": failed, "skipped_cached": skipped, "total_seeds": len(seeds)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", required=True, choices=["pypi", "go"])
    ap.add_argument("--seeds", required=True, help="シード定義 JSON（seeds_*.json）")
    ap.add_argument("--cache", default=str(HERE / "cache"))
    ap.add_argument("--refresh", action="store_true", help="キャッシュを無視して再取得")
    args = ap.parse_args()

    seeds_def = json.loads(pathlib.Path(args.seeds).read_text(encoding="utf-8"))
    seeds = seeds_def["seeds"]
    print(f"=== 収集開始 system={args.system} seeds={len(seeds)} ===")
    t0 = time.time()
    if args.system == "go":
        stats = collect_go(seeds, args.cache, refresh=args.refresh)
    else:
        stats = collect(args.system, seeds, args.cache, refresh=args.refresh)
    stats["duration_sec"] = round(time.time() - t0, 1)
    stats["finished_at"] = now_utc()
    meta_path = pathlib.Path(args.cache) / args.system / "_collect_meta.json"
    meta_path.write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"=== 完了: {stats} ===")
    if stats["ok"] == 0 and stats["skipped_cached"] == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
