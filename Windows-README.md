# iperf3 桌面監測器 — Windows 免安裝版

## 開始使用

1. 將帶版本號的 ZIP **完整解壓縮**到可寫入的資料夾，例如桌面。
2. 進入對應版本的資料夾，開啟 `IperfMonitor.exe`。
3. 填寫 Server IP、port，選擇 TCP／UDP 和上傳／下載，按「開始測速」。
4. 要讓下次啟動沿用目前設定，按右上角「儲存設定」。

已包含 Python、Tkinter/Tcl/Tk、Matplotlib、Paramiko SSH 及相關依賴，以及 iperf3 3.16 與其 Windows DLL。**不需要另外安裝 Python、pip 或套件。** 程式會自動選取 `iperf3` 子資料夾中的執行檔。

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
  "output": "gui-results",
  "ssh": {
    "enabled": false,
    "host": "",
    "port": 22,
    "username": "technician",
    "vap": "wlan2.2"
  }
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

## SSH / Station 設定

1. 按「SSH / Station 設定」，勾選低速事件擷取，填寫 SSH IP、port（預設 22）、帳號（預設 `technician`）及 VAP（例如 `wlan2.2`）。**IP 留白或未啟用時完全不連線**，手動測試亦同。
2. 輸入 SSH／sudo 共用密碼，只保留於本次程式執行，不寫入設定、命令列或日誌。
3. 按「測試 SSH/Station」，首次連線請核對設備 SHA-256 主機指紋並確認，信任記錄存於程式旁的 `ssh_known_hosts`。自動查詢拒絕未知主機；金鑰改變時也拒絕，請確認設備變更後處理舊記錄。
4. 按「套用」回主畫面，需要保存參數時再按「儲存設定」。下次啟動需重新輸入密碼。舊 `config.json` 與 `ssh_known_hosts` 可沿用。

暖機後每個 LOW 事件開始時，以 root 權限執行以下唯讀命令；IP／VAP 可設定，MAC 自動來自清單：

```sh
dwpal_cli wlan2.2 peerlist
iw dev wlan2.2 station get EA:8C:B6:92:F0:B2
```

程式透過 `sudo -S -p '' -- sh -lc ...` 執行，密碼經標準輸入送入。設備需允許無終端 sudo 驗證，root 的 PATH 需能找到 `dwpal_cli` 和 `iw`。直接取得完整 iw 輸出後，在本機選取下列欄位顯示；等同你指定的 `grep -E "Station |inactive|signal|tx bitrate|rx bitrate"` 欄位，保留原始輸出供查核，亦保留 iw 命令本身的錯誤狀態。

```text
Station EA:8C:B6:92:F0:B2 (on wlan2.2)
inactive time: 0 ms
signal: -56 [-58] dBm
signal avg: -56 dBm
tx bitrate: 960.7 MBit/s 80MHz HE-MCS 9 HE-NSS 2 HE-GI 0 HE-DCM 0
rx bitrate: 1080.6 MBit/s 80MHz HE-MCS 10 HE-NSS 2 HE-GI 0 HE-DCM 0
```

詳細頁保留完整值、單位與 PHY 字串，設備沒提供的欄位顯示「未提供」；不強制要求 HE-MCS，因此也接受一般 legacy／HT／VHT bitrate。Station MAC／VAP 不符、命令失敗或沒有任何指定欄位時，顯示查詢錯誤。單一 peer 失敗會繼續查其他 peer。

連續低速只查詢一次，恢復正常後再低速才重抓。每次最多一個背景查詢，新事件若碰到前次尚未結束會記 `SKIPPED_BUSY`。連線／驗證各階段有 7 秒逾時，連線後全部遠端查詢共享 25 秒期限，每條輸出上限 2 MiB。停止會取消查詢；關閉視窗會等取消結果保存。定時測試自然結束時，已啟動的查詢可完成，期間不能開始另一輪。

事件表顯示 TX／RX 速率摘要與 **Fail 偵測日期時間（本機）**；欄位較多時可拉動表格底下的水平捲軸。選取事件後，「低速 Station 資料」顯示 Station 欄位及日期時間。日期格式例如 `2026-09-15 14:32:08.123+08:00`，表示本機收到第一筆低速區間報告的時間，**不是設備端 date，也不是區間開始時間的推算**。SSH IP 空白亦記錄日期；連續低速跨日保留首次日期，恢復後再低速才產生新日期。準確性取決於本機時鐘與 iperf 輸出延遲。SSH 觸發、開始與結束時間另外保留。

`samples.csv` 新增 `observed_at`，`low_events.csv` 與 `summary.json` 事件新增 `detected_at`，均以含時區的 ISO 8601 記錄。舊人工資料若沒有日期，畫面顯示「未提供」，不猜測。

Station 結果仍保存到 `mcs-events.jsonl` 以沿用原檔名。每行為一次狀態更新，同一 `event_id`（從 0 起）以最後一筆為準。完成紀錄包含 `source: "iw_station"`、`detected_at`、SSH 各階段時間、`peers`，每個 peer 包含 `mac`、`vap`、`inactive_time`、`signal`、`signal_avg`、`tx_bitrate`、`rx_bitrate`、`missing_fields`、`raw` 及成功／錯誤狀態；缺少的值為 null。新版不再產生舊版的 `mcs_1`、`mcs_2`。

狀態包含 `RUNNING`、`OK`、`NO_PEERS`、`ERROR`、`SKIPPED_BUSY`、`CANCELLED`。IP 留白不建立 SSH 紀錄檔，測速 CSV／JSON 的日期仍會保存。SSH 錯誤不改變吞吐量 PASS／LOW；查詢到的 Station 狀態可能晚於 fail。手動測試僅在設定視窗顯示結果。已通過本機模擬 SSH 與真正 Tk 測試，尚未對你的設備實測。

## 檔案結構

ZIP 與 SHA-256 檔名都包含版本號，例如 `iperf-monitor-windows-x64-v1.5.0.zip` 和 `iperf-monitor-windows-x64-v1.5.0.zip.sha256`。解壓縮的外層資料夾也會包含版本號，內部 EXE 保持原名。

```text
IperfMonitor-v1.5.0/       以 v1.5.0 為例
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
