# 單一 HTML 可攜版

只需複製 **iperf-monitor.html** 到其他 Windows、Ubuntu 或 macOS 電腦，用現代瀏覽器開啟。HTML 自含所有樣式、程式和圖表功能；不需要 Python、Node.js、網路或額外圖表套件。請自行準備對應作業系統的 iperf3；Windows 版本還需要其 DLL。

## 使用方式

1. 開啟 `iperf-monitor.html`，先選「執行環境」：Windows／Ubuntu／macOS，再調整 Server IPv4、port、方向、測試秒數。環境指執行 iperf3 client 的電腦，與 server 作業系統無關。預設 Windows、`192.168.137.57:4477`、上傳、60 秒，忽略前 20 秒，低於 100 Mbps 標記。
2. 按右上角「執行」下載對應腳本，或「複製命令」貼到所選環境的終端機。Windows 下載 `run-iperf.cmd`，放在 `iperf3.exe` 同一資料夾後雙擊；Ubuntu／macOS 下載 `run-iperf.sh`，在下載資料夾的終端機輸入 `sh run-iperf.sh`。腳本會將 log 寫在腳本同一資料夾。
3. 測試結束後，把生成的 `iperf_*.log` 拖入 HTML，或按「選擇 iperf3 紀錄」。也可貼上完整 iperf3 文字输出。
4. 查看圖形及低速事件；可匯出 PNG、取樣 CSV、低速事件 CSV，或按「儲存單一 HTML 報告」保留資料與判定設定。

**一般瀏覽器不能直接執行本機 iperf3。** 切換作業系統也不會改變這項限制。本版是命令產生＋紀錄分析流程；不會在頁面按鈕後自行連線測速，也不提供測試中的即時圖。命令把輸出導向紀錄檔，所以終端機在等待期間不會每秒列印速率。

| 執行環境 | 命令／脚本 | iperf3 位置 |
|---|---|---|
| Windows | CMD／`.cmd`（CRLF） | `iperf3.exe` 與 DLL 放在腳本旁 |
| Ubuntu | POSIX shell／`.sh`（LF） | 先找 PATH 中的 `iperf3`，再找目前資料夾可執行的 `./iperf3` |
| macOS | 終端機／`.sh`（LF） | 同 Ubuntu；需 macOS 對應架構的 iperf3 |

Ubuntu／macOS 的腳本使用 `sh`，不必對下載的 `.sh` 執行 chmod；若自行放置 iperf3 二進位檔，該程式本身仍須具備執行權限。POSIX 腳本使用英文 locale 以保持紀錄格式一致，執行失敗會保留非零退出碼。

## 設定與判定

- 不加反向參數時為上傳；在頁面選「下載」就會產生 iperf3 `-R`。
- IP／port／測試時間／方向／連線數決定下一次執行命令；已匯入圖表的目標與方向從原始紀錄讀取，不會因為修改下一次命令而被改標。
- 忽略時間與門檻會重新分析已匯入紀錄，不會重新執行測速。裸 `.log` 不含這兩個判定設定，匯入時請確認頁面設定；儲存的 HTML 報告會一起保存。
- `start >= 暖機秒數` 才判定；跨越暖機邊界的整段忽略；等於門檻不算低速。
- 多條 stream 只使用 SUM；合併相鄰低速區間形成事件。
- 每次複製命令、下載腳本或修改設定都會產生新紀錄檔名。若重複執行相同命令且檔案已存在，會拒絕覆寫；請回頁面重新複製命令或下載腳本。儲存 HTML 報告時也會記住所選環境；舊報告未包含環境欄位時沿用 Windows。
- ERROR、INCOMPLETE、NO_DATA 都不是通過；只有完整測試且暖機後沒有低速才是 PASS。
- 支援 iperf3 原始文字 `.log` / `.txt`，最大 32 MB。不支援 `-J` JSON、`-O` 暖機重設或多次測試合併的 log；請使用頁面產生的命令。
- 使用十進位 Mbps，精度依 iperf3 的 Kbits/sec 文字輸出；約一秒平均無法識別更短的瞬時下降。

測試用固定資料位於 `html-src/fixtures/download.txt`，是明確標示的人工資料，不代表真實網路測速。個人測試紀錄及產生的報告不納入 repository。

## 開發與驗證

原始碼：`../html-src/core.js`（解析／判定）、`../html-src/page.html`（介面）、`../build_html.py`（嵌入打包）。重建：在上一層執行 `python build_html.py`。

核心驗證：`node --test html-src/test-core.cjs`，12 項通過。離線 DOM 驗證：`node html-src/test-ui.cjs`，使用 repo 內的固定資料，涵蓋三種環境切換、腳本下載、表單、門檻重新分析、PNG/CSV 匯出、報告重新載入及文字安全嵌入。

腳本驗證：`node html-src/test-shell.cjs`，在 Windows 的 Git POSIX sh 下確認 `.sh` 語法、含空白路徑、本機二進位檔搜尋、參數、成功／失敗退出碼、紀錄防覆寫和缺少執行檔。這是 shell 相容性驗證，沒有在實際 Ubuntu 或 macOS 主機上執行新版腳本。

DOM 測試專用依賴放在 `html-src/.test-tools/`，不包含在 HTML 執行需求中。重建測試環境：

```bat
npm.cmd install --prefix html-src/.test-tools --cache html-src/.test-tools/.npm-cache --no-audit --no-fund --ignore-scripts jsdom @napi-rs/canvas
```

與既有 Python 程式比對三份實測 log：上傳、下載、受控低速的最低值、加權平均、事件數均一致。已生成並檢视 PNG。瀏覽器自動化工具禁止開啟本機 file:// URL，因此未完成真實瀏覽器的視覺操作驗證；本次使用離線 DOM 與 Canvas 程式驗證，沒有绕過瀏覽器政策。
