# iperf3 Monitor

使用 iperf3 監測吞吐量、忽略起始暖機時間，標示低速時段並保存曲線與紀錄。提供 Python 桌面版、Windows 免安裝版、命令列版及單一離線 HTML。

## 下載

請至 [Releases](https://github.com/Poloman3657-Tommy/iperf3-monitor/releases/latest) 下載：

| 版本 | 檔案 | 使用方式 |
|---|---|---|
| Windows x64 免安裝 | `iperf-monitor-windows-x64.zip` | 完整解壓縮，開啟 `IperfMonitor.exe`；內含 Python、Tk、Matplotlib 及 iperf3 |
| Python 桌面原始碼 | `iperf-monitor-python-gui.zip` | 安裝依賴後執行 `gui.py` |
| 單一 HTML | `iperf-monitor.html` | 選擇環境、產生命令，本機執行後匯入 log 畫圖 |

Windows 包需保留整個資料夾，不能只複製 EXE。原始碼適用 Windows、Ubuntu、macOS；目前原生 GUI 與免安裝包已在 Windows 驗證，其他系統需自行準備相容 Python/Tk 與 iperf3。

## 功能

- 可調 IP、port、上傳／下載、測試時間、暖機時間、低速門檻與平行連線數。
- 桌面版按「開始／停止」直接控制本機 iperf3，即時顯示曲線。
- 桌面版支援 TCP／UDP，UDP 可指定每條連線的目標 Mbps。
- 桌面版啟動時載入 `config.json`，按「儲存設定」保存 IP、port、協定與其他參數。
- Python 桌面／CLI 的測試秒數設為 **0** 可持續測試，直到停止或發生錯誤。
- 預設忽略前 **20 秒**；之後 **<100 Mbps** 標記低速，等於門檻不算。
- 保存原始 log、每秒 CSV、事件 CSV、摘要 JSON、執行參數及 PNG。
- 單一 HTML 完全離線，可選 Windows／Ubuntu／macOS 並下載 `.cmd`／`.sh`；一般瀏覽器不能直接啟動 iperf3。

## Python 桌面版

需要 Python 3.11+、Tkinter、Matplotlib，以及本機可執行的 iperf3。

```sh
git clone https://github.com/Poloman3657-Tommy/iperf3-monitor.git
cd iperf3-monitor
python -m venv .venv
```

Windows CMD：

```bat
.venv\Scripts\python.exe -m pip install -r requirements.txt
run-gui.cmd
```

Ubuntu／macOS：

```sh
.venv/bin/python -m pip install -r requirements.txt
sh run-gui.sh
```

若系統命令是 `python3`，建立虛擬環境時也改用 `python3`。在介面選擇 iperf3 執行檔，填入自己的 server IP／port，再開始測試。Server 需另行啟動，例如：

```sh
iperf3 -s -p 4477
```

[桌面版詳細說明](GUI-README.md) · [Windows 免安裝說明](Windows-README.md) · [HTML 說明](portable/README.md)

## 命令列

使用已安裝依賴的 Python；`--iperf` 指定實際路徑，或可由 PATH 找到的名稱。

```sh
python monitor.py --iperf iperf3 --server 192.168.137.57 --port 4477 --duration 60
python monitor.py --iperf iperf3 --server 192.168.137.57 --port 4477 --duration 0 -R
```

`-R`／`--reverse` 表示下載；省略方向參數為上傳。Ctrl+C 停止並保存已取得資料。

## 判定與資料

時間從流量開始計算。只有 `start >= warmup` 的完整取樣區間才列入低速判定；跨越暖機邊界的整段忽略。多流使用 SUM 合計，約一秒平均不能識別更短的瞬間下降。速率依 iperf3 文字輸出的精度判定，採十進位 Mbps。

只有正常完成且無低速才是 PASS。手動停止是 INTERRUPTED，連線／輸出錯誤是 ERROR，不會誤判通過。持續模式若程序非預期退出，也不算通過。

個人測速資料、虛擬環境與建置暫存不納入 Git；ZIP 發行檔放在 Releases。HTML 測試使用 repository 內明確標示的人工固定資料。

## 測試

```sh
python -m unittest -v test_config_store test_gui_runner test_monitor
node --test html-src/test-core.cjs
npm ci --prefix html-src/.test-tools --cache html-src/.test-tools/.npm-cache --ignore-scripts
node html-src/test-ui.cjs
node html-src/test-shell.cjs
```

Python 測試不需要真實 server；DOM 測試需要 Node.js 24。Shell 測試使用 POSIX sh，Windows 需 Git for Windows。真實 Tk／回環驗證可執行 `validate_gui.py --iperf <path>`，持續模式加 `--continuous`。

## 建置

```sh
python build_html.py
python build_gui_package.py
```

Windows 免安裝包在 Windows 上建立，並使用已安裝依賴的 Python：

```bat
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --distpath build-windows\dist --workpath build-windows\work build-windows.spec
python prepare_windows_bundle.py C:\tools\iperf3
python zip_windows_bundle.py
```

`prepare_windows_bundle.py` 會複製所提供的 iperf3/DLL、收集授權並建立 SHA-256 manifest。免安裝包附有第三方套件的授權與來源說明。
