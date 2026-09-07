"""設計副駕的行為契約。

用 stub 預測器，不載入權重——這一組測試守的是**副駕怎麼講話**，
不是模型準不準。兩件事分開測，因為它們的失敗方式完全不同：
模型不準是分數問題，副駕在分佈外報一個乾淨的數字是**誠信問題**。
"""

import numpy as np
import pytest

from thermoforge.copilot.answer import answer_query
from thermoforge.copilot.board import load_board
from thermoforge.copilot.query import RuleBasedParser
from thermoforge.data.sampler import check_in_distribution


@pytest.fixture(scope="module")
def board():
    return load_board("configs/reference_board.yaml")


class StubPredictor:
    """回傳一個固定形狀的溫度場。副駕的邏輯不該依賴模型是誰。"""

    name = "stub"

    def __init__(self, peak_rise: float = 40.0) -> None:
        self.peak_rise = peak_rise

    def fit(self, train):  # noqa: ARG002
        return None

    def predict(self, ds):
        n, ny, nx = ds.power_map.shape
        base = ds.t_amb[:, None, None] + np.zeros((n, ny, nx))
        # 讓熱點跟著功率圖走，好讓「換位置會改變排序」這件事成立。
        p = ds.power_map / ds.power_map.reshape(n, -1).max(axis=1)[:, None, None]
        return base + self.peak_rise * p


CAL = {
    "id": {
        "tmax_err_q05": -1.2,
        "tmax_err_q50": 0.05,
        "tmax_err_q95": 1.4,
        "tmax_under_p95": 1.1,
    },
    "ood": {"ood_power": {"tmax_mae": 12.7}},
}


# --- 解析 -----------------------------------------------------------------

def test_parses_a_what_if_on_a_named_component(board):
    """「從 A 拉到 B」必須取 B。取到 A 會得到一個正確計算、但回答了現況的答案。"""
    q = RuleBasedParser().parse("如果把 CPU 從 25.5W 拉到 60W，還安全嗎？", board)
    assert q.action == "what_if"
    assert q.component_name == "CPU"
    assert q.set_power == 60.0
    assert q.unparsed == ()


def test_single_power_number_still_parses(board):
    q = RuleBasedParser().parse("CPU 60W 的話呢", board)
    assert q.set_power == 60.0


def test_parses_an_alias(board):
    q = RuleBasedParser().parse("處理器改成 40 瓦", board)
    assert q.component_name == "CPU" and q.set_power == 40.0


def test_parses_a_limit(board):
    q = RuleBasedParser().parse("熱點不能超過 85 度，現在如何？", board)
    assert q.t_max_limit == 85.0


def test_optimize_intent(board):
    q = RuleBasedParser().parse("幫我把元件重新排一下", board)
    assert q.action == "optimize"


def test_vague_cooling_request_is_reported_not_guessed(board):
    """「風扇加強一點」沒有數字。副駕必須說看不懂，不能自己編一個倍率。"""
    q = RuleBasedParser().parse("風扇加強一點會不會好一些？", board)
    assert q.set_h_conv is None
    assert any("加強散熱" in u for u in q.unparsed)


def test_unknown_component_with_a_number_is_flagged(board):
    q = RuleBasedParser().parse("把顯卡拉到 60W", board)
    assert q.set_power is None
    assert any("沒認出" in u for u in q.unparsed)


# --- 分佈檢查 -------------------------------------------------------------

def test_reference_board_is_in_distribution(board):
    """參考板刻意放在分佈內——這是副駕示範的起點。"""
    assert check_in_distribution(board.to_layout()) == {}


def test_raising_cpu_power_pushes_out_of_distribution(board):
    hot = board.with_power(board.index_of("cpu"), 60.0)
    ood = check_in_distribution(hot.to_layout())
    assert "peak_rise" in ood, ood


# --- 回答 -----------------------------------------------------------------

def test_in_distribution_answer_is_graded_inference_with_an_interval(board):
    q = RuleBasedParser().parse("現在這塊板的熱點多少度？", board)
    a = answer_query(q, board, StubPredictor(), CAL)
    assert a.grade == "推論"
    assert a.t_max_interval is not None
    assert any("推論" in line for line in a.lines)


def test_out_of_distribution_answer_refuses_to_be_used(board):
    q = RuleBasedParser().parse("把 CPU 改成 60W", board)
    a = answer_query(q, board, StubPredictor(), CAL)
    assert a.grade == "未驗證"
    assert any("未驗證" in line for line in a.lines)
    assert any("送求解器" in line or "CFD" in line for line in a.lines)
    assert any("熱點溫升" in line for line in a.lines), "沒有點名是哪一軸出界"


def test_missing_calibration_downgrades_to_unverified(board):
    q = RuleBasedParser().parse("現在這塊板的熱點多少度？", board)
    a = answer_query(q, board, StubPredictor(), calibration=None)
    assert a.grade == "未驗證"


def test_thin_margin_is_flagged_against_the_underestimate_p95(board):
    """餘裕比模型的低估 p95 還小的時候，必須說這個結論不夠穩。"""
    q = RuleBasedParser().parse("現在這塊板的熱點多少度？", board)
    # 讓預測剛好落在上限下方 0.5 度，小於 CAL 的 under_p95 = 1.1
    peak = board.t_max_allowed - board.t_amb - 0.5
    a = answer_query(q, board, StubPredictor(peak_rise=peak), CAL)
    assert 0 < a.margin < CAL["id"]["tmax_under_p95"]
    assert any("不夠穩" in line for line in a.lines)


def test_optimize_reports_solver_confirmed_numbers(board):
    """最佳化的結論必須是求解器確認過的，代理模型只負責排序。"""
    q = RuleBasedParser().parse("幫我重新排一下", board)
    a = answer_query(q, board, StubPredictor(), CAL, n_candidates=12, n_confirm=2)
    assert a.grade == "已確認"
    assert len(a.proposals) == 2
    for p in a.proposals:
        assert p["solver_tmax"] > 0
    assert any("求解器" in line and "已確認" in line for line in a.lines)
    assert any("不是最佳解證明" in line for line in a.lines)
