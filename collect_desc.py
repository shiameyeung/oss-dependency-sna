# -*- coding: utf-8 -*-
"""
collect_desc.py — ネットワーク内全ノードの簡易説明文を公式レジストリから収集する

方針:
  - PyPI: pypi.org JSON API の summary（1 行説明）を取得。
  - Go: モジュールパスを GitHub プロジェクトへ写像し、deps.dev の projects エンド
    ポイントから description（リポジトリ説明）を取得。写像できないモジュールは
    説明なしとして記録する（取得率は技術評価の素材として集計）。
  - 結果は cache/<system>/_descriptions.json に保存（取得日時つき・増分・再開可能）。
    既に取得済みのノードはスキップするため、再実行は差分のみ。
  - 説明文は各レジストリ由来の原文（主に英語）をそのまま保持する（翻訳・生成はしない）。

使い方:
  python3 collect_desc.py --system pypi
  python3 collect_desc.py --system go
"""

import argparse
import datetime
import json
import pathlib
import re
import time
import urllib.parse

import requests

HERE = pathlib.Path(__file__).resolve().parent


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def nodes_in_cache(cache_dir, system):
    """収集キャッシュから全ノード名（小文字）の集合を得る。"""
    names = set()
    for p in sorted((pathlib.Path(cache_dir) / system).glob("*.json")):
        if p.name.startswith("_"):
            continue
        rec = json.loads(p.read_text(encoding="utf-8"))
        if rec.get("status") != "ok":
            continue
        names.update(n.lower() for n in rec.get("nodes", []))
    return names


def fetch_pypi_summary(session, name):
    r = session.get(f"https://pypi.org/pypi/{urllib.parse.quote(name, safe='')}/json", timeout=20)
    if r.status_code != 200:
        return None
    return (r.json().get("info", {}) or {}).get("summary") or None


# Go モジュールパス → GitHub プロジェクトへの写像規則（決定論的・上から順に適用）
GO_PROJECT_RULES = [
    (re.compile(r"^github\.com/([^/]+)/([^/]+)"), lambda m: f"github.com/{m.group(1)}/{m.group(2)}"),
    (re.compile(r"^sigs\.k8s\.io/([^/]+)"), lambda m: f"github.com/kubernetes-sigs/{m.group(1)}"),
    (re.compile(r"^k8s\.io/([^/]+)"), lambda m: f"github.com/kubernetes/{m.group(1)}"),
    (re.compile(r"^golang\.org/x/([^/]+)"), lambda m: f"github.com/golang/{m.group(1)}"),
    (re.compile(r"^google\.golang\.org/grpc"), lambda m: "github.com/grpc/grpc-go"),
    (re.compile(r"^google\.golang\.org/protobuf"), lambda m: "github.com/protocolbuffers/protobuf-go"),
    (re.compile(r"^google\.golang\.org/genproto"), lambda m: "github.com/googleapis/go-genproto"),
    (re.compile(r"^google\.golang\.org/api"), lambda m: "github.com/googleapis/google-api-go-client"),
    (re.compile(r"^cloud\.google\.com/go"), lambda m: "github.com/googleapis/google-cloud-go"),
    (re.compile(r"^go\.uber\.org/([^/]+)"), lambda m: f"github.com/uber-go/{m.group(1)}"),
    (re.compile(r"^go\.etcd\.io/etcd"), lambda m: "github.com/etcd-io/etcd"),
    (re.compile(r"^go\.etcd\.io/bbolt"), lambda m: "github.com/etcd-io/bbolt"),
    (re.compile(r"^go\.opentelemetry\.io/collector"), lambda m: "github.com/open-telemetry/opentelemetry-collector"),
    (re.compile(r"^go\.opentelemetry\.io/contrib"), lambda m: "github.com/open-telemetry/opentelemetry-go-contrib"),
    (re.compile(r"^go\.opentelemetry\.io/otel"), lambda m: "github.com/open-telemetry/opentelemetry-go"),
    (re.compile(r"^istio\.io/"), lambda m: "github.com/istio/istio"),
    (re.compile(r"^helm\.sh/helm"), lambda m: "github.com/helm/helm"),
    (re.compile(r"^knative\.dev/([^/]+)"), lambda m: f"github.com/knative/{m.group(1)}"),
    (re.compile(r"^vitess\.io/vitess"), lambda m: "github.com/vitessio/vitess"),
    (re.compile(r"^gopkg\.in/yaml\."), lambda m: "github.com/go-yaml/yaml"),
    (re.compile(r"^go\.mongodb\.org/mongo-driver"), lambda m: "github.com/mongodb/mongo-go-driver"),
    (re.compile(r"^gonum\.org/v1/gonum"), lambda m: "github.com/gonum/gonum"),
    (re.compile(r"^dario\.cat/mergo"), lambda m: "github.com/darccio/mergo"),
    (re.compile(r"^filippo\.io/edwards25519"), lambda m: "github.com/FiloSottile/edwards25519"),
    (re.compile(r"^oras\.land/oras-go"), lambda m: "github.com/oras-project/oras-go"),
    (re.compile(r"^layeh\.com/radius"), lambda m: "github.com/layeh/radius"),
    (re.compile(r"^lukechampine\.com/blake3"), lambda m: "github.com/lukechampine/blake3"),
]


def go_project_key(module):
    """Go モジュールパス → GitHub プロジェクトキー（写像不能なら None）。"""
    # 末尾のメジャーバージョンサフィックス（/v2 等）は GitHub パスでは除く
    for pat, fn in GO_PROJECT_RULES:
        m = pat.match(module)
        if m:
            key = fn(m)
            return re.sub(r"/v\d+$", "", key)
    return None


def fetch_go_description(session, module):
    key = go_project_key(module)
    if not key:
        return None
    for base in ("https://api.deps.dev/v3/projects/",
                 "https://api.deps.dev/v3alpha/projects/"):
        r = session.get(base + urllib.parse.quote(key, safe=""), timeout=20)
        if r.status_code == 200:
            return r.json().get("description") or None
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", required=True, choices=["pypi", "go"])
    ap.add_argument("--cache", default=str(HERE / "cache"))
    ap.add_argument("--sleep", type=float, default=0.08)
    args = ap.parse_args()

    out_path = pathlib.Path(args.cache) / args.system / "_descriptions.json"
    store = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {"entries": {}}
    entries = store["entries"]

    names = sorted(nodes_in_cache(args.cache, args.system))
    todo = [n for n in names if n not in entries]
    print(f"=== 説明文収集 system={args.system} nodes={len(names)} 未取得={len(todo)} ===")

    session = requests.Session()
    session.headers["User-Agent"] = "oss-sna-pipeline (masters research prototype)"
    fetched = 0
    for name in todo:
        try:
            desc = fetch_pypi_summary(session, name) if args.system == "pypi" \
                else fetch_go_description(session, name)
        except requests.RequestException:
            desc = None
        entries[name] = {"desc": (desc or "").strip()[:200], "fetched_at": now_utc()}
        fetched += 1
        if fetched % 50 == 0:
            out_path.write_text(json.dumps(store, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"  …{fetched}/{len(todo)}")
        time.sleep(args.sleep)

    ok = sum(1 for n in names if entries.get(n, {}).get("desc"))
    store["summary"] = {"total": len(names), "with_desc": ok,
                        "coverage": round(ok / max(len(names), 1), 3), "updated_at": now_utc()}
    out_path.write_text(json.dumps(store, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"=== 完了: {ok}/{len(names)} 件に説明あり（{store['summary']['coverage']*100:.1f}%）===")


if __name__ == "__main__":
    main()
