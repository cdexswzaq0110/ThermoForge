"""依賴檔之間的一致性。

三份 requirements 各有用途，而且**會漂**：

| 檔 | 用途 |
|---|---|
| `requirements.txt` | 本機開發，torch 釘 cu121 |
| `requirements-ci.txt` | GitHub runner，torch 換 CPU 版 |
| `requirements.lock.txt` | `uv pip freeze` 的完整凍結，重建環境用 |

漂掉的症狀是「CI 綠燈但本機壞掉」或反過來，而那種失敗會被歸咎到程式碼上，
不會有人想到去比對兩份 txt。所以把比對變成測試。

這是 `docs/lessons/0003`（模板與它的驗收腳本會不一致）在依賴檔上的同一個形狀。
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_PIN = re.compile(r"^([A-Za-z0-9_.\-]+)==(.+)$")


def _pins(path: Path) -> dict[str, str]:
    """解析釘住的版本，忽略註解、空行與 index-url 這類選項行。"""
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        m = _PIN.match(line)
        if m:
            out[m.group(1).lower()] = m.group(2)
    return out


def test_ci_requirements_match_dev_except_torch():
    """CI 與開發環境只准差在 torch 這一項。"""
    dev = _pins(ROOT / "requirements.txt")
    ci = _pins(ROOT / "requirements-ci.txt")
    assert set(dev) == set(ci), f"套件清單不同：只在 dev {set(dev) - set(ci)}，只在 ci {set(ci) - set(dev)}"

    differing = {k for k in dev if dev[k] != ci[k]}
    assert differing == {"torch"}, f"除了 torch 之外還有版本不同：{differing}"
    assert dev["torch"].startswith(ci["torch"]), (
        f"CI 的 torch {ci['torch']} 與開發的 {dev['torch']} 不是同一個上游版本"
    )


def test_lockfile_covers_every_direct_dependency():
    """凍結檔必須包含每一個直接依賴——少了就代表它是舊的。"""
    direct = _pins(ROOT / "requirements.txt")
    lock = _pins(ROOT / "requirements.lock.txt")
    missing = {k for k in direct if k not in lock}
    assert not missing, f"lock 檔沒有這些直接依賴（要重跑 uv pip freeze）：{sorted(missing)}"


@pytest.mark.parametrize("name", ["requirements.txt", "requirements-ci.txt", "requirements.lock.txt"])
def test_every_dependency_is_pinned(name):
    """全部釘死。`>=` 會讓「上週能跑」變成沒有意義的陳述。"""
    text = (ROOT / name).read_text(encoding="utf-8")
    loose = [
        line.strip()
        for line in text.splitlines()
        if (s := line.split("#", 1)[0].strip())
        and not s.startswith("-")
        and "==" not in s
    ]
    assert not loose, f"{name} 有沒釘死的項目：{loose}"
