# -*- coding: utf-8 -*-
"""
run_all.py — 最小パイプライン一括実行（収集 → ネットワーク生成 → 指標計算 → 可視化）

使い方:
  python3 run_all.py                 # 収集から実行（要ネットワーク接続）
  python3 run_all.py --offline      # 既存キャッシュのみで実行（収集スキップ）

出力:
  output/pypi_metrics.json, output/go_metrics.json   … 指標・分析結果
  output/oss_sna_demo_v2.html                        … 自己完結型デモ
  output/run_meta.json                               … 実行メタ（再現性記録）
"""

import argparse
import datetime
import json
import os
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
PY = sys.executable

# 完全再現性のため Python の文字列ハッシュを固定する。
# set の走査順がプロセスごとに変わると浮動小数点の合算順序が変わり、
# 媒介中心性の近接同値ノードの順位が ±1 揺れるため（アルゴリズム自体は決定的）。
ENV = {**os.environ, "PYTHONHASHSEED": "0"}

DOMAINS = [
    # (system, domain key, label, seeds file)
    ("pypi", "ds", "データサイエンス系 (PyPI)", "seeds_pypi.json"),
    ("go",   "cn", "クラウドネイティブ系 (Go)", "seeds_go.json"),
]


def run(cmd):
    print(f"\n$ {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=HERE, env=ENV)
    if r.returncode != 0:
        raise SystemExit(f"失敗: {' '.join(cmd)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="収集をスキップしキャッシュのみ使用")
    ap.add_argument("--refresh", action="store_true", help="キャッシュを無視して再収集")
    args = ap.parse_args()

    t0 = time.time()
    stages = {}

    # 1) 収集（依存グラフ + ノード説明文）
    if not args.offline:
        t = time.time()
        for system, _, _, seeds in DOMAINS:
            cmd = [PY, "collect.py", "--system", system, "--seeds", seeds]
            if args.refresh:
                cmd.append("--refresh")
            run(cmd)
        for system, _, _, _ in DOMAINS:
            run([PY, "collect_desc.py", "--system", system])
        stages["collect_sec"] = round(time.time() - t, 1)
    else:
        stages["collect_sec"] = "skipped (--offline)"

    # 2) ネットワーク生成 + 指標計算
    t = time.time()
    inputs = []
    for system, domain, label, _ in DOMAINS:
        run([PY, "build_metrics.py", "--system", system, "--domain", domain, "--label", label])
        inputs.append(str(HERE / "output" / f"{system}_metrics.json"))
    stages["metrics_sec"] = round(time.time() - t, 1)

    # 3) 可視化
    t = time.time()
    out_html = str(HERE / "output" / "oss_sna_demo_v2.html")
    run([PY, "make_demo.py", "--inputs", *inputs, "--out", out_html])
    stages["visualize_sec"] = round(time.time() - t, 1)

    # 4) 実行メタ（再現性記録）
    meta = {
        "finished_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "python": sys.version.split()[0],
        "python_hash_seed": ENV["PYTHONHASHSEED"],
        "offline": args.offline,
        "stages": stages,
        "total_sec": round(time.time() - t0, 1),
        "outputs": [str(p) for p in sorted((HERE / "output").glob("*"))],
    }
    (HERE / "output" / "run_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n=== 完了 ({meta['total_sec']}s) ===")
    print(json.dumps(meta, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
