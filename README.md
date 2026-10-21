# PowerQuery TW｜台電開放資料 Text2SQL 智慧查詢系統

用中文查詢台電資料，並在回答前確認 SQL 安全性與資料是否足以支持答案。

目前已實作至 **Phase 9**：SQLite 語意層、離線規則路由、可選 OpenAI adapter、SQL／語意雙守門、離線評測、FastAPI、圖表工作台，以及需登入與人工審核的資料／語料管理。離線模式不需要 API key；它使用確定性規則，未涵蓋的問法會拒答，不是本機生成式模型。

## 組員交接：2026-10-21

**程式碼基線：`main` 的 `47a7bf1`。** 本節是最新交接狀態；`docs/PHASE9_STATUS.md`、舊分工文件與歷史 checkpoint 的測試數字屬於當時版本，不代表本次基線。

### 已完成與驗證

- [PR #2](https://github.com/mina201199/text2sql_project/pull/2)：自然語言標準答案題組、離線規則與機組別名，詳見 [問句與答案包](docs/offline-language-pack.md)。
- [PR #3](https://github.com/mina201199/text2sql_project/pull/3)：清楚區分查詢成功與語料收錄失敗，提供檢索評測差異及技術原因。
- [PR #4](https://github.com/mina201199/text2sql_project/pull/4)：同類分析意圖優先、類內 TF-IDF 排序；未知意圖或沒有同類範例時維持字詞排序。舊版本因 `retrieval_regression` 被拒絕的候選，再次送出時會重跑完整驗證，保留舊驗證稽核紀錄；通過後仍須人工審核。
- 本機完整測試 **345 passed**；Ruff lint／format 通過；PR #4 的 push 與 pull request CI 均通過並合併。
- 同一批 golden＋eval **140 題**的首選範例意圖符合數由 **72 提升至 131（93.57%）**，原先符合題目無退步。四筆候選單獨及按 24 種順序累計加入，皆維持 131／140；門檻未放寬，benchmark 未加入語料。
- 原有離線意圖 80／80、執行 60／60、語意陷阱 45／45、SQL 攻擊阻擋 15／15、正常問題誤攔 0／20。這些成績與檢索符合率都不是線上 LLM 答案準確率。

### 尚未完成／待接手

分工代號沿用 [四人分工](docs/TEAM_4_ROLES.md)：A 資料、B Text2SQL／語料、C 安全／評測、D API／前端／整合。以下是建議承接角色，不代表已指派給特定組員。

| 優先度 | 工作與目前狀態 | 建議承接 | 下一步與完成條件 |
|---|---|---|---|
| P0 | **OpenAI 真實模型評測未執行**；串接、fake client 測試與預檢已完成，實際模型 ID、key 設定位置仍待提供 | B＋C，D 協助設定 | 先取得模型與設定位置，依 [線上評測指南](docs/ONLINE_EVALUATION.md) 執行 dry-run，再在確認呼叫範圍後執行有上限的線上評測。提交獨立、去敏感資訊的結果；分開報告純模型與規則混合路徑，勿用離線成績代替。 |
| P1 | **四筆候選已通過學習評測，但尚未人工核准發布** | B | 依下表重現，在「資料管理 → 語料審查」檢查 SQL、參數、來源與驗證結果，再由組員決定核准／拒絕。核准會再次驗證；驗收發布後索引同步、重啟可還原、原答案不變。待審核是既有治理流程，不是系統錯誤。 |
| P1 | **檢索仍有 9／140 題首選意圖不符**，皆為 `other` 題組 | B＋C | 從 `eval-other-{01,03,04,05,06}`、`golden-other-{01,03,05,07}` 分析複合／未分類問題。以獨立的新問法補語料或改善排序，保留既有正確題目、完整答案與安全評測。不得將這些 benchmark 問句／標準 SQL 複製進 corpus，也不得降低學習門檻。 |
| P1 | **新資料與全量原始封存尚待準備**；可信快照可用，但不是即時資料 | A，D 協助匯入 | 取得新來源後清理、對齊六個 CSV，核對涵蓋期間與來源 checksum，建立候選資料庫並人工審核。全量原始查詢另需相容的 `manifest.json`／`files/`；乾淨 clone 不含這些封存。驗收見 [資料匯入流程](docs/SERVING.md#資料熱插拔資料庫版本與稽核)。 |
| 發布前 | **團隊環境的部署與整合驗收尚未完成**；目前驗證為本機離線服務 | D＋C，A／B 提供版本資訊 | 在組員乾淨 checkout 重現下列驗收；資料或模型變更後重跑登入、候選審核、版本切換／回退、來源追溯及桌機／手機流程。若決定對外提供，再設定自訂帳密、allowed hosts、TLS、持久化備份與回退流程。公開部署目前未執行。 |

### 組員先重現這一輪

1. 從最新 `main` 建立自己的工作分支，依下方「快速開始」安裝依賴與建庫。已有資料版本的環境先備份，勿以重建 demo DB 覆寫現有工作區。
2. 離線啟動後，網頁選擇「僅可信資料」＋「離線規則」。若要沿用本次展示埠，啟動命令為 `uv run --no-sync powerquery --serve --host 127.0.0.1 --port 8789`，網址為 <http://127.0.0.1:8789/>；先確認該埠未被其他服務占用。
3. 跑下表，再跑「驗證與開發」的完整測試、Ruff 與離線評測；檢索／候選的針對性測試可用 `uv run --no-sync pytest tests/test_retriever.py tests/test_promotion_gate.py tests/test_corpus_learning.py tests/test_serving.py -q`。
4. 若要改檢索，先核對 `src/text2sql/retriever.py`、`src/eval/promotion_gate.py` 與 `src/serving/corpus_learning.py`。檢索演算法或意圖規則改動若影響舊候選判定，須同步更新 `RETRIEVER_VERSION`，並驗證重新評測、冪等與人工拒絕不被重開。

| 問句 | 展示快照預期答案 | 尚未人工處理的候選狀態 |
|---|---|---|
| `2026年7月林口三號機出力不是零的天數` | 26 天 | 待人工審核 |
| `2026年7月林口三號機出力為零的天數` | 5 天 | 待人工審核 |
| `2026年7月台中#2有發電幾天` | 31 天 | 待人工審核 |
| `2026年7月台中#2沒有發電幾天` | 0 天 | 待人工審核 |
| `2026年7月9日中火二號機尖峰出力多少` | 2026-07-09、28.4 萬瓩 | 待人工審核 |

「有發電天數」在此只表示系統尖峰時刻觀測到正出力的天數，不能推論全天發電狀況。前四筆在新版的收錄前／後檢索評測皆為 131／140；若後續已審核或換資料，狀態與數值應以該環境紀錄為準。

**執行期狀態不隨 Git 傳遞。** DB、`.powerquery-learning/`、`.powerquery-data/`、原始封存及 `logs/` 不在 Git 中；乾淨 clone 必須重建資料並重新送出問句，不會自動出現這台電腦的候選、審核或稽核紀錄。需交接既有執行期狀態時，另行備份並核對完整資料版本，不要把 DB、API key 或帳密加入 Git。`.env.example` 只是設定參考，程式不會自動載入 `.env`。

## 快速開始：本機離線展示

需要 Python 3.11 以上與 [uv](https://docs.astral.sh/uv/)。在專案根目錄執行；第一次安裝依賴需要網路，之後的建庫與可信資料查詢使用 repo 內的 CSV，不下載資料、不呼叫模型。

```powershell
uv sync --frozen --extra dev
uv run --no-sync python -m project_tasks init-dirs
uv run --no-sync python -m ingest.build_db
# 預設模式為 auto；移除此程序繼承的 key，確保本次展示使用離線模式。
Remove-Item Env:OPENAI_API_KEY -ErrorAction SilentlyContinue
uv run --no-sync powerquery --serve
```

開啟 <http://127.0.0.1:8000/>。服務視窗按 `Ctrl+C` 停止。macOS／Linux 請將 `Remove-Item` 那行改為 `unset OPENAI_API_KEY`。

Windows 也可雙擊 [`啟動.bat`](啟動.bat)，使用 <http://127.0.0.1:8765/>；啟動器會按需同步 dev／online 依賴、建庫，健康檢查通過後開瀏覽器。它沿用程序環境，有 key 時預設 `auto` 會啟用線上 runtime；要固定離線展示請使用上面的明確步驟。

可直接測試：

```powershell
uv run --no-sync powerquery "2026年6月每日備轉容量率"
uv run --no-sync powerquery --json "天然氣機組共有幾台？"
```

展示快照的預期結果：

| 問題／檢查 | 預期 |
|---|---|
| `GET /api/health` | `success: true`、`mode.active_mode: offline` |
| `GET /api/stats` | 175 台機組、36,928 筆尖峰出力、138 筆歲修紀錄 |
| 2026年6月每日備轉容量率 | 30 筆，折線圖與原始列 |
| 天然氣機組共有幾台？ | 24 台 |
| 2025年1月1日有哪些機組在歲修？ | 成功但 0 筆，沒有圖表；不代表確認當天無歲修 |
| 台中電廠去年總發電量是多少？ | `PEAK_SUM_ACROSS_DAYS`，拒絕將跨日功率加總成電量 |

完整啟動、管理登入、API 請求、缺檔排查與部署邊界見 [docs/SERVING.md](docs/SERVING.md)。

## 已實作能力

| 能力 | 目前行為 |
|---|---|
| 資料工程 | CSV 驗證、機組名稱／容量對齊、長表轉換、SQLite 星狀模型與中文 `v_*` views |
| 查詢 | 中文意圖／實體抽取、規則路由、意圖優先＋TF-IDF 範例檢索；可選線上 LLM 與受限重試 |
| 安全守門 | SQL AST、唯讀與 view／欄位允許清單、筆數／逾時限制 |
| 語意守門 | 針對指標、單位、時間、粒度與涵蓋範圍進行拒答、澄清或限制揭露 |
| 呈現 | SQL、參數、執行 trace、摘要、統計、表格及受限 line／bar／scatter 圖表；CDN 不可用時用本機 SVG |
| 資料治理 | 六個 CSV 資料槽、候選建庫、人工審核、不可變版本、原子切換與雜湊鏈稽核 |
| 語料治理 | 去識別、去重、benchmark 洩漏檢查、重播／回歸驗證；候選均須人工核准後發布 |
| 評測 | 語料內／外題組、結果比對、SQL 攻擊、語意陷阱、誤攔與 ablation 報告 |

```mermaid
flowchart LR
    U[中文問題] --> R[意圖、實體與範例檢索]
    R --> C[規則 SQL／可選 LLM]
    C --> S{SQL 與語意守門}
    S -->|拒答／澄清| X[原因與替代問法]
    S -->|通過／揭露| DB[(唯讀 SQLite views)]
    DB --> V[摘要、圖表、表格與來源]
    V --> H[候選語料驗證與人工審核]
    H --> R
    D[CSV 驗證與對齊] --> DB
```

網頁包含查詢中心、資料總覽、資料管理、API 與模型、API 文件五個工作區。公開查詢不需登入；資料、語料及模型管理需管理 session，寫入另需同源與 CSRF 驗證。本機預設 `admin`／`PowerQuery@123` 僅用於 loopback demo；自訂帳密與操作方式見 [管理登入](docs/SERVING.md#資料管理登入)。

## 資料快照與涵蓋範圍

repo 隨附 `taipower_align/` 的六個建庫 CSV：`units.csv`、`daily.csv`、`crosswalk.csv`、`daily_long.csv`、`outage.csv` 與 `generation_cost.csv`。建庫會產生本機 `data/processed/power.db`，資料版本、來源 SHA-256、筆數與期間寫入 manifest。

| 展示快照 | 數量／範圍 |
|---|---:|
| 機組主檔 | 175 台 |
| 每日尖峰資料期間 | 2025-01-01 ～ 2026-07-31，577 天 |
| 每日機組／彙總欄位 | 64 個，其中 43 個可對應機組主檔 |
| 尖峰出力長表 | 36,928 筆 |
| 歲修紀錄 | 138 筆，查詢應以實際涵蓋日期為準 |
| 發電成本 | 2023～2025 年按發電方式的元／度資料；保留審定／自編決算口徑 |

**全量原始資料封存未隨 Git checkout 提供。** `manifest.json` 與 `files/` 屬另外準備的快照；未提供時可信資料查詢仍可用，選擇「全量原始資料」則會回報缺少 manifest。原始資料搜尋／預覽不等於通用跨檔 Text2SQL，也不能取代語意層的可答性限制。準備方式見 [原始資料範圍](docs/SERVING.md#可信資料與全量原始資料)。

資料來源包含台電 [機組設備](https://data.gov.tw/dataset/8934)、[過去電力供需](https://data.gov.tw/dataset/19995)、歲修與各種發電方式成本資料。資料使用依政府資料開放授權條款；每日供需來源採滾動視窗，更新時需另行封存，不能把此展示快照視為即時資料。對齊方法見 [taipower_align/README.md](taipower_align/README.md)。

## 驗證與開發

```powershell
uv run --no-sync pytest
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync python -m eval.run_eval
```

離線評測讀取 `benchmarks/`，輸出 `reports/eval_latest.json`、歷史紀錄與 SVG。報告的 `mode` 為 `offline_deterministic_rules`；通過此題組代表目前快照上的離線能力，不代表線上模型或任意中文問題的正確率。benchmark 不得晉升為檢索語料。

OpenAI 線上評測另外使用 `python -m eval.run_online_eval`，預設只做預檢，實際呼叫必須明確指定 `--online` 與 `--model`。設定、呼叫上限與報告判讀見 [線上評測指南](docs/ONLINE_EVALUATION.md)；模型名稱與 API key 尚待提供，因此目前沒有真實模型準確率。此次新增問法、修正前後結果與涵蓋限制見 [查詢品質紀錄](docs/query-quality.md)。

可信資料更新需先將新來源清理、對齊成上述六個 CSV 的格式，再透過網頁「資料管理」建立候選、檢查驗證結果並人工核准，詳見 [資料熱插拔流程](docs/SERVING.md#資料熱插拔資料庫版本與稽核)。單純下載檔案不會更新可信資料庫；原始封存目錄也須使用相容的 manifest，不能以下載器產物直接取代。Windows 手動重建 DB 前請先停止服務，避免 SQLite 檔案鎖定。網頁內經人工審核的資料版本切換則可在服務運行時完成。

```text
src/ingest/       下載、驗證、SQLite builder 與 schema
src/align/        名稱、粒度、歲修與資料陷阱對齊
src/text2sql/     router、entities、retriever、LLM、雙守門與 pipeline
src/serving/      FastAPI、runtime、管理驗證、版本／語料治理與靜態前端
src/eval/         離線評測、線上預檢與明確啟用的模型評測
corpus/           核准檢索語料
benchmarks/       獨立評測題組
tests/            單元、契約、整合與端到端測試
configs/          路徑、檢索、模型與護欄設定
```

## 已知限制

- 尖峰出力是單一時刻的功率，不能跨日加總成發電量；也不能據此估算個別電廠成本或碳排。年度發電方式成本有獨立資料與會計口徑。
- 每日資料不含逐時／每十分鐘曲線；缺少紀錄或空結果不能推論實際值為零。
- 部分電廠機組位於殘差或跨廠彙總欄位，不能還原完整電廠出力；核能、IPP 等也缺少相同粒度主檔。
- 離線模式的路由範圍有限；線上模式仍受相同 SQL 與語意護欄約束，且需自行配置依賴、模型與 key。
- 主工作台可在無 CDN 時用 SVG；`/docs` 的 Swagger UI 首次載入仍需 jsDelivr。
- 服務預設僅供本機展示。公開 hosting 與 tunnel 均為另行選擇的部署操作，快速開始不會啟動。

## 進一步文件

- [啟動、管理與 API 使用方式](docs/SERVING.md)
- [API 契約](src/serving/API_CONTRACT.md)
- [完整設計規格](docs/superpowers/specs/2026-09-09-text2sql-taipower-design.md)（歷史設計；實際行為以程式與目前使用文件為準）
- [組員分工與 AI 協作規範](docs/TEAM_4_ROLES.md)
