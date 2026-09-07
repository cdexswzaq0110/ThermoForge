"""切分——`se-ml-lifecycle` Gate 1 的核心。

## 兩層切分，兩種用途

| 切分 | 內容 | 用途 | 可以看幾次 |
|---|---|---|---|
| `id-val`（5 個 fold 的 OOF） | 與訓練同分佈 | 調參、比較候選模型 | 無限次 |
| `ood-holdout` | 四個 OOD regime，每個只推一軸 | 最終判定 | **整個專案一次** |

## 為什麼是 GroupKFold 而不是 KFold

同一個 base layout（幾何相同）會配多組操作條件，產生多個樣本。它們的溫度場
高度相關——隨機切分會把兄弟樣本拆到訓練與驗證兩邊，模型只要記住幾何就贏了。

這是本專案唯一的 leakage 管道，因為輸入端沒有「未來欄位」可洩漏。
`tests/test_splits.py` 把它釘成機械化檢查而不是紀律要求。

## 為什麼 OOD holdout 要另外生成而不是從 ID 池裡挑

從 ID 池裡挑「比較極端的樣本」當 OOD，挑出來的仍然在訓練分佈內，
只是落在尾巴——那量到的是尾部表現，不是外推能力。這兩件事的結論方向相反：
尾部表現好可以直接上線，外推能力好才敢用在沒見過的板型上。
"""

from __future__ import annotations

import numpy as np

__all__ = ["group_kfold_assign", "check_no_group_leakage"]


def group_kfold_assign(groups: np.ndarray, n_splits: int = 5, seed: int = 0) -> np.ndarray:
    """回傳每一列的 validation fold 編號（0..n_splits-1）。

    先把 group 依大小遞減排序，再貪婪塞進當下最小的 fold——這讓每個 fold 的
    列數盡量接近。均等不是美觀問題：fold 大小差太多時，fold 間的分數變異
    有一部分來自樣本數而不是模型，Gate 3 的「改善是否大於 fold noise」就判不準。
    """
    groups = np.asarray(groups)
    unique, inverse = np.unique(groups, return_inverse=True)
    if len(unique) < n_splits:
        raise ValueError(f"group 數 {len(unique)} 少於 fold 數 {n_splits}")

    sizes = np.bincount(inverse, minlength=len(unique))
    rng = np.random.default_rng(seed)
    # 先打散，讓大小相同的 group 不會永遠依 id 順序落在同一個 fold。
    order = rng.permutation(len(unique))
    order = order[np.argsort(-sizes[order], kind="stable")]

    fold_of_group = np.empty(len(unique), dtype=np.int64)
    fold_load = np.zeros(n_splits, dtype=np.int64)
    for g in order:
        f = int(np.argmin(fold_load))
        fold_of_group[g] = f
        fold_load[f] += sizes[g]

    return fold_of_group[inverse]


def check_no_group_leakage(groups: np.ndarray, folds: np.ndarray) -> None:
    """任一 group 只能落在一個 fold。違反就丟例外——這條不接受警告。"""
    groups = np.asarray(groups)
    folds = np.asarray(folds)
    if groups.shape != folds.shape:
        raise ValueError("groups 與 folds 長度不符")

    order = np.argsort(groups, kind="stable")
    g_sorted = groups[order]
    f_sorted = folds[order]
    boundaries = np.flatnonzero(np.r_[True, g_sorted[1:] != g_sorted[:-1], True])

    offenders = []
    for start, stop in zip(boundaries[:-1], boundaries[1:]):
        if len(np.unique(f_sorted[start:stop])) > 1:
            offenders.append(g_sorted[start])
    if offenders:
        raise AssertionError(f"{len(offenders)} 個 group 跨了 fold，前五個：{offenders[:5]}")
