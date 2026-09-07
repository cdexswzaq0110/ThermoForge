"""Gate 1 的機械化檢查。

`se-ml-lifecycle` Stage 2：「可用程式重建相同 folds；每列 validation 次數符合預期；
group／time／leakage 單元測試通過」。

其中最重要的一條是 `test_leakage_checker_catches_a_planted_violation`——
**沒看過紅燈的 gate 不算裝好**（繼承自 L0002）。一個永遠回傳「通過」的
leakage 檢查，比沒有檢查更危險，因為它會讓人停止懷疑。
"""

import numpy as np
import pytest

from thermoforge.data.splits import check_no_group_leakage, group_kfold_assign


def _groups(n_groups=60, rows_per_group=4):
    return np.repeat(np.arange(n_groups), rows_per_group)


def test_no_group_appears_in_two_folds():
    groups = _groups()
    folds = group_kfold_assign(groups, n_splits=5, seed=0)
    check_no_group_leakage(groups, folds)


def test_every_row_gets_exactly_one_fold():
    groups = _groups()
    folds = group_kfold_assign(groups, n_splits=5, seed=0)
    assert folds.shape == groups.shape
    assert set(np.unique(folds).tolist()) == {0, 1, 2, 3, 4}


def test_folds_are_reproducible_from_the_seed():
    """Gate 1 要求「可用程式重建相同 folds」——同 seed 必須逐位元相同。"""
    groups = _groups()
    a = group_kfold_assign(groups, n_splits=5, seed=7)
    b = group_kfold_assign(groups, n_splits=5, seed=7)
    np.testing.assert_array_equal(a, b)


def test_different_seed_gives_a_different_assignment():
    groups = _groups()
    a = group_kfold_assign(groups, n_splits=5, seed=1)
    b = group_kfold_assign(groups, n_splits=5, seed=2)
    assert not np.array_equal(a, b)


def test_fold_sizes_are_balanced_with_uneven_group_sizes():
    """group 大小不齊時仍要接近均等，否則 fold 間變異會混入樣本數效應。"""
    rng = np.random.default_rng(0)
    sizes = rng.integers(1, 9, size=80)
    groups = np.repeat(np.arange(80), sizes)
    folds = group_kfold_assign(groups, n_splits=5, seed=0)
    counts = np.bincount(folds, minlength=5)
    assert counts.max() - counts.min() <= 8, counts


def test_leakage_checker_catches_a_planted_violation():
    """種一個違規進去，檢查它真的被擋下來。

    這是本檔存在的理由。gate 的預設失敗模式是靜默放行——只驗證「合法輸入會通過」
    的測試，對一個 `return None` 的假實作也會全綠。
    """
    groups = _groups()
    folds = group_kfold_assign(groups, n_splits=5, seed=0)
    victim = groups[0]
    idx = np.flatnonzero(groups == victim)
    folds[idx[0]] = (folds[idx[0]] + 1) % 5

    with pytest.raises(AssertionError, match="跨了 fold"):
        check_no_group_leakage(groups, folds)


def test_rejects_more_folds_than_groups():
    with pytest.raises(ValueError, match="少於"):
        group_kfold_assign(np.arange(3), n_splits=5)


def test_rejects_mismatched_lengths():
    with pytest.raises(ValueError, match="長度不符"):
        check_no_group_leakage(np.arange(10), np.zeros(9, dtype=int))
