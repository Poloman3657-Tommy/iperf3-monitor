# 舊版 HTML 開發資料

目前發行下載只提供 Windows x64 免安裝包，請使用 [最新 Release](https://github.com/Poloman3657-Tommy/iperf3-monitor/releases/latest)。

舊版 HTML 的來源與固定測試資料保留在 `html-src/`，供開發與回歸檢查使用，不再提供獨立下載附件。

需要執行這組開發測試時，先在 repository 根目錄產生本機測試頁面：

```sh
python build_html.py
node --test html-src/test-core.cjs
npm ci --prefix html-src/.test-tools --cache html-src/.test-tools/.npm-cache --ignore-scripts
node html-src/test-ui.cjs
node html-src/test-shell.cjs
```

生成物、測試報告和下載 ZIP 都不納入 Git。
