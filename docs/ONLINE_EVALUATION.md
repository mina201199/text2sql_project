# 線上 AI 評測

本命令將指定 benchmark 問題交給 `Text2SQLPipeline`，經過問題語意檢查、檢索、
模型生成、SQL AST 檢查、SQL 語意檢查，最後以唯讀 SQLite 執行。
與 benchmark 的參考查詢比較結果欄名與資料列集合，不以 SQL 字串相同判定正確。

**Provider 已確認使用 OpenAI。目前只以 fake client 驗證流程；確切模型與金鑰位置仍待提供，
實際模型品質評測尚未執行。**
既有 `python -m eval.run_eval`、`reports/eval_latest.json` 與
`reports/eval_history.jsonl` 是離線規則評測，不代表線上模型準確率。

## 先執行本機預檢

在專案根目錄使用專案 Python 環境：

```powershell
uv sync --extra online
uv run python -m eval.run_online_eval --dry-run --model YOUR_MODEL_ID
```

省略 `--online` 時一律只預檢；`--dry-run` 是明確寫法。
`--model` 必填，不採用 `OPENAI_MODEL` 或 adapter 的預設模型。
請以帳號實際可使用的模型 ID 取代 `YOUR_MODEL_ID`；本命令不查詢模型清單。

預檢驗證資料庫、語料、選取的 benchmark 問題與參考 SQL，並以唯讀模式執行參考查詢。
既有 benchmark 的字串字面值會先由 SQLGlot 的 SQLite tokenizer 依來源順序轉成綁定參數，
再交給 SQL guard 驗證；引號識別字與註解不會當成字串值替換。
缺少資料庫時不會建立空資料庫。參考 SQL 必須通過相同 SQL guard，且結果欄名必須唯一。
預檢只檢查 SDK 可用性與 `OPENAI_API_KEY` 是否存在，不建立 provider client、
不驗證金鑰有效性、不送網路請求。即使金鑰存在，也不會自動切換到線上模式。

預設位置為 `data/processed/power.db`、`benchmarks/eval_questions.json`、
`corpus/training_corpus.json`。可使用 `--database`、`--benchmark`、`--corpus` 指定位置。
資料庫須有既有建置流程產生的語意 views、`meta_manifest` 與 `meta_pitfall`。
Benchmark 是非空 JSON array，每項至少包含非空 `question` 與 `sql` 字串；
可提供布林 `in_corpus` 供分組。參考 SQL 使用字面值，沒有獨立的參考參數欄位；
已含 placeholder 的參考 SQL 因缺少參數會被預檢拒絕。
原始資料不隨此工具附送；請使用既有匯入流程先準備資料庫。

## 明確啟用線上呼叫

在之後確認資料、模型與費用並提供金鑰後，於執行程序的環境設定 `OPENAI_API_KEY`，再執行：

```powershell
uv run python -m eval.run_online_eval --online --model YOUR_MODEL_ID --max-cases 5 --max-calls 5 --max-attempts 1 --timeout-seconds 30
```

本命令不會讀取 `.env`、不接收命令列金鑰，也不會把金鑰存進報告。
實際送出的 prompt 包含問題、語料 schema／規則與檢索範例；選取資料應適合傳送給 provider。
重生時也會包含前次 guard／執行失敗回饋。模型 adapter 使用 Responses API，並設定 `store=False`。

預設停用規則路由，使原本規則能回答的問題也必須經過模型；問題語意 guard 仍可先行拒絕。
`--use-router` 可改成正式服務的混合路徑，讓規則優先回答。
報告會分開顯示 `routed_cases`、整體 `execution`、實際呼叫過模型的 `model_execution`。
完全未呼叫模型時 `live_evaluation` 是 `not_run`，`model_execution` 是 `null`，
不會把規則回答的成績算成模型準確率。

| 選項 | 預設 | 範圍與行為 |
| --- | --- | --- |
| `--max-cases` | 5 | 1–100；按 benchmark 順序取前 N 題 |
| `--max-calls` | 5 | 1–300；整場所有題目、重生及 provider 失敗合計的呼叫上限 |
| `--max-attempts` | 1 | 1–3；每題模型生成上限 |
| `--timeout-seconds` | 30 | 大於 0、至多 120；每次 SDK 請求 timeout |

達到呼叫上限後不再向 provider 送出請求，其餘題目記為 `skipped`。
金鑰驗證／權限失敗也停止剩餘題目。SDK 的自動重試關閉，避免額外請求繞過預算；
這與 [OpenAI Python SDK 的重試與 timeout 設定](https://developers.openai.com/api/reference/python)
一致。Timeout 是單次請求的設定，不是整場評測的絕對時間期限。
呼叫上限也不是金額／token 預算；報告不估計實際帳單費用。

## 報告與退出碼

預設輸出 `reports/online/online_latest.json` 與 `reports/online/online_history.jsonl`，
可用 `--report`、`--history` 指定。命令拒絕覆寫本次輸入、兩個相同輸出位置，
以及名稱為 `eval_latest.json`／`eval_history.jsonl` 的離線報告。

報告包含設定、benchmark／corpus SHA-256、選題數、provider 呼叫次數、各題位置索引、
結果是否匹配、guard 拒絕數、耗時與固定錯誤代碼。
不保存問句、原始 case ID、prompt、SQL、參數、資料列、檔案路徑、pipeline trace 或例外訊息。
`case_index` 是從 1 開始的原始 benchmark 位置，配合 SHA-256 可重現選題。

`execution` 的分母是已評測題目，包含 guard 拒絕與 provider 失敗，排除 `skipped`；
`model_execution` 只包含實際嘗試過模型呼叫的題目。
`status=completed` 表示流程跑完，不保證所有題目答對。
dry-run 的 `execution`／`model_execution` 都是 `null`。
`pending_configuration` 表示 SDK 或金鑰尚未就緒；預檢不能確認 provider 帳號存取權。
結果比對採集合語意，不測量重複列的次數或資料列順序；空結果匹配仍可能掩蓋不佳資料涵蓋率。
正式品質結論應先確認 benchmark 參考結果與資料涵蓋率，並保存對應資料快照。

退出碼：`0` 是成功預檢（可包含待設定項目）或全部已評測問題匹配；
`1` 是線上結果不匹配、guard／provider 失敗或預算中止；
`2` 是設定、本機輸入、client 初始化、報告寫入失敗，或線上模式仍缺必要設定。

測試只替換 provider 邊界，其餘使用真正的 pipeline、guard、retriever 與小型唯讀測試資料庫：

```powershell
uv run pytest tests/test_online_eval.py tests/test_pipeline.py tests/test_llm.py
```
