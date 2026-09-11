# iperf3 桌面監測器 — Windows 免安裝版

## 開始使用

1. 將 ZIP **完整解壓縮** 到可寫入的資料夾，例如桌面。
2. 開啟 `IperfMonitor.exe`。
3. 填寫 Server IP、port，選擇上傳或下載，按「開始測速」。

已包含 Python、Tkinter/Tcl/Tk、Matplotlib、數值及繪圖依賴，以及 iperf3 3.16 與其 Windows DLL。**不需要另外安裝 Python、pip 或 Matplotlib。** 程式會自動選取 `iperf3` 子資料夾中的執行檔。

預設 `192.168.137.57:4477`、上傳、60 秒、忽略前 20 秒、低於 100 Mbps 標記。測試秒數填 **0** 可持續測試，直到按停止、關閉視窗或發生錯誤。結果預設存於程式旁的 `gui-results`，也可在介面另選資料夾。

## 檔案結構

```text
IperfMonitor/
  IperfMonitor.exe        桌面程式
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

這個診斷只在 `127.0.0.1` 執行約 4 秒的回環測試，使用真正 Tk 事件循環，檢查持續測試、停止及 PNG 輸出；不連到外部 server。結果寫入指定 JSON 及旁邊的 `run-data` 資料夾。
