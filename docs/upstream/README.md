# 上游發現（Serendipity-Epiphany）

**這個目錄裝的是「在本專案裡撞到、但缺陷屬於工具」的東西。裡面的 patch 一律 inert——
本專案不套用，也不代替工具 repo 做決定。**

## 為什麼分開放

`.claude/` 來自 [Serendipity-Epiphany](https://github.com/cdexswzaq0110/Serendipity-Epiphany)，
那是一套會被**所有**未來專案共用的 harness。在這個專案裡改它，等於用一輪專案工作
去決定所有未來專案的行為——改動半徑差一個數量級。

所以界線是：**專案消費工具，不改工具。**

| 在專案裡發現工具的缺陷 | 做什麼 |
|---|---|
| 記錄 | 寫進 `docs/lessons/`，含觸發情境、機制與建議修法 |
| 保留可執行的修正 | 存成 patch 放這裡，**不套用** |
| 真的修 | 等工具 repo 自己排一輪，在那邊做 |

這條界線是 2026-09-07 撞出來的：那天先在工具 repo 開了分支與 PR，
被指出不合理之後撤回（見 `docs/lessons/0005`）。

## 目前的內容

| 檔 | 對應的 lesson | 狀態 |
|---|---|---|
| `serendipity-bootstrap-check.patch` | [L0003](../lessons/0003-bootstrap-template-and-checker-disagree.md) | **未套用**。已在 Serendipity 的工作副本上驗證過（自測 3/3、hooks 22/22、對本專案回歸 8/8），之後撤回 |

## 要套用的話

在 **Serendipity 那個 repo** 自己起一輪：

```bash
cd <Serendipity 路徑>
git checkout -b fix/context-template-fails-its-own-check
git am < <ThermoForge>/docs/upstream/serendipity-bootstrap-check.patch
bash templates/_meta/bootstrap_check.sh --selftest      # 預期 3/3
bash .claude/hooks/selftest.sh                          # 預期 22/22
bash templates/_meta/bootstrap_check.sh <ThermoForge>   # 回歸，預期 8/8
```
