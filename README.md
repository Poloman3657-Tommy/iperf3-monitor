# iperf3 Monitor — Windows 免安裝版

直接執行 iperf3 的 Windows x64 桌面測速工具，可即時查看速率曲線、標記低速時段，並自動保存結果。已內含 Python、Tkinter、Matplotlib、相關依賴和 iperf3，**不需要另外安裝 Python 或套件**。

## 下載與啟動

到 [最新 Release](https://github.com/Poloman3657-Tommy/iperf3-monitor/releases/latest) 下載：

- `iperf-monitor-windows-x64-v<版本>.zip`：Windows x64 免安裝包。
- `iperf-monitor-windows-x64-v<版本>.zip.sha256`：對應版本的 SHA-256 校驗碼。

例如 v1.4.0 的檔名是 `iperf-monitor-windows-x64-v1.4.0.zip`，解壓縮後會建立 `IperfMonitor-v1.4.0` 資料夾。請從上方「最新 Release」選擇需要的版本；歷史版本也使用各自的版本號。

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
| 測試秒數 | 指定總時間；**0 表示持續測試** | 60 秒 |
| 忽略開始秒數 | 起始暖機期間不判定低速 | 20 秒 |
| 低速門檻 | 嚴格低於此值才標記 | 100 Mbps |
| 協定 | TCP 或 UDP | TCP |
| 傳輸方向 | 上傳：本機 → server；下載：server → 本機 | 上傳 |
| 平行連線數 | 多條 stream，以 SUM 合計速率判定 | 1 |
| UDP Mbps／每條 | UDP 每條連線的目標發送速率 | 1000 Mbps |
| iperf3 執行檔 | 自動尋找包內程式，也可自行選擇 | 自動 |
| 結果資料夾 | 儲存每次測試的圖表與紀錄 | EXE 旁的 `gui-results` |

「iperf3 原始輸出」及 `iperf.log` 的 bitrate 顯示 **Mbits/sec**，與圖表的 Mbps 等義。進行測試時會鎖定測速參數，時間顯示單位仍可切換；「停止」或關閉視窗會停止本程式啟動的 iperf3，並保存已收到的資料。

## 即時曲線與時間單位

圖表上方可選 **自動／秒／分／時／天**，測試中也能切換；橫軸是時間，縱軸維持 Mbps。自動模式在圖示時間範圍達 60 秒、1 小時、1 天時切換為分、時、天。

曲線平滑連接取樣點，保留藍色取樣點及低速紅點。平滑只是視覺插值，不會新增超出相鄰顯示點範圍的高低點；低速判定與所有統計仍使用原始資料。

PNG 保存整段測試總覽，採用停止當下的單位；縮放或其後切換只調整畫面。CSV／事件表仍以秒記錄。時間單位可透過「儲存設定」保存在 `config.json` 的 `time_unit`（`auto`／`seconds`／`minutes`／`hours`／`days`）。

### 放大查看低速事件

- 滑鼠滾輪或「＋／－」可縮放橫軸；左鍵拖曳或下方水平捲軸可左右移動。
- 點選低速事件列，直接放大到該事件前後。事件表提供垂直捲軸，保留本次測試的全部事件。
- 手動查看歷史時，新資料不會重設檢視範圍。按「跟隨最新」恢復追蹤，按「顯示全部」回到總覽。
- 多天總覽使用最高／最低及低速代表點加快繪圖；放大後恢復該區間逐筆資料。原始紀錄、統計及低速事件不刪減。

## 低速時透過 SSH 擷取 MCS

右上角「SSH / MCS 設定」可設定 SSH IP、port、帳號、VAP 與本次密碼。預設關閉，**IP 留白時完全不連線**。勾選啟用並填入設備 IP 後，先按「測試 SSH/MCS」，核對首次連線的設備主機指紋，再按「套用」。按主視窗「儲存設定」可保存 IP 等參數；密碼不會保存，重開程式需重新輸入。

暖機後每個低速事件開始時擷取一次：先執行 `dwpal_cli <VAP> peerlist`，再對每個 MAC 執行 `peerratesinfo`，取得最後兩筆 `MCS index`。例如 `-1、0、11` 顯示 **MCS 1＝0、MCS 2＝11**；不推定它們是 TX／RX。

結果顯示於事件表；選取事件後可到「低速 MCS 資料」頁籤查看完整紀錄。每次擷取的觸發時間、MAC、MCS、原始輸出與錯誤保存至 `mcs-events.jsonl`。連續低速不重複擷取；恢復正常後再次低速會重新觸發。前次查詢未結束時，新事件明確記為 `SKIPPED_BUSY`。

SSH 在背景執行；使用同一密碼經標準輸入交給 `sudo -S`，以 root 權限執行上述查詢。SSH 失敗不改變吞吐量的 PASS／LOW 判定。擷取有連線／命令逾時，停止測試會取消查詢；MCS 是查詢當下的狀態，可能晚於低速取樣。詳細設定及主機指紋說明見 [Windows 說明](Windows-README.md#ssh--mcs-設定)。

此功能已通過本機模擬 SSH 設備與 GUI 測試；未提供實際 SSH IP，因此尚未驗證你的設備輸出與 sudo 環境。

## 儲存設定

程式啟動時會讀取 **EXE 旁的 `config.json`**。在介面修改參數後，按「儲存設定」才會更新此檔案，下次啟動即沿用。

也可以手動編輯設定檔；格式與預設值見 [config.example.json](config.example.json)。`server` 是 IP、`reverse: true` 是下載、`protocol` 可填 `TCP`／`UDP`，`duration: 0` 是持續模式。路徑可相對於設定檔；`iperf` 空字串代表自動尋找。

設定檔格式錯誤會在視窗顯示載入失敗並保留原檔。請確認畫面參數後再測試。升級前先關閉舊程式，保留自己的 `config.json`，解壓新版後再放回。

## TCP／UDP 與低速判定

TCP 不設定發送速率上限。UDP 的目標速率是**每條連線**的值，例如 25 Mbps × 2 條，總目標約 50 Mbps；門檻仍看合計速率。若目標本身低於門檻，出現 LOW 是預期結果。

前 20 秒預設只忽略一次。只有完整位於暖機後的區間（`start >= warmup`）才判定；跨越暖機邊界的整段忽略，等於門檻不算低速。每個取樣是約一秒平均，判定精度以 iperf3 顯示的數值為準。

UDP 丟包和 jitter 留在原始 log，這版 PASS／LOW 只判斷吞吐量。已驗證 Windows client 對 Linux server 的 UDP 多連線；包內 Cygwin iperf3 3.16 作為 Windows server 時，多條 UDP 連線可能失敗，該情況可使用單條連線或 Linux server。

## 結果檔案

每次測試會建立不同的時間戳資料夾，包含：

| 檔案 | 內容 |
|---|---|
| `throughput.png` | 速率曲線、暖機與低速標記 |
| `iperf.log` | iperf3 原始輸出及錯誤 |
| `samples.csv` | 每個取樣的起訖、Mbps 和狀態 |
| `low_events.csv` | 合併後的低速時段與最低速率 |
| `summary.json` | 統計與最終結果 |
| `run.json` | 當次實際參數及執行命令 |
| `mcs-events.jsonl` | 啟用 SSH 且觸發低速時的查詢狀態、各 peer 的 MCS 與原始輸出 |

只有正常完成且無低速才是 PASS。LOW 表示完成但有低速；INTERRUPTED 表示手動停止；ERROR 表示測試或輸出失敗；NO_DATA 表示沒有暖機後的有效資料。持續模式按停止後顯示 INTERRUPTED，並保留已有統計。

`run.json` 是測試紀錄，與啟動時載入的 `config.json` 不同。

## 診斷與開發

完整操作與包內診斷方式見 [Windows 使用說明](Windows-README.md)。目前發行下載僅提供 Windows x64；原生 GUI 已在 Windows 11 驗證。

開發者可直接 clone repository，依 [原始碼開發說明](GUI-README.md) 安裝依賴、測試及建置。個人設定、測速資料、虛擬環境及建置暫存不納入 Git。
