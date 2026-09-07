#!/usr/bin/env bash
# Stage 4-5 的完整實驗序列。序列執行——GPU 是 Connection Pool 資源，
# 同時只能有一個持有者（.claude/rules/dispatch.md 第 3 條）。
#
#   bash scripts/run_experiments.sh
#
# 每一輪寫一列到 runs/ledger.jsonl。跑完看 runs/ledger.jsonl 或
# python -m thermoforge.report。
set -euo pipefail

PY="${PY:-.venv/Scripts/python}"
EPOCHS="${EPOCHS:-25}"
export PYTHONIOENCODING=utf-8

run() { echo; echo "=== $* ==="; "$PY" -m thermoforge.experiments "$@"; }

# --- 基準：不需要訓練，但走同一條評估路徑 ---------------------------------
run --model mean_field \
    --hypothesis "下限：不看佈局、只預測訓練集平均無因次場能到哪" \
    --change "無（第一輪基準）"

run --model greens_free \
    --hypothesis "自由空間 Green's 疊加在遠離邊界處近似成立" \
    --change "改用 K0 疊加取代平均場"

run --model greens_images \
    --hypothesis "一階鏡像源補掉自由空間解系統性低估的受限誤差" \
    --change "images=0 -> images=1"

# --- 神經代理模型：一次只改一件事 ------------------------------------------
run --model unet --variant direct --epochs "$EPOCHS" --seed 0 \
    --hypothesis "對照組：不做物理無因次化，只用 training fold 統計量標準化" \
    --change "輸入改回原始功率圖 + kt/h/Lx/Ly"

run --model unet --variant norm --epochs "$EPOCHS" --seed 0 \
    --hypothesis "以 theta_ref 與 m*L 無因次化之後，網路只需學形狀函數" \
    --change "direct -> norm（唯一改動：輸入與目標的無因次化）"

run --model unet --variant residual --epochs "$EPOCHS" --seed 0 \
    --hypothesis "學物理基準的殘差比從零學整個場容易，且低估率會降" \
    --change "norm -> residual（唯一改動：目標改成 theta_norm - greens）"

run --model unet --variant residual --epochs "$EPOCHS" --seed 0 --under-weight 3.0 \
    --hypothesis "對低估加權可以把 under_rate 壓下去，代價是整體 MAE 變差" \
    --change "under_weight 1.0 -> 3.0"

# --- 第二顆 seed：改善只在一個 seed 出現就要拒絕 ---------------------------
run --model unet --variant norm --epochs "$EPOCHS" --seed 1 \
    --hypothesis "norm 的分數跨 seed 穩定" --change "seed 0 -> 1"

run --model unet --variant residual --epochs "$EPOCHS" --seed 1 \
    --hypothesis "residual 對 norm 的領先跨 seed 穩定" --change "seed 0 -> 1"

echo
echo "=== 全部完成，帳本在 runs/ledger.jsonl ==="
