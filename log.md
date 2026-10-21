# PowerQuery TW 開發進度

> 這份檔案在每個可驗證、可回退的儲存點更新。回退前需保留使用者原有的未提交變更。

## CP-014 — 檢索改善後的組員交接

- 日期：2026-10-21。
- 程式碼基線：`main` 的 `47a7bf1`，PR #4 已於 CI 通過後合併；自然語言擴充與拒絕提示修正分別見 PR #2、#3。
- 本次範圍：僅更新 `README.md` 與本交接紀錄，未修改程式或執行期資料。
- README 已補最新交付、建議 A／B／C／D 分工、待完成事項與驗收條件，包含 OpenAI 真實評測、四筆候選人工審核、剩餘 9 題檢索誤配、資料交付及部署前整合驗收。
- 基線驗證：前一輪完整測試 345 passed，Ruff 通過；140 題檢索符合數 72 → 131，原先正確題目無退步，四候選累計加入無退步。原有離線執行 60／60、語意陷阱 45／45、SQL 攻擊阻擋 15／15、正常問題誤攔 0／20。此紀錄不宣稱線上模型準確率。
- 本次驗證：核對 CLI 啟動參數、實作與既有指南；重新確認 9 題未符合的 ID；提交前檢查 Markdown 本機連結與 `git diff --check`。僅文件變更，未重跑程式測試。
- 交接邊界：執行期 DB、候選／稽核、原始封存與 logs 不隨 Git 交付；待人工審核不等於已發布。新組員須依 README 重建／確認資料後重現。
- 回退方式：需要撤回本次文件時，以此文件提交的 SHA 執行 `git revert <文件提交SHA>`；不回退 PR #4 的檢索改善，也不修改執行期資料。

## CP-013 — 資料治理、專案交接與 Windows 一鍵展示

- 時間：2026-09-13 22:25 +08:00
- 狀態：已完成
- 管理介面：原「語料中心」已改為「資料管理」，登入後可在資料檔、待審異動、語料審查、資料庫版本與稽核紀錄五個頁籤中調閱及操作；左側仍保留查詢中心、資料總覽、API 與模型及 API 文件。
- 登入與權限：本機展示預設為 `admin`／`PowerQuery@123`，只允許 loopback；可由環境變數覆寫。管理 session 使用短期 HttpOnly／SameSite cookie，異動 API 另驗證同源與 CSRF，審核者一律取自伺服器 session。
- 資料熱插拔：五個固定 CSV 資料槽可新增或替換，`outage_csv` 可移除；上傳、移除與回退只建立 `pending_review` 候選，驗證 schema、跨檔資料品質並建置不可變 SQLite 後，仍須人工核准才切換。舊版與來源 checksum 保留，可下載歷史來源、建立需再次審核的回退異動。
- 語料治理：離線 router 與線上 LLM 產生的新語料均先停在待人工審核；核准時重新執行去識別、SQL／語意、結果與 benchmark 回歸檢查，通過才發布及重建索引。候選保存查詢 view、資料版本與實際來源檔 SHA-256，未保存結果 rows。
- 發布一致性：build journal 先綁定候選 DB 與確切來源 checksum；mutation journal 使 staged、failed、rejected 的 change 與 audit 在中斷後成對、冪等恢復；不可變來源、DB、版本、核准異動及稽核事件持久化後，`active.json` 才最後切換。publish journal 可恢復中斷發布，audit head 與永久建立標記能分辨首次舊版遷移和後續錨點遺失，active revision 會與發布事件交叉核對；來源、DB、manifest、指標或稽核遭竄改時，查詢及所有管理讀寫都 fail closed。每次查詢的 runtime 與 provenance 使用同一個已驗證 snapshot，多 worker 依共享指標同步。
- 熱插拔驗收：在隔離的暫存工作區，以同一歲修問句驗證 `138 筆 → 移除候選仍 138 筆 → 核准後 0 筆 → 重傳候選仍 0 筆 → 核准後恢復 138 筆`，證明人工核准是唯一生效點。
- 瀏覽器驗收：實際登入新版資料管理，完成查詢「2026年四月有哪些機組在歲修？」、來源追溯、語料人工核准與稽核調閱；候選顯示 `v_outage`、作用中資料版本及 `outage.csv`／`units.csv` checksum，頁面無先前的大型失效圖片。
- 重啟驗收：既有 `.powerquery-data` 工作區已平滑建立 audit head 及永久建立標記；連續兩次啟動後登入、作用中版本、五個來源、DB checksum 與稽核鏈均有效，且沒有殘留 mutation／publish journal。驗收後已停止服務，避免 Windows／OneDrive 占用 SQLite。
- 自動驗收：`uv lock --check`、`ruff format --check .`、`ruff check .`、`node --check src/serving/static/app.js`、`git diff --check HEAD` 與 `pytest -q` 全數通過（184 passed，含 3 個 Windows launcher 測試）；只保留 Starlette 第三方淘汰警告與使用公開 demo 帳密的預期警告。
- 本機安全備份：實機遷移前保留 `data/processed/.powerquery-data-pre-cp013` 與 `data/processed/.powerquery-learning-pre-cp013`，均位於 gitignored 執行期資料目錄。
- 進度與分工：README 已加入 0.3.0／Phase 1～8、184 passed、熱插拔及實機驗收快照；新增 `docs/TEAM_4_ROLES.md`，以 A～D 明定 Phase 9 唯一檔案所有權、量化驗收、跨組交接單、共用 AI 規則與四段可直接啟動的角色 Prompt；`log.md` 明訂為各角色可追加本次 checkpoint 的共享例外。
- 一鍵展示：新增根目錄 `啟動.bat` 與兩個 `scripts/launcher_*.ps1` 輔助程式，可從中文、OneDrive 或含空白路徑雙擊；會檢查 `uv`、只在依賴輸入改變時同步環境、初始化目錄、缺少時建庫、重用既有服務，並在 `127.0.0.1:8765` 健康後開啟瀏覽器。實機驗證依賴 stamp 為兩段 64 位 SHA-256、已啟動服務可直接沿用，且 `/api/health` 與首頁均回 200；驗收後已停止服務。
- 目錄整理：`DATA_DICTIONARY.md`、`EVALUATION.md`、`SEMANTIC_GUARD.md`、`SERVING.md`、`SYSTEM_CARD.md`、`TEXT2SQL_PIPELINE.md` 已集中到 `docs/`，README 與相對連結同步更新且本機 Markdown link check 無斷鏈；根目錄只保留專案入口、建置設定、進度紀錄與一鍵啟動檔。
- 回退方式：回退 `feat: add governed data management and project launcher` 這個 commit；先停止服務，再視需要以 CP-013 前本機備份恢復執行期工作區。CP-001～012、已發布 Release 與使用者原有未提交變更保持不動。

## CP-012 — Windows 資料庫占用提示與建庫復原

- 時間：2026-09-13 20:27 +08:00
- 狀態：已完成
- 現象與根因：Windows 執行 `ingest.build_db` 時，仍在運作的 PowerQuery／SQLite connection 占用 `data/processed/power.db`，使最後的原子 `os.replace` 回傳 WinError 5；前段資料建置本身沒有失敗。
- 修正：原子發布遇到 `PermissionError` 時改拋相容於既有 `PermissionError`／`OSError` 捕捉邏輯的 `DatabasePublishError`，明確指示先以 `Ctrl+C` 停止服務並確認目錄可寫；CLI 只顯示這段操作訊息與 exit code 1，不再輸出 traceback。
- 保護：替換失敗時保留既有 `power.db`，並由 `finally` 嘗試移除本次 `.power-*.db` 暫存檔；測試鎖定情境確認舊檔內容未變且一般 target-only lock 不留暫存檔。
- 文件：`docs/SERVING.md` 已補上 Windows 重建資料庫前必須停止服務的順序與原因。
- 實機復原：關閉先前預覽服務後重新建庫成功，SQLite `PRAGMA quick_check=ok`；再由 `uv run powerquery --serve` 於 `127.0.0.1:8000` 啟動，`GET /api/health` 回 200。占用狀態重跑建庫則正確保留原資料庫並輸出新提示。
- 自動驗收：`ruff format --check .`、`ruff check .`、`git diff --check`、`pytest -q` 全數通過（113 passed）；僅保留既有 Starlette 第三方 AnyIO alias 淘汰警告。
- 回退方式：回退 `fix: explain locked database rebuilds on Windows` 這個 commit；CP-001～011、已發布 Release 與使用者原有變更保持不動。

## CP-011 — 台電資料 GitHub Release

- 時間：2026-09-13 16:43 +08:00；公開完成：2026-09-13 16:46 +08:00
- 狀態：已完成
- Release：https://github.com/chenliyu0410/text2sql_project/releases/tag/taipower-data-2026-09-13
- Git tag：`taipower-data-2026-09-13`，指向 `da749ad6f93eae7d949b47e1d291c690a0e4cb29`。
- 目標：`taipower-data-2026-09-13`／「台電開放資料與 PowerQuery 資料包（2026-09-13）」。
- 資產：完整原始開放資料、PowerQuery 可直接查詢資料、專案文件三個 ZIP，另附 `SHA256SUMS.txt`；詳細成員、大小與 checksum 見 `docs/releases/taipower-data-2026-09-13.md`。
- 安全邊界：排除含真實電號或機構名稱的參考筆記、`.powerquery-learning` 本機學習工作區、查詢紀錄、語料事件、憑證、虛擬環境與快取。每包都附台灣電力公司顯名、OGL 1.0、非即時資料與精確基礎設施位置提醒。
- 驗證：三包 CRC 通過；中文檔名保留；原始包 204 個資源與 manifest 逐筆一致；三個 ZIP 的 SHA-256 已重算一致。GitHub 回報四個 asset 均為 `uploaded`，三個 ZIP 的遠端 byte 大小與 SHA-256 digest 和本機完全相同。
- 回退方式：先從 GitHub Release 管理介面刪除 `taipower-data-2026-09-13` Release 與 tag，再回退 `chore: prepare Taipower data release` 及本筆完成紀錄 commit；大型資產未加入 Git，CP-001～010 與使用者原有變更保持不動。

## CP-000 — 實作前基線

- 時間：2026-09-13 13:02 +08:00
- 狀態：已完成
- Git 基線：`4565ca08adbb2a3d413c4d94283a1a3a9e67a2c8`
- 已驗證：`taipower_align/align.py` 與 `taipower_align/final.py` 都可在 Python 3.13 成功執行。
- 現有資料基準：175 台機組、577 天、43 個已對應欄位、36,928 筆長表資料。
- 使用者原有未提交變更：`.gitignore`、`README.md`、系統規格、`docs/AI_AGENT_COLLABORATION.md`、`scripts/`、`參考資料/`。
- 回退方式：只回退 CP-001 之後新增的實作檔；不對上述使用者變更執行 reset 或 checkout。

## CP-010 — 多頁操作中心、執行模式與可稽核語料學習

- 時間：2026-09-13 16:35 +08:00
- 狀態：已完成
- 前端工作台：完成查詢中心、資料總覽、語料中心、API 與模型、API 文件五個頁面；左側導覽加入常用分析與只留問句的本機最近查詢。逐次查詢的「沿用預設」不再誤送 `auto`，手機抽屜具備 inert／焦點管理，Plotly 與原生 SVG fallback 均無破圖。
- 離線／線上模式：新增 `offline`、`online`、`auto` runtime 管理與逐次覆寫；OpenAI API key 只存在伺服器程序記憶體，不寫磁碟、不回傳、不進瀏覽器儲存，並可由介面明確清除。憑證移除或環境 key 輪替會清掉舊 client cache，狀態與錯誤回應不洩漏 key 或 adapter 細節。
- OpenAI adapter：使用 Responses API Structured Outputs、`store=False`、30 秒 timeout 與單層重試控制；線上 extra 已安裝，並以無效測試 key 驗證 client 初始化後立即清除，沒有向 OpenAI 發出模型請求。
- 自動語料治理：Web／API 查詢可建立候選；router 候選須通過 benchmark 洩漏、去重、SQL／語意、結果重播與檢索回歸關卡才自動發布，LLM 候選必須人工審核。語料中心可搜尋、篩選、查看完整欄位、事件與審核內容。
- 資料安全與一致性：候選只保存問句、參數、SQL、驗證與結果 checksum，不保存結果 rows；遞迴去識別化涵蓋電號、身分證、電話、卡號與標記姓名。工作區使用程序鎖、跨程序檔案鎖、原子寫入、版本／checksum manifest；canonical 或資料庫基線變更時自動備份、重建索引並要求既有候選重新驗證。
- API 與文件：新增 runtime、語料清單、事件、審核及訓練狀態端點；422 驗證錯誤不反射敏感輸入。主工作台提供離線 API 說明，`/openapi.json` 可本機使用；`/docs` 固定 Swagger UI 5.32.15、nonce、精確 SRI 與頁面專用 CSP，且已明示首次載入需要 jsDelivr。
- 實機驗收：在新版工作台執行「2026年7月20日出力前五名機組」，取得 5 筆、平均 405.92 萬瓩並正常顯示圖表；五個頁面、語料詳細視窗、runtime 狀態與 Swagger UI 均通過，瀏覽器 console 無 CSP／載入錯誤，頁面影像檢查無破圖。
- 自動驗收：`ruff format --check .`、`ruff check .`、`node --check src/serving/static/app.js`、`pytest -q` 全數通過（111 passed）。Starlette TestClient 仍有一則第三方 AnyIO alias 淘汰警告，不影響測試或執行。
- 回退方式：回退 `feat: add runtime and corpus control center` 這個 commit；執行期 `.powerquery-learning` 可獨立移除或由其版本備份回復，不影響 canonical corpus；CP-001～009 與使用者原有變更保持不動。

## CP-009 — Plotly 圖示與畫布樣式修復

- 時間：2026-09-13 15:30 +08:00
- 狀態：已完成
- 根因：`.chart svg` 後代 selector 誤中 Plotly modebar 的內部 SVG，把相機、分享與縮放圖示強制放大為至少 620×260px；嚴格 CSP 同時阻擋 Plotly 以 CSSOM 注入的版面規則，使三張 overlay SVG 在文件流中垂直堆疊。
- 修正：fallback 圖改用 `.chart > svg`；Plotly 容器固定 320px，並在本機 stylesheet 以 `.plotly-chart` scope 補齊必要的 overlay 與 modebar 規則，沒有放寬 `style-src` CSP。
- 瀏覽器驗收：實際執行「2026年7月20日出力前五名機組」，正常顯示 5 根長條與資料表；圖表／主 SVG 均為 820×320px 左右，三張主 SVG 全為 absolute overlay，8 個 modebar icons 均為 16×16px。
- 回歸保護：靜態端點測試明確禁止 `.chart svg {`，並要求 direct-child fallback selector 與 Plotly absolute overlay 規則存在。
- 自動驗收：`ruff format --check .`、`ruff check .`、`node --check src/serving/static/app.js`、`pytest -q` 全數通過（65 passed）。
- 回退方式：回退 `fix: scope plotly svg styles` 這個 commit；CP-001～008 與使用者原有變更保持不動。

## CP-008 — Phase 7 API、CLI 與對話式呈現層

- 時間：2026-09-13 14:23 +08:00
- 狀態：已完成
- API：完成 FastAPI 應用、延遲載入 runtime、健康／資料統計／語料狀態／範例／查詢端點與 OpenAPI 文件；資料庫未就緒時回 503，輸入格式錯誤回 422，語意拒答維持結構化業務 envelope。
- CLI：`powerquery` 可直接查詢、輸出完整 `--json`，或以 `--serve` 啟動 Uvicorn；`make serve` 與 `docs/SERVING.md` 收錄可重現操作方式。
- 呈現：後端只建立 `line`、`bar`、`scatter` 白名單圖表規格，日期／數值、類別／數值與雙數值形狀各自選圖；scalar、空結果、全 NULL 或純文字回傳 `chart_spec: null`。圖表 x/y 直接投影自 SQL rows。
- 前端：完成繁中對話介面、資料涵蓋側欄、範例問句、階段式進度、可取消查詢、結構化錯誤／限制揭露、KPI、表格、SQL 細節與響應式版面。固定版本 Plotly.js basic bundle提供互動圖表，無法載入 CDN 時退回相同資料的原生 SVG。
- 安全與無障礙：所有動態內容使用 `textContent` 或 SVG attribute，不拼接不可信 HTML；加入 CSP、`nosniff`、frame deny 與 no-referrer headers；支援雙 live region、`aria-current`、鍵盤焦點、中文輸入法組字、防誤送 Enter、reduced motion 與手機 safe area。
- 相依版本：FastAPI 0.141.1、Uvicorn 0.52.4、HTTPX2 2.12.0；Plotly.js basic bundle 固定為 4.0.0 並驗證 SHA-384 SRI。
- 實機驗收：本機 Uvicorn 啟動後，`GET /api/health` 與 `POST /api/query` 均回 200；「2026年6月每日備轉容量率」取得 30 筆，`chart_spec.data[0].x[0]` 與 SQL 第一列日期同為 `2026-06-01`。
- CLI 驗收：「2026年7月備轉容量率最低是哪一天？」成功回傳 `2026-07-05`、`10.23%`；無 API key 時明確標示離線規則模式，長尾問題不以假模型輸出替代。
- 自動驗收：`ruff format --check .`、`ruff check .`、`node --check src/serving/static/app.js`、`pytest -q` 全數通過（65 passed）。Starlette 1.6.0 仍從第三方 `testclient.py` 發出一則 AnyIO 型別別名淘汰警告，不影響測試或執行。
- 回退方式：回退 `feat: deliver api cli and accessible web interface` 這個 commit；CP-001～007 與使用者原有變更保持不動。

## CP-007 — Phase 6 離線評測與回歸關卡

- 時間：2026-09-13 14:09 +08:00
- 狀態：已完成
- 結果比對：候選 SQL 與標準 SQL 都在同一個唯讀 SQLite 快照上執行；指標以欄名集合與列集合等價性計算，不比對 SQL 字串。
- 離線基準：黃金意圖 80/80；eval 意圖 60/60；執行結果 60/60，`in_corpus=true` 與 `false` 各 30/30；攻擊 15/15；語意陷阱 45/45；合法邊界題 0/20 誤攔。所有驗收條件通過。
- 詮釋界線：上述執行成績標示為 `offline_deterministic_rules`，是可重現規則 handler 基準，不是線上 GPT 準確率；沒有 API key 時不會把 benchmark 答案假裝成 LLM 輸出。
- Ablation：RAG top-1 意圖為 31/60（51.67%），無檢索且預設 other 為 6/60（10%）；語意守門開／關陷阱處理為 100% / 0%；規則查詢首次已成功，重試 1/2/3 次無差異；關閉路由的對照需線上 LLM，誠實標記 `not_run_without_online_llm`。
- 語料回歸：`CorpusRegressionGate` 比較候選 corpus 與基線的獨立題庫 top-1 意圖檢索率，超過可容忍退步就拒絕整批晉升。
- 產物：`reports/eval_latest.json`、只追加的 `reports/eval_history.jsonl`、`reports/figures/eval_summary.svg`；`make eval` 可重建。
- 驗收：`python -m eval.run_eval`、`ruff format --check .`、`ruff check .`、`pytest -q` 全數通過（57 passed）。
- 回退方式：回退 `feat: add reproducible offline evaluation` 這個 commit；CP-001～006 與使用者原有變更保持不動。

## CP-006 — Phase 5 資料語意守門

- 時間：2026-09-13 13:52 +08:00
- 狀態：已完成
- 雙層判斷：在生成前檢查問句可答性，在執行前再以 `sqlglot` AST 檢查真實 SQL 形狀；所有結果都是結構化 `code`、`severity`、說明、建議與 evidence。
- 規則：完成 `PEAK_SUM_ACROSS_DAYS`、`UNIT_MISMATCH`、`NO_UNIT_DETAIL`、`RESIDUAL_TREND`、`PLANT_TOTAL_INCOMPLETE`、`KNOWN_CAPACITY_GAP`、`ZERO_PERIOD_AMBIGUOUS`、`AMBIGUOUS_UNIT_NAME`、`DATA_RANGE_OUT_OF_BOUNDS` 九條守門。
- 分級：`refuse` 與 `clarify` 不執行 SQL；`disclose` 可繼續查詢但必須隨結果回傳限制。同一規則在問句層與 SQL 層同時命中時只揭露一次。
- 動態資料：資料期間從 `meta_manifest` 讀取；殘差欄、電廠總量不完整與容量缺口對象從 `meta_pitfall` 讀取，查詢層不重複寫死清單。
- 邊界檢查：單日跨機組加總、同單位容量比較、殘差欄單日值、具明確期間的零出力等 20 個反例均放行。
- 驗收：陷阱題 45/45 命中（100%，要求 ≥ 95%）；20 個合法邊界反例 0 誤攔（0%，要求 ≤ 5%）；`ruff format --check .`、`ruff check .`、`pytest -q` 全數通過（52 passed）。
- 回退方式：回退 `feat: add data-aware semantic guardrails` 這個 commit；CP-001～005 與使用者原有變更保持不動。

## CP-005 — Phase 4 Text2SQL 管線

- 時間：2026-09-13 13:44 +08:00
- 狀態：已完成
- 管線：建立實體抽取→問句語意接點→零成本路由→字元 n-gram TF-IDF 檢索→LLM結構化產生→SQL AST 守門→SQL語意接點→唯讀 SQLite 執行的完整編排，並在 trace 保留每步驟耗時。
- 實體：支援西元日期、民國年、中文／全形數字、去年／今年／上個月／上下半年、燃料與 Top-N；相對日期可注入 reference date 以便重現。
- 線上／離線：`OpenAILLM` 使用 Responses API 與 JSON Schema Structured Outputs；`FakeLLM` 用於無 key 的離線 CI，線上模式缺 key 時明確報錯，不會假裝成真實模型。
- 安全：所有路由與 LLM SQL 都經過同一守門；只允許單一 `SELECT`、四個審核 view 與欄位 allowlist，強制參數化字串、`LIMIT <= 200`，禁止註解、多敘述、寫入、系統表與危險函式。SQLite adapter 以 `mode=ro`、`query_only` 與 progress handler 做唯讀及逾時防護。
- 失敗處理：LLM 輸出、SQL 守門或執行錯誤會帶結構化原因重生，上限 3 次；仍失敗時回傳 `GENERATION_FAILED`，不偷換預設查詢。
- 驗收：黃金意圖題庫 80/80（100%，要求 ≥ 90%）；攻擊題庫 15/15 全數攔截；`ruff format --check .`、`ruff check .`、`pytest -q` 全數通過（42 passed）。
- 回退方式：回退 `feat: implement guarded text2sql pipeline` 這個 commit；CP-001～004 與使用者原有變更保持不動。

## CP-004 — Phase 3 語料與獨立題庫

- 時間：2026-09-13 13:31 +08:00
- 狀態：已完成
- 正式語料：`corpus/training_corpus.json` 含 DDL、領域文件與 40 組 question–SQL examples；已建立可重現的字元 n-gram `corpus/index.json`。
- 題庫：`golden_questions.json` 80 題（10 意圖各 8 題）、`eval_questions.json` 60 題（`in_corpus=true/false` 各 30）、`trap_questions.json` 45 題（9 條規則各 5）、`attack_questions.json` 15 題。
- 訓練／測試邊界：corpus 與所有 benchmark 問句正規化後無逐字重疊；benchmark 不會被索引。
- 自動語料學習：加入去識別、批次去重、benchmark 洩漏阻擋、可注入 SQL／語意／結果關卡、回歸關卡、版本 checksum、舊版備份與 rollback。
- 原子性：一個 batch 中任一候選失敗時，正式 corpus 與 index 都不會被部分更新。
- 驗證：`python -m text2sql.corpus`、`ruff format --check .`、`ruff check .`、`pytest -q` 全數通過（23 passed）。
- 回退方式：回退 `feat: add governed corpus and isolated benchmarks` 這個 commit；已發布的 corpus 也可用 `rollback_corpus` 切回 `corpus/versions/` 備份。

## CP-003 — Phase 2 對齊層與歲修資料

- 時間：2026-09-13 13:24 +08:00
- 狀態：已完成
- 範圍：命名轉換、粒度／燃料分類、crosswalk 容量比驗證、歲修對齊、從對齊結果產生 `meta_pitfall`，所有核心郏輯都是無資料庫、無網路 I/O 的純函式。
- Crosswalk：43 列唯一對應、175 台機組全數涵蓋，ratio 重算與異常備註檢查無 issue。
- 歲修快照：官方 `d006008` 138 列已以內容 SHA-256 `f0b30c1d32a3…` 封存。自動對齊 125 列（90.58%），達成 ≥ 90% 驗收門檻。
- 未對齊：`大潭#8`、`大潭#9`、`興達新#1` 不存在目前機組主檔；`立霧` 可指向兩台機組。全數留在 `reports/outage_unmatched.txt` 供人工核對，沒有猜測。
- 下載問題與修正：Python 3.13 系統 CA 第一次拒絕官方端點的舊憑證鏈。改用 `certifi` 信任 CA bundle 後通過，未關閉 TLS 驗證。
- 官方資料警告：歲修第 102 列的開始日 `2027-12-20` 晚於結束日 `2027-02-23`。系統保留原值、設 `date_status=invalid_range`，不自行猜測正確年份。
- 資料陷阱：`meta_pitfall` 共 10 列：`RESIDUAL_TREND` 2、`PLANT_TOTAL_INCOMPLETE` 6、`KNOWN_CAPACITY_GAP` 2。
- 驗證：`python -m align`、重建 `power.db`、`ruff format --check .`、`ruff check .`、`pytest -q` 全數通過（15 passed）。
- 回退方式：回退 `feat: extract alignment layer and import outages` 這個 commit；CP-001／002 保持不動。

## CP-002 — Phase 1 SQLite 資料層

- 時間：2026-09-13 13:18 +08:00
- 狀態：已完成
- 範圍：資料下載與內容尋址封存、CSV schema／日期／數值／重複鍵驗證、SQLite 星狀模型、四個 `v_*` 語意檢視、`meta_manifest`、資料字典與品質報告。
- 驗收數字：22 座電廠、175 台機組、64 個原始出力欄位、43 個主檔對應、36,928 筆尖峰出力、577 筆系統日資料。
- 資料期間：2025-01-01 ～ 2026-07-31；來源檔、建庫內容與 schema 都有 checksum，重建內容冪等。
- Schema 決策：增加 `dim_b_column` 保留全部 64 欄，`bridge_b_column` 專注 43 個已對應關係，避免 B-only 的 21 欄在 fact 裡丟失。
- 資料異常與修正：52 台機組的商轉日期只有月精度（`YYYYMM`）。系統保留原值與 `month` 精度，並以當月 1 日作可排序值，沒有偽造不存在的精確日期。
- 資料陷阱：建庫時由 crosswalk 導出 2 個殘差趨勢、6 個電廠總量不完整、2 個容量缺口，共 10 列，沒有寫死對象清單。
- 驗證：`ruff format --check .`、`ruff check .`、`pytest -q` 全數通過（7 passed）；SQLite `quick_check=ok`，四個 views 齊全。
- 產物：`data/processed/power.db` 為可重建、gitignored 產物；`reports/data_quality.json` 保留本次驗證結果。
- 回退方式：回退 `feat: build validated SQLite semantic layer` 這個 commit；Phase 0 與使用者原有變更保持不動。

## CP-001 — Phase 0 專案地基

- 時間：2026-09-13 13:12 +08:00
- 狀態：已完成
- 範圍：`pyproject.toml`、`uv.lock`、`Makefile`、`configs/`、`src/` 套件骨架、離線 CI、`SYSTEM_CARD.md`、`.env.example`。
- OpenAI 設定：依官方 Responses API 與模型文件預留 `OPENAI_MODEL`，線上套件放在選用 `online` extra，CI 不需 API key。
- 驗證：`uv sync --extra dev`、`ruff format --check .`、`ruff check .`、`pytest -q` 全數通過（2 passed）。
- 回退方式：回退 `feat: scaffold phase 0 project foundation` 這個 commit；不影響 CP-000 列出的使用者變更。
