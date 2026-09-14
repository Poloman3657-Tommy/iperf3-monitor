# iperf3 桌面監測器 — Windows 免安裝版

## 開始使用

1. 將帶版本號的 ZIP **完整解壓縮**到可寫入的資料夾，例如桌面。
2. 進入對應版本的資料夾，開啟 `IperfMonitor.exe`。
3. 填寫 Server IP、port，選擇 TCP／UDP 和上傳／下載，按「開始測速」。
4. 要讓下次啟動沿用目前設定，按右上角「儲存設定」。

已包含 Python、Tkinter/Tcl/Tk、Matplotlib、數值及繪圖依賴，以及 iperf3 3.16 與其 Windows DLL。**不需要另外安裝 Python、pip 或 Matplotlib。** 程式會自動選取 `iperf3` 子資料夾中的執行檔。

預設 `192.168.137.57:4477`、上傳、60 秒、忽略前 20 秒、低於 100 Mbps 標記。測試秒數填 **0** 可持續測試，直到按停止、關閉視窗或發生錯誤。結果預設存於程式旁的 `gui-results`，也可在介面另選資料夾。

「iperf3 原始輸出」與 `iperf.log` 的 bitrate 使用 **Mbits/sec**（`-f m`），與圖表的 Mbps 相同。低速判定依原始輸出的數值與顯示精度進行。

## 時間單位與曲線

「即時曲線與低速事件」頁籤上方有 **時間單位** 選單：自動／秒／分／時／天，測試中也可以切換。橫軸仍是時間，縱軸維持 Mbps。自動模式依圖上時間範圍切換：不足 60 秒用秒，60 秒起用分，1 小時起用時，1 天起用天。

速率以平滑曲線連接區間中點，藍點代表取樣，紅點標示低速。曲線僅是顯示用插值，不會超過相鄰顯示點的最高／最低值；警示、平均、最低值仍使用原始取樣，不使用插值數據。

停止時保存的 PNG 是整段測試總覽，使用當下選擇的時間單位。縮放、拖移或之後切換單位只改畫面，不覆寫已保存 PNG；`run.json` 保留開始時的設定，CSV 與事件表的時間仍以秒記錄。按「儲存設定」可記住選擇的單位。

## 縮放與查看多天測試的低速事件

- 在圖內滾動滑鼠滾輪，以游標位置為中心放大／縮小；也可按「＋／－」。
- 在圖內按住左鍵左右拖移，或拉動圖下方的水平捲軸，查看歷史時間。
- 低速事件表保留本次測試的全部事件，可用右側捲軸查看早期項目。點選一列會放大到該事件前後的時間；再次點選同一列也會重新定位。
- 手動縮放、拖移或選取事件後，進入「歷史」檢視。新取樣不會將畫面拉回最新，但測速與存檔繼續，頂端「目前 Mbps」仍顯示最新取樣。
- 「跟隨最新」以目前縮放寬度追蹤最新資料；若從全部總覽切換，預設顯示最近 60 秒。
- 「顯示全部」回到完整時間範圍並隨新資料延伸。新測試也會重設為全部檢視。

多天總覽會保留每組最高、最低與低速代表點以加快重畫，畫面標示「總覽取極值」。放大後只繪製所選時段，恢復逐筆取樣與精確低速底色。所有事件、統計及 CSV/log 仍完整保留，沒有因圖表取點而刪減。

時間單位選「自動」時依目前可見時間寬度切換；即使已經運行數天，放大到短事件也能查看秒級細節。圖上方同時顯示天數與時分秒的檢視範圍。

## 設定檔與 TCP／UDP

`config.json` 位於 EXE 旁，啟動時自動讀取。按「儲存設定」才寫入；修改介面、開始或結束測試不會自動覆蓋設定。升級前請保留自己的 `config.json`，新版解壓縮後可放回使用。

```json
{
  "version": 1,
  "server": "192.168.137.57",
  "port": 4477,
  "duration": 60,
  "warmup": 20,
  "threshold": 100,
  "parallel": 1,
  "reverse": false,
  "protocol": "TCP",
  "udp_mbps": 1000,
  "time_unit": "auto",
  "iperf": "",
  "output": "gui-results"
}
```

- `server` 是 IP，`reverse: true` 表示下載，`duration: 0` 表示持續測試。
- `protocol` 可設 `TCP` 或 `UDP`；TCP 不加限速。
- `time_unit` 可設 `auto`、`seconds`、`minutes`、`hours`、`days`，只影響圖表。舊設定缺少此欄位時使用 `auto`。
- `udp_mbps` 是 UDP **每條連線**的目標 Mbps，只有選 UDP 才生效。例如 25 Mbps × 2 條約為 50 Mbps，低速門檻判斷 SUM 合計。
- `iperf` 空字串表示自動尋找包內 iperf3；路徑可相對於設定檔，例如 `iperf3/iperf3.exe`。輸出路徑也可用相對路徑。
- 設定檔錯誤時會顯示載入失敗，使用畫面上的內建預設，並保留原檔；請修正檔案後重開，或確認介面設定後按儲存。

UDP 仍以吞吐量判斷 PASS／LOW；丟包與 jitter 保留在 `iperf.log`，不作為這版的額外通過條件。若目標發送速率低於門檻，出現 LOW 是預期結果。

本次已驗證 Windows client 對 NUC Linux server 的雙條 UDP 下載。包內 Cygwin iperf3 3.16 若作為 **Windows server**，多條 UDP 連線可能失敗；該情境請用單條連線或 Linux server。程式會保留原始錯誤，不會偷偷改成 TCP。

## 檔案結構

ZIP 與 SHA-256 檔名都包含版本號，例如 `iperf-monitor-windows-x64-v1.3.0.zip` 和 `iperf-monitor-windows-x64-v1.3.0.zip.sha256`。解壓縮的外層資料夾也會包含版本號，內部 EXE 保持原名。

```text
IperfMonitor-v1.3.0/       以 v1.3.0 為例
  IperfMonitor.exe        桌面程式
  config.json             預設／已儲存設定
  _internal/              Python、Tk 與繪圖執行環境
  iperf3/                 iperf3.exe 與配套 DLL
  licenses/               相依軟體授權
  README.md               本說明
  THIRD-PARTY-NOTICES.md   相依版本與來源
  build-manifest.json     程式與 iperf3 檔案校驗值
```

搬到其他電腦時請搬整個資料夾，不能只拿 EXE。打包目標是 **Windows x64**；已在 Windows 11 x64 驗證。Ubuntu／macOS 需要對應系統的另一份打包版本。

Server 端仍需執行 iperf3 server，例如 `iperf3 -s -p 4477`。免安裝包只是包含本機所需程式，不會替遠端啟動 server。

## 診斷

如需檢查包內套件、GUI 與 iperf3 是否完整，可在 CMD 執行：

```bat
IperfMonitor.exe --check-package package-check.json
```

這個診斷只在 `127.0.0.1` 執行約 4 秒的單條 UDP 回環下載，使用真正 Tk 事件循環，檢查持續測試、停止、PNG 輸出及設定儲存／重讀；不連到外部 server。結果寫入指定 JSON、旁邊的 `run-data` 與 `package-test-config.json`，不修改 EXE 旁的使用者設定。
