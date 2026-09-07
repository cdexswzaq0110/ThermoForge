"""OOF 迴圈的契約。

兩條都是「安靜地給出錯的東西」那一類的防線：

- fold 數對不上 → 空的 fold 會讓 metrics 變成 NaN，而 NaN 在報告裡看起來像
  「這一格沒填」，不像「這次跑錯了」。
- 有列沒被任何 fold 預測到 → OOF 就不是 OOF 了。
"""

import numpy as np
import pytest

from thermoforge.dataset import Dataset, from_layouts
from thermoforge.data.sampler import ID_RANGES, derive_layout, sample_base_layout
from thermoforge.evaluate import run_oof
from thermoforge.solver import solve_layout


def _dataset(n_groups=12, per_group=2, n_folds=3, seed=0) -> Dataset:
    rng = np.random.default_rng(seed)
    layouts, temps, groups = [], [], []
    for g in range(n_groups):
        base = sample_base_layout(rng, ID_RANGES, g, "id")
        for _ in range(per_group):
            lay = derive_layout(base, rng, ID_RANGES)
            _, t = solve_layout(lay, ny=32, nx=32)
            layouts.append(lay)
            temps.append(t)
            groups.append(g)
    ds = from_layouts(layouts, ny=32, nx=32)
    ds.arrays["temperature"] = np.stack(temps).astype(np.float32)
    ds.arrays["base_id"] = np.array(groups, dtype=np.int64)
    ds.arrays["fold"] = np.array(groups, dtype=np.int64) % n_folds
    return ds


class _Constant:
    """每個 fold 回傳 training fold 的平均溫度。夠用來驗迴圈的形狀。"""

    name = "constant"

    def fit(self, train):
        self.value_ = float(train.temperature.mean())

    def predict(self, ds):
        return np.full(ds.power_map.shape, self.value_, dtype=np.float64)


def test_every_row_is_predicted_by_a_model_that_did_not_see_it():
    ds = _dataset(n_folds=3)
    oof, per_fold = run_oof(_Constant, ds, n_folds=3)
    assert oof.shape == ds.temperature.shape
    assert not np.isnan(oof).any()
    assert len(per_fold) == 3
    assert sum(m.n for m in per_fold) == len(ds)


def test_mismatched_fold_count_is_rejected_not_silently_nan():
    """資料只有 3 折卻要求跑 5 折——必須報錯，不能回傳一半是 NaN 的結果。"""
    ds = _dataset(n_folds=3)
    with pytest.raises(ValueError, match="fold"):
        run_oof(_Constant, ds, n_folds=5)


def test_fewer_folds_than_the_data_has_is_also_rejected():
    """反過來也要擋：跑 2 折會讓第 3 折的列一列都沒被預測到。"""
    ds = _dataset(n_folds=3)
    with pytest.raises(ValueError, match="fold"):
        run_oof(_Constant, ds, n_folds=2)
