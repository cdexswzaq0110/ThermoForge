"""從帳本產生結果表格，並就地更新報告檔案。

    python -m thermoforge.report                       # 印到 stdout
    python -m thermoforge.report --update docs/05-results.md

更新是**就地替換**兩個標記之間的內容：

    <!-- BEGIN generated:results -->
    ...
    <!-- END generated:results -->

## 為什麼不手寫表格

手寫的數字會漂。重跑一次實驗、改一次 seed、換一份資料，文件裡的數字就過期了，
而過期的數字看起來跟正確的數字一模一樣——這是文件最貴的失敗方式。

`.claude/rules/git-workflow.md`：「這次改動讓哪份已填寫的文件失真，就一起改。」
把表格變成產生的，那條規則就不需要靠人記得。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

BEGIN = "<!-- BEGIN generated:results -->"
END = "<!-- END generated:results -->"

#: 顯示名稱。沒列到的 run 照 run_id 顯示。
LABELS = {
    "mean_field_s0": "A — 平均場（下限）",
    "greens_free_s0": "B — Green's 自由空間",
    "greens_images_s0": "B+ — Green's ＋ 一階鏡像（**物理基準**）",
    "unet_direct_s0": "C — U-Net direct（無因次化對照組）",
    "unet_norm_s0": "D — U-Net 無因次化",
    "unet_residual_s0": "E — U-Net 殘差（**champion**）",
    "unet_residual_uw3_s0": "F — E ＋ 低估加權 3×",
}
ORDER = list(LABELS)


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _fmt_candidates(rows: dict[str, dict]) -> str:
    lines = [
        "| 候選 | OOF field MAE | OOF Tmax MAE | Tmax bias | 低估率 | 低估 p95 | 池內 recall@10/60 | 推論 ms/佈局 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    keys = [k for k in ORDER if k in rows] + [k for k in rows if k not in ORDER]
    for k in keys:
        r = rows[k]["result"]
        o = r["oof"]
        lines.append(
            "| {label} | {fm:.3f} | **{tm:.3f}** | {bias:+.3f} | {ur:.1%} | {up:.2f} | "
            "**{rc:.3f} ± {rs:.3f}** | {lat:.2f} |".format(
                label=LABELS.get(k, k),
                fm=o["field_mae"],
                tm=o["tmax_mae"],
                bias=o["tmax_bias"],
                ur=o["under_rate"],
                up=o["under_p95"],
                rc=r["screening_recall_mean"],
                rs=r["screening_recall_std"],
                lat=r["inference_ms_per_layout"],
            )
        )
    return "\n".join(lines)


def _fmt_stability(rows: dict[str, dict]) -> str:
    groups: dict[str, list[tuple[int, dict]]] = {}
    for k, e in rows.items():
        base = k.rsplit("_s", 1)[0]
        seed = int(k.rsplit("_s", 1)[1])
        groups.setdefault(base, []).append((seed, e))
    multi = {k: sorted(v) for k, v in groups.items() if len(v) > 1}
    if not multi:
        return "_只有一顆 seed 的 run，沒有跨 seed 比較。_"

    lines = [
        "| 候選 | seed | OOF Tmax MAE | fold 間標準差 | 池內 recall |",
        "|---|---|---|---|---|",
    ]
    for base, entries in sorted(multi.items()):
        for seed, e in entries:
            r = e["result"]
            lines.append(
                f"| {base} | {seed} | {r['oof']['tmax_mae']:.3f} | "
                f"{r['oof_fold_noise_std']:.4f} | {r['screening_recall_mean']:.3f} ± "
                f"{r['screening_recall_std']:.3f} |"
            )
    return "\n".join(lines)


def _fmt_frozen(entry: dict | None) -> str:
    if entry is None:
        return "_frozen holdout 尚未解凍。_"

    series = {entry["champion"]: entry["ood"], **entry.get("ood_comparisons", {})}
    regimes = list(next(iter(series.values())))
    lines = [
        f"解凍時間 `{entry['created_utc']}`，commit `{entry['git_commit']}`，"
        f"champion `{entry['champion']}`。",
        "",
        "| regime（各推一軸） | " + " | ".join(f"{n} Tmax MAE" for n in series) + " |",
        "|---" * (len(series) + 1) + "|",
    ]
    for r in regimes:
        cells = " | ".join(f"{series[n][r]['tmax_mae']:.3f}" for n in series)
        lines.append(f"| {r} | {cells} |")

    lines += [
        "",
        "| 低估率 | " + " | ".join(f"{n}" for n in series) + " |",
        "|---" * (len(series) + 1) + "|",
    ]
    for r in regimes:
        cells = " | ".join(f"{series[n][r]['under_rate']:.1%}" for n in series)
        lines.append(f"| {r} | {cells} |")

    p = entry["pool_frozen"]
    lines += [
        "",
        f"**pool-frozen（20 個候選池，1200 列）**：recall@10/60 "
        f"**{entry['pool_frozen_recall_mean']:.3f} ± {entry['pool_frozen_recall_std']:.3f}**，"
        f"field MAE {p['field_mae']:.3f} °C，Tmax MAE {p['tmax_mae']:.3f} °C，"
        f"低估率 {p['under_rate']:.1%}。",
    ]
    return "\n".join(lines)


def build(runs_dir: Path) -> str:
    rows = {e["run_id"]: e for e in _load(runs_dir / "ledger.jsonl")}
    frozen = _load(runs_dir / "frozen_ledger.jsonl")

    parts = [
        "### 候選比較（id-val 的 OOF ＋ pool-dev）",
        "",
        _fmt_candidates(rows),
        "",
        "### 跨 seed 穩定性",
        "",
        _fmt_stability(rows),
        "",
        "### Frozen holdout（解凍一次）",
        "",
        _fmt_frozen(frozen[-1] if frozen else None),
    ]
    if len(frozen) > 1:
        parts.append("")
        parts.append(
            f"⚠ **解凍帳本有 {len(frozen)} 列**——holdout 被看過不只一次，"
            "上表只反映最後一次。這件事要在 PR 裡解釋。"
        )
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="從帳本產生結果表格")
    p.add_argument("--runs-dir", type=Path, default=Path("runs"))
    p.add_argument("--update", type=Path, help="就地更新這個檔案的 generated 區塊")
    args = p.parse_args(argv)

    body = build(args.runs_dir)
    if args.update is None:
        print(body)
        return 0

    text = args.update.read_text(encoding="utf-8")
    if BEGIN not in text or END not in text:
        raise SystemExit(f"{args.update} 缺少 {BEGIN} / {END} 標記")
    head, rest = text.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    args.update.write_text(f"{head}{BEGIN}\n\n{body}\n\n{END}{tail}", encoding="utf-8")
    print(f"已更新 {args.update}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
