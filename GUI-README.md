# 原始碼開發說明

**Windows 不想安裝相依套件：** 使用 [Windows x64 免安裝包](https://github.com/Poloman3657-Tommy/iperf3-monitor/releases/latest/download/iperf-monitor-windows-x64.zip)，完整解壓縮後開啟 `IperfMonitor.exe`。包內已含 Python、Tk、Matplotlib 與 iperf3；不需 pip。詳細步驟見 [Windows 說明](Windows-README.md)。以下是 Python 原始碼版的使用與開發方式。

按「開始測速」會**直接啟動本機 iperf3**，每秒更新速率曲線及低速事件；不需要 HTML、下載測試腳本或手動匯入 log。

## 在目前這台 Windows 啟動

工作區已有 Python 虛擬環境與依賴，可在 CMD 執行：

```bat
E:\Herdr\Workspace\iperf-monitor\run-gui.cmd --iperf D:\iperf3.16_64\iperf3.exe
```

也可直接開啟 `run-gui.cmd`，再按介面中的「瀏覽」選擇 `D:\iperf3.16_64\iperf3.exe`。

1. 填寫 IP、port、測試秒數、忽略秒數、門檻與連線數。
2. 選擇「上傳：本機 → server」或「下載：server → 本機」。
3. 確認本機 iperf3 執行檔及可寫入的結果資料夾，按「開始測速」。
4. 觀看即時曲線；可按「停止」。關閉視窗時會先停止自己啟動的 iperf3、保存資料後關閉。
5. 結束後按「開啟本次結果資料夾」，查看圖表與紀錄。

預設 `192.168.137.57:4477`、上傳、60 秒、忽略前 20 秒、門檻 100 Mbps、單條 TCP 連線。開始後表單鎖定，避免測試中的方向或門檻被改標；結束後可修改再測。

**持續測試：將「測試秒數」填為 `0`。** 程式使用 iperf3 `-t 0`，不設總時長上限、不定期重連，直到按「停止」、關閉視窗，或遇到測試錯誤。進度條顯示持續活動，不顯示完成百分比。暖機只忽略開始的一次 20 秒（可修改），之後持續判定低速；停止後保存已取得的紀錄及圖表。非零秒數仍依原本指定時間測試。

## 保存設定與 UDP

桌面版啟動時讀取程式旁的 `config.json`。按「儲存設定」後，下次會載入 IP、port、方向、協定、UDP 目標速率、秒數、暖機、門檻、連線數和路徑。Clone 原始碼時可將 [config.example.json](config.example.json) 複製為 `config.json`；也可在介面按儲存建立。Windows 免安裝包已附有 `config.json`。

設定檔支援部分欄位，其餘使用預設；未知／重複欄位、錯誤類型或格式會顯示錯誤並保留原檔。寫入採原子替換，失敗不破壞舊檔。位於程式資料夾內的路徑以相對路徑保存，方便搬移。`config.json` 是個人設定，已加入 `.gitignore`；`run.json` 仍僅記錄每次測試參數。

「協定」選 TCP 時維持原本不限速；選 UDP 時啟用「UDP Mbps／每條」，預設 1000 Mbps。程式加入 `-u -b`，目標是每條連線的速率，SUM 合計約等於目標 × 連線數。例：UDP 25 Mbps、2 條連線，總目標約 50 Mbps。UDP 仍以吞吐量判定低速，丟包／jitter 保留在原始 log。

UDP 多連線已對 Linux server 驗證；目前包內 Windows/Cygwin iperf3 作為 server 時有多 UDP stream 相容性問題，請在該情境使用單條連線或 Linux server。設定例子與詳細欄位見 [Windows 說明](Windows-README.md)。原有 CLI／HTML 版本仍維持各自的參數介面，本次新增的是桌面版。

## 搬到其他電腦

### 出現 `No module named 'matplotlib'`

代表目前啟動程式的 Python 沒有安裝 Matplotlib。不同 Python／虛擬環境的套件互不共用。

在目前工作區請優先使用 `run-gui.cmd`，它會選取已安裝依賴的專案 `.venv`。若在其他電腦，先完成下方安裝步驟；若直接執行 `python gui.py`，就必須用同一個 `python -m pip install -r requirements.txt` 安裝依賴。不要只用可能指向其他 Python 的 `pip install`。

```bat
python -c "import sys; print(sys.executable)"
python -m pip install -r requirements.txt
python gui.py
```

Ubuntu／macOS 若使用 `python3 gui.py`，上述命令也請改用 `python3`。在 IDE 執行時，請將 Python interpreter 選到已安裝依賴的 `.venv`。新版缺少 Matplotlib 時會列出實際 Python 路徑與精確安裝命令。

開發用途請 clone 此 repository，並在 repository 根目錄建立虛擬環境；一般使用請下載 Windows 免安裝包。

需要：

- Python **3.11 或以上**，含 Tkinter；本機驗證版本為 Python 3.12、Tk 8.6。
- `requirements.txt` 指定的 Matplotlib。
- 符合目標作業系統與 CPU 架構的 iperf3；Windows 需配套 DLL。Git repository 不包含 iperf3 二進位檔；Windows 免安裝包則已包含。

### Windows（第一次）

在 repository 根目錄的 CMD 執行：

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m tkinter
run-gui.cmd
```

`python -m tkinter` 應開啟測試視窗，確認 Tk 安裝完整後關閉它。之後雙擊 `run-gui.cmd` 即可。

### Ubuntu／macOS（第一次）

在 repository 根目錄的終端機執行：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m tkinter
sh run-gui.sh
```

Ubuntu 如缺少 Tkinter，請安裝與系統 Python 相符的 `python3-tk`；若使用自行安裝的 Python，需使用該發行方式對應的 Tk 套件。Ubuntu 的伺服器環境還需要可用的圖形桌面／DISPLAY。[Ubuntu 套件說明](https://packages.ubuntu.com/noble/python3-tk)

macOS 請使用含可用 Tkinter 的 Python；可先用 `python3 -m tkinter` 檢查。Tkinter 適用 Windows、macOS 與多數 Unix 平台，官方 Python 二進位發行版包含 Tcl/Tk。[Python 官方說明](https://docs.python.org/3/library/tkinter.html)

原始碼依實際 OS 自動偵測環境，不需要在 UI 選另一種 OS。它只能啟動本機可執行的 iperf3，不能在 Windows 直接執行 Linux 二進位檔。搜尋順序是程式旁的 iperf3，再找 PATH；找不到時按「瀏覽」，或使用 `python gui.py --iperf /完整路徑/iperf3`。

## 量測規則與產物

- 速率為十進位 Mbps，依 iperf3 每秒文字報告判定，受其顯示精度限制。
- 桌面版使用 `-f m`，所以「iperf3 原始輸出」與 `iperf.log` 的 bitrate 顯示 `Mbits/sec`。圖表仍使用等義的 Mbps；判定精度依 iperf3 顯示的數值。
- 完全位於暖機之後的區間才判定：`start >= warmup`。跨界整段忽略，等於門檻不算低速。
- 暖機後 0 Mbps 算低速；沒有收到報告不當作 0 Mbps。
- 上傳是本機 sender 的發送速率；下載是本機 receiver 的接收速率。多流只判斷 SUM 合計。
- 正常完成且沒有低速才是 PASS；LOW 表示完成但有低速；ERROR 表示測試／輸出失敗；INTERRUPTED 表示手動停止，NO_DATA 表示沒有暖機後資料。
- 每次使用不同時間戳資料夾，包含 `iperf.log`、`samples.csv`、`summary.json`、`low_events.csv`、`run.json`、`throughput.png`。log 與 samples.csv 在測試期間即時寫入，其餘在結束時儲存。
- GUI 原始輸出顯示最近 1000 行，事件表顯示最近 100 次；完整資料仍存在檔案。
- 「停止」先終止本程式啟動的 iperf3，再排空已收到的輸出，不影響其他 iperf3 程序。錯誤訊息保留在狀態列與報告中。
- 首次連線 timeout 為 5 秒；非零測試秒數的整體期限為設定秒數加 20 秒。秒數為 0 時取消總時間限制，但仍保留錯誤處理與停止功能。停止排空期限另設 5 秒。

## 技術結構與驗證

- `gui.py`：Tk 表單、即時曲線、事件佇列及主視窗生命週期。
- `gui_runner.py`：不可變設定、路徑驗證、背景測速；不呼叫 Tk。
- `config_store.py`：設定檔驗證、相對路徑與原子儲存。
- `charting.py`：即時圖／PNG 共用的時間刻度、原始取樣標記與不超調的平滑連線。
- `monitor.py`：與既有 CLI 共用解析、門檻判定、低速事件及檔案輸出；靜態圖使用獨立 Agg Figure，不切換 Tk 的 backend。

工作區測試命令：

```bat
..\.venv\Scripts\python.exe -m unittest -v test_charting test_config_store test_gui_runner test_monitor
..\.venv\Scripts\python.exe validate_settings_gui.py --iperf D:\iperf3.16_64\iperf3.exe
..\.venv\Scripts\python.exe validate_gui.py --iperf D:\iperf3.16_64\iperf3.exe
..\.venv\Scripts\python.exe validate_gui.py --iperf D:\iperf3.16_64\iperf3.exe --close-only
..\.venv\Scripts\python.exe validate_gui.py --iperf D:\iperf3.16_64\iperf3.exe --continuous
..\.venv\Scripts\python.exe validate_gui.py --iperf D:\iperf3.16_64\iperf3.exe --live --udp
```

27 項單元／子程序測試通過，涵蓋設定檔錯誤與原子儲存、相對路徑搬移、TCP／UDP 命令、暖機／門檻及停止保存。真正 Tk 測試已驗證保存設定後重新啟動、協定欄位狀態與錯誤呈現。NUC UDP 雙條下載測試共 24 秒，每條目標 25 Mbps，暖機後平均約 50.000 Mbps，4 個低速取樣合併成 1 次事件。重建的 Windows EXE 已在隔離 Python 路徑的資料夾驗證 UDP 持續模式、PNG 及設定重讀。Ubuntu／macOS 尚未有原生 GUI 實測。

2026-09-11 以 GUI 流程實測 NUC `192.168.137.57:4477`，下載 60 秒，前 20 秒忽略：最低 **496.441 Mbps**，加權平均 **850.017 Mbps**，低速 **0 次**，結果 PASS。這只代表該次觀察，長期監測可增加秒數。
