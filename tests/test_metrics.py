"""指標的行為契約——特別是那些「算得出數字但意義相反」的邊界。"""

import numpy as np
import pytest

from thermoforge.metrics import evaluate_fields, screening_recall_at_k


def _fields(n=32, ny=8, nx=8, seed=0):
    rng = np.random.default_rng(seed)
    return rng.normal(60.0, 8.0, size=(n, ny, nx))


def test_perfect_prediction_scores_zero_everywhere():
    true = _fields()
    m = evaluate_fields(true.copy(), true)
    assert m.field_mae == 0.0 and m.tmax_mae == 0.0
    assert m.under_rate == 0.0 and m.under_p95 == 0.0


def test_uniform_overestimate_has_zero_under_rate():
    """整體高估是**安全**的錯誤方向，低估率必須為 0。"""
    true = _fields()
    m = evaluate_fields(true + 5.0, true)
    assert m.tmax_bias == pytest.approx(5.0)
    assert m.under_rate == 0.0


def test_uniform_underestimate_is_fully_flagged():
    """整體低估必須 100% 被標記——這是這個指標唯一的存在理由。"""
    true = _fields()
    m = evaluate_fields(true - 5.0, true)
    assert m.tmax_bias == pytest.approx(-5.0)
    assert m.under_rate == 1.0
    assert m.under_p95 == pytest.approx(5.0, abs=1e-9)


def test_small_underestimate_within_tolerance_is_not_flagged():
    """低於容忍值的低估不計——求解器自己的離散化誤差就在這個量級。"""
    true = _fields()
    m = evaluate_fields(true - 0.5, true)
    assert m.under_rate == 0.0


def test_screening_recall_is_perfect_for_a_monotone_biased_model():
    """把所有溫度都加 5 度的模型，MAE 很差但篩選能力**完好**。

    這一條就是主要 metric 與誤差 metric 分道揚鑣的地方。量錯了會選錯模型。
    """
    rng = np.random.default_rng(3)
    true_tmax = rng.uniform(50.0, 95.0, size=400)
    mean, std = screening_recall_at_k(true_tmax + 5.0, true_tmax, k=20, pool_size=100, n_pools=50)
    assert mean == 1.0 and std == 0.0


def test_screening_recall_of_random_ranking_is_near_chance():
    rng = np.random.default_rng(4)
    true_tmax = rng.uniform(50.0, 95.0, size=400)
    noise = rng.uniform(50.0, 95.0, size=400)
    mean, _ = screening_recall_at_k(noise, true_tmax, k=20, pool_size=100, n_pools=100)
    assert 0.10 < mean < 0.30, f"隨機排序的召回率應接近 k/pool=0.2，得到 {mean:.3f}"


def test_evaluate_rejects_shape_mismatch():
    with pytest.raises(ValueError):
        evaluate_fields(_fields(n=4), _fields(n=5))


def test_evaluate_rejects_unbatched_input():
    with pytest.raises(ValueError, match="ny, nx"):
        evaluate_fields(np.zeros((8, 8)), np.zeros((8, 8)))
