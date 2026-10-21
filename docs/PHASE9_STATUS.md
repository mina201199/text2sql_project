# Phase 9 本輪交付紀錄

日期：2026-10-21。基準：`origin/main` 的 `9a8ecad`。
三個工作分支已整合至 `codex/github-status-followup`，以此分支提出 PR 至 `main`。

| 工作 | 分支 | 交付 |
|---|---|---|
| 展示與文件 | `codex/demo-stability` | 修正未登入時模式標籤、完整日期顯示；更新啟動與資料匯入說明 |
| 查詢品質 | `codex/query-quality` | 修正數字月份、機組別名、排行、正／零出力天數；補明確期間的電量拒答 |
| OpenAI 串接與評測 | `codex/online-evaluation` | 明確啟用的線上評測、預檢、呼叫上限、獨立且去敏感資訊的報告 |

功能整合版本：`cbcf00c`。原有五個 Ruff lint 錯誤及七個檔案格式問題也已修正。

## 驗收證據

- 整合版完整 pytest：**259 passed**，五個既有警告（AnyIO 相容性與本機示範帳密）。
- Ruff lint、format check、git diff whitespace check：通過。
- 離線基準：意圖 80／80、執行 60／60、語意陷阱 45／45、SQL 攻擊 15／15；正常問題誤攔 0／20。
- 獨立最終審查：66 項測試通過；六個新問法在規則與模擬模型路徑結果相同，三個拒答案例在生成前被攔截。
- 瀏覽器實測：模式標籤與完整資料期間正常；`2026/07 台中#2有發電幾天？` 回傳 31；明確月份的總發電量問題回傳 `PEAK_SUM_ACROSS_DAYS` 與原因。
- 真實 SQLite 快照上的 OpenAI 無 key 預檢：資料與 SDK 就緒、`pending_configuration`、模型呼叫 0 次、準確率為 null。

審查曾發現文件中的下載指令會產生與原始資料服務不相容的 manifest；已移除該捷徑，改寫為六個 CSV 的清理、對齊及人工審核匯入流程，並完成複查。

## 待補設定與限制

使用者已確認使用 OpenAI；確切模型名稱與 API key 設定位置稍後提供。
本輪未進行真實模型呼叫，因此尚無線上模型準確率。
Git checkout 未附全量原始資料封存；本輪使用隨附的可信資料快照，驗證原始資料缺檔提示。
新增規則只涵蓋已測試問法，不代表任意中文問題都可回答；「有發電天數」表示系統尖峰時刻觀測到正出力的天數。

使用方式見 [啟動與 API](SERVING.md)、[查詢品質紀錄](query-quality.md)、[線上評測](ONLINE_EVALUATION.md)。
