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

## SSH / MCS 設定

1. 按右上角「SSH / MCS 設定」，勾選「低速事件發生時擷取 MCS」。
2. 填寫設備的 SSH IP、port（預設 22）、帳號（預設 `technician`）及 VAP（例如 `wlan2.2`）。**IP 空白或未勾選啟用，都不會建立 SSH 連線**，包括「測試 SSH/MCS」按鈕。
3. 輸入本次 SSH／sudo 共用密碼。密碼欄遮蔽顯示，只保留在程式記憶體，不寫入設定或測試紀錄。
4. 按「測試 SSH/MCS」：首次連線會顯示 SHA-256 主機指紋，請與設備核對後確認。信任記錄存於程式旁的 `ssh_known_hosts`；自動低速擷取不會直接信任未知主機。主機金鑰改變時拒絕連線，需確認設備變更後處理舊記錄。此確認只信任主機身分，不修改設備設定。
5. 按「套用」回主視窗；需要保存 IP／port／帳號／VAP／啟用狀態時，再按「儲存設定」。下次啟動仍需輸入密碼。舊版設定缺少 `ssh` 時預設關閉。

暖機後每次低速事件開始時，背景執行 `dwpal_cli <VAP> peerlist`，對所有 MAC 執行 `dwpal_cli <VAP> peerratesinfo <MAC>`，解析最後兩筆 `MCS index`。例如三筆為 `-1、0、11`，MCS 1＝0、MCS 2＝11；欄位名稱只代表最後兩筆的順序，不推定 TX／RX。以同一密碼經標準輸入交給 `sudo -S -p '' -- sh -lc ...` 取得 root 權限，效果等同以 root 執行這兩種查詢，不需要互動式 `sudo su`。設備必須允許無終端的 sudo 密碼驗證，且 root 登入 shell 可找到 `dwpal_cli`。

連續低速只查詢一次，恢復正常後再次低速才重抓；資料中断也會依事件表分成新事件。每次最多一個背景查詢，正在查詢時再有新事件會記錄 `SKIPPED_BUSY`，避免查詢累積。連線／驗證各階段有 7 秒逾時，連線後所有 dwpal 查詢共享 25 秒期限，每條輸出最多 2 MiB。

事件表顯示 MCS 或錯誤狀態。選取事件，再開啟「低速 MCS 資料」頁籤可查看詳細 JSON。結果資料夾內的 `mcs-events.jsonl` 逐行追加開始／完成紀錄，包含 `event_id`（從 0 開始，對應事件表順序）、觸發區間與速率、擷取時間、MAC、MCS 和原始輸出。狀態包括 `RUNNING`、`OK`、`NO_PEERS`、`ERROR`、`SKIPPED_BUSY`、`CANCELLED`；同一事件以最後一筆為準。IP 空白不建立此檔案。

SSH 失敗或沒有 peer 會明確記錄，吞吐量測試繼續，PASS／LOW 仍只看速率。手動停止／關閉會取消查詢；定時測試自然結束時，已開始的查詢可完成，期間「開始測速」暫時停用。MCS 是查詢當下的狀態，可能晚於低速取樣，不代表兩者精確同步。手動「測試 SSH/MCS」結果僅顯示於設定視窗。

升級時可保留自己的 `config.json` 與 `ssh_known_hosts`。此功能已使用本機模擬 SSH 設備及真正 Tk 介面驗證，尚未對你的設備實測。

## 檔案結構

ZIP 與 SHA-256 檔名都包含版本號，例如 `iperf-monitor-windows-x64-v1.4.0.zip` 和 `iperf-monitor-windows-x64-v1.4.0.zip.sha256`。解壓縮的外層資料夾也會包含版本號，內部 EXE 保持原名。

```text
IperfMonitor-v1.4.0/       以 v1.4.0 為例
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
