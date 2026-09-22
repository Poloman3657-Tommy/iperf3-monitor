# iperf3 Monitor — Windows 免安裝版

直接執行 iperf3 的 Windows x64 桌面測速工具，可即時查看速率曲線、標記低速時段，並自動保存結果。已內含 Python、Tkinter、Matplotlib、相關依賴和 iperf3，**不需要另外安裝 Python 或套件**。

## 下載與啟動

到 [最新 Release](https://github.com/Poloman3657-Tommy/iperf3-monitor/releases/latest) 下載：

- `iperf-monitor-windows-x64-v<版本>.zip`：Windows x64 免安裝包。
- `iperf-monitor-windows-x64-v<版本>.zip.sha256`：對應版本的 SHA-256 校驗碼。

例如 v1.7.0 的檔名是 `iperf-monitor-windows-x64-v1.7.0.zip`，解壓縮後會建立 `IperfMonitor-v1.7.0` 資料夾。請從上方「最新 Release」選擇需要的版本；歷史版本也使用各自的版本號。

1. 將 ZIP **完整解壓縮**到可寫入的資料夾。
2. 進入 `IperfMonitor-v<版本>` 資料夾，開啟 `IperfMonitor.exe`。
3. 填入 server IP、port，選擇 TCP／UDP 與上傳／下載。
4. 按「開始測速」；需要結束時按「停止」。

請保留 EXE、`_internal`、`iperf3` 等整個資料夾結構，不能只搬移 EXE。Server 端仍需另外啟動，例如：

```sh
iperf3 -s -p 4477
```

## 介面與參數

| 項目 | 用途 | 預設值 |
|---|---|---|
| Server IP／Port | 測試對象 | `192.168.137.57:4477` |
| 測試秒數 | 每輪測試時間；**0 表示持續測試** | 60 秒 |
| 重測等待（分鐘） | 每輪測完後，等幾分鐘再開始下一輪 | 5 分鐘 |
| 總排程分鐘 | 整體經過時間，包含測試、等待及存檔；**0 表示只測一輪** | 0 |
| 忽略開始秒數 | 起始暖機期間不判定低速 | 20 秒 |
| 低速門檻 | 嚴格低於此值才標記 | 100 Mbps |
| 協定 | TCP 或 UDP | TCP |
| 傳輸方向 | 上傳：本機 → server；下載：server → 本機 | 上傳 |
| 平行連線數 | 多條 stream，以 SUM 合計速率判定 | 1 |
| UDP Mbps／每條 | UDP 每條連線的目標發送速率 | 1000 Mbps |
| iperf3 執行檔 | 自動尋找包內程式，也可自行選擇 | 自動 |
| 結果資料夾 | 儲存每次測試的圖表與紀錄 | EXE 旁的 `gui-results` |

「iperf3 原始輸出」及 `iperf.log` 的 bitrate 顯示 **Mbits/sec**，與圖表的 Mbps 等義。進行測試時會鎖定測速參數，時間顯示單位仍可切換；「停止」或關閉視窗會停止本程式啟動的 iperf3，並保存已收到的資料。

## 重複測試排程

例如設定 **測試 60 秒、重測等待 5 分鐘、總排程 30 分鐘**：先測一輪，測完後等 5 分鐘，再開始下一輪，直到按開始後總共經過 30 分鐘。介面顯示第幾輪、下輪倒數及總排程剩餘時間。等待期間也能按「停止」，取消後續輪次。

測試秒數設為 **0** 時，重測等待與總排程兩個欄位停用且不生效，維持原本持續測試。非零秒數搭配總排程 **0** 表示單次；總排程大於 0 才重複執行。重測等待 **0** 表示本輪存檔完成後立即開始下一輪。

每輪重新計算暖機期間，並各自保存 HTML、CSV、PNG 與 Station 紀錄，集中在 `gui-results/schedule-時間戳/各輪時間戳/`。下一輪必須等上一輪 SSH 與報告完成；若存檔超過等待時間，會延後啟動，輪次不重疊。總時間到期會停止測速並保存已收到資料，最後不足一整輪時記為 `INTERRUPTED`，原因為 `Schedule time limit reached`；存檔收尾可能晚於截止時間。

LOW 仍會繼續下一輪；測速或報告錯誤會停止排程並顯示原因。SSH 查詢失敗只記錄診斷錯誤，不改變吞吐量判定。按「儲存設定」可保存 `repeat_minutes` 和 `total_minutes`，舊設定檔缺少這兩個欄位時維持單次測試。

## 即時曲線與時間單位

圖表上方可選 **自動／秒／分／時／天**，測試中也能切換；橫軸是時間，縱軸維持 Mbps。自動模式在圖示時間範圍達 60 秒、1 小時、1 天時切換為分、時、天。

曲線平滑連接取樣點，保留藍色取樣點及低速紅點。平滑只是視覺插值，不會新增超出相鄰顯示點範圍的高低點；低速判定與所有統計仍使用原始資料。

PNG 保存整段測試總覽，採用停止當下的單位；縮放或其後切換只調整畫面。CSV／事件表仍以秒記錄。時間單位可透過「儲存設定」保存在 `config.json` 的 `time_unit`（`auto`／`seconds`／`minutes`／`hours`／`days`）。

### 放大查看低速事件

- 滑鼠滾輪或「＋／－」可縮放橫軸；左鍵拖曳或下方水平捲軸可左右移動。
- 點選低速事件列，直接放大到該事件前後。事件表提供垂直捲軸，保留本次測試的全部事件。
- 手動查看歷史時，新資料不會重設檢視範圍。按「跟隨最新」恢復追蹤，按「顯示全部」回到總覽。
- 多天總覽使用最高／最低及低速代表點加快繪圖；放大後恢復該區間逐筆資料。原始紀錄、統計及低速事件不刪減。

## 低速時透過 SSH 擷取 Station 資訊

右上角「SSH / Station 設定」可設定 SSH IP、port、帳號、VAP 與本次密碼。預設關閉，**IP 留白時完全不連線**。啟用後先按「測試 SSH/Station」核對主機指紋，再按「套用」；主視窗「儲存設定」會保存 IP 等參數，密碼只保留本次執行。

暖機後每個低速事件開始時，先執行 `dwpal_cli <VAP> peerlist`，再對每個 MAC 執行 `iw dev <VAP> station get <MAC>`。詳細頁顯示 Station、inactive time、signal、signal avg、完整 tx bitrate／rx bitrate，包括頻寬、HE-MCS、HE-NSS、HE-GI、HE-DCM。設備未提供的欄位明確顯示「未提供」。

選取事件後，到「低速 Station 資料」查看各 MAC 的欄位。連續低速擷取一次，恢復正常後再低速會重新觸發；查詢忙碌時記錄 `SKIPPED_BUSY`。單一 peer 失敗會保留錯誤並繼續其他 peer；SSH 失敗不影響吞吐量判定。

**Fail 日期時間**顯示於事件表及詳細頁，使用本機收到第一筆低速報告的日期時間，包含時區，例如 `2026-09-15 14:32:08.123+08:00`。SSH 未啟用也會記錄。此時間是偵測時間，並非回推區間開始或設備端 `date`；SSH 觸發與查詢時間另列，方便辨識延遲。連續事件跨午夜仍保留首次偵測時間。

Station 結果沿用 `mcs-events.jsonl` 檔名，內容改為 `source: "iw_station"`、各 peer 的 Station 欄位與原始輸出；不再產生 `mcs_1`／`mcs_2`。詳細說明見 [Windows 說明](Windows-README.md#ssh--station-設定)。已通過本機模擬 SSH 及 GUI 測試；尚未對你的實際 SSH 設備驗證。

## 儲存設定

程式啟動時會讀取 **EXE 旁的 `config.json`**。在介面修改參數後，按「儲存設定」才會更新此檔案，下次啟動即沿用。

也可以手動編輯設定檔；格式與預設值見 [config.example.json](config.example.json)。`server` 是 IP、`reverse: true` 是下載、`protocol` 可填 `TCP`／`UDP`，`duration: 0` 是持續模式。路徑可相對於設定檔；`iperf` 空字串代表自動尋找。

設定檔格式錯誤會在視窗顯示載入失敗並保留原檔。請確認畫面參數後再測試。升級前先關閉舊程式，保留自己的 `config.json`，解壓新版後再放回。

## TCP／UDP 與低速判定

TCP 不設定發送速率上限。UDP 的目標速率是**每條連線**的值，例如 25 Mbps × 2 條，總目標約 50 Mbps；門檻仍看合計速率。若目標本身低於門檻，出現 LOW 是預期結果。

每輪預設忽略前 20 秒；持續模式則只在開始時忽略一次。只有完整位於暖機後的區間（`start >= warmup`）才判定；跨越暖機邊界的整段忽略，等於門檻不算低速。每個取樣是約一秒平均，判定精度以 iperf3 顯示的數值為準。

UDP 丟包和 jitter 留在原始 log，這版 PASS／LOW 只判斷吞吐量。已驗證 Windows client 對 Linux server 的 UDP 多連線；包內 Cygwin iperf3 3.16 作為 Windows server 時，多條 UDP 連線可能失敗，該情況可使用單條連線或 Linux server。

## 結果檔案

### 單一 HTML 互動報告

測試完成、按停止或關閉程式後，會在本次資料夾自動保存 **`report.html`**。程式會先等已啟動的 Station 查詢完成／取消，再寫入報告；存好後可按左側「開啟 HTML 報告」。報告寫入期間會暫時停用開始下一輪測試。

只需複製這一個 HTML 到其他電腦，以瀏覽器開啟即可，**不需要 Python、iperf3 或網路**。支援自動／秒／分／時／天、滾輪縮放、左鍵拖移、下方水平捲軸，以及點選 fail 事件定位。完整保留取樣、統計、fail 日期與 Station 資料；事件超過 100 筆時分頁顯示，每頁可捲動，資料不刪除。

HTML 是已完成測試的報告。「查看最後一段」定位到最後資料，預設最近 60 秒；「顯示全部」回到總覽。開啟時使用測試結束時選定的時間單位，後續切換／縮放不改變原始數據，也不保存瀏覽器檢視狀態。多天資料只在畫面取代表點，放大恢復逐筆顯示；完整資料內嵌，因此檔案大小會隨測試時間增加。

已以 Chrome 驗證四天、345,600 筆取樣及 173 次 fail 的離線互動。若 HTML 寫入失敗，程式顯示錯誤，並盡可能留下 `html-report-error.txt`，原本的 CSV／JSON／PNG 仍保留。

每次測試會建立不同的時間戳資料夾，包含：

| 檔案 | 內容 |
|---|---|
| `throughput.png` | 速率曲線、暖機與低速標記 |
| `report.html` | 單一離線互動報告，包含完整取樣、fail 日期、Station 與圖表縮放／捲動 |
| `iperf.log` | iperf3 原始輸出及錯誤 |
| `samples.csv` | 每個取樣的起訖、Mbps、狀態與本機接收日期 `observed_at` |
| `low_events.csv` | 合併後的低速時段、最低速率與首次偵測日期 `detected_at` |
| `summary.json` | 統計與最終結果 |
| `run.json` | 當次實際參數及執行命令 |
| `mcs-events.jsonl` | 啟用 SSH 且觸發低速時的查詢狀態、各 peer 的 Station 欄位與原始輸出 |

只有正常完成且無低速才是 PASS。LOW 表示完成但有低速；INTERRUPTED 表示手動停止；ERROR 表示測試或輸出失敗；NO_DATA 表示沒有暖機後的有效資料。持續模式按停止後顯示 INTERRUPTED，並保留已有統計。

`run.json` 是測試紀錄，與啟動時載入的 `config.json` 不同。

## 診斷與開發

完整操作與包內診斷方式見 [Windows 使用說明](Windows-README.md)。目前發行下載僅提供 Windows x64；原生 GUI 已在 Windows 11 驗證。

開發者可直接 clone repository，依 [原始碼開發說明](GUI-README.md) 安裝依賴、測試及建置。個人設定、測速資料、虛擬環境及建置暫存不納入 Git。
