/* Pure parsing and measurement rules, shared by browser UI and Node checks. */
(function(root) {
  'use strict';
  const interval = /^\[\s*(\d+|SUM)\s*\]\s+(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s+sec\s+\S+\s+[KMGT]?Bytes\s+(\d+(?:\.\d+)?)\s+([KMGT]?)bits\/sec\b/;
  const units = {'':1e-6,K:1e-3,M:1,G:1000,T:1e6};

  function validate(options) {
    const o = {...options, platform:options.platform??'windows', ip:String(options.ip).trim()};
    if(!['windows','ubuntu','macos'].includes(o.platform)) throw Error('請選擇 Windows、Ubuntu 或 macOS。');
    // IPv4 only keeps generated CMD commands simple and prevents shell injection.
    const parts = o.ip.split('.');
    if(parts.length !== 4 || parts.some(p=>!/^\d{1,3}$/.test(p) || Number(p)>255))
      throw Error('請輸入有效的 IPv4 位址，例如 192.168.137.57。');
    if(!Number.isInteger(o.port) || o.port<1 || o.port>65535) throw Error('Port 必須是 1–65535 的整數。');
    if(!Number.isFinite(o.warmup) || o.warmup<0) throw Error('忽略時間必須是大於或等於 0 的數字。');
    if(!Number.isInteger(o.duration) || o.duration<Math.ceil(o.warmup)+1 || o.duration>86400)
      throw Error('測試秒數必須比忽略時間至少多 1 秒，最多 86400 秒。');
    if(!Number.isFinite(o.threshold) || o.threshold<=0) throw Error('門檻必須大於 0 Mbps。');
    if(!Number.isInteger(o.parallel) || o.parallel<1 || o.parallel>128) throw Error('連線數必須是 1–128 的整數。');
    return o;
  }

  function command(options, filename) {
    const o=validate(options);
    if(!/^[A-Za-z0-9_.-]+\.log$/.test(filename)) throw Error('紀錄檔名不合法。');
    const args=`-c ${o.ip} -p ${o.port} -t ${o.duration} -i 1 -f k -P ${o.parallel} --forceflush --connect-timeout 5000${o.reverse?' -R':''}`;
    if(o.platform==='windows'){
      const run=`iperf3.exe ${args} > "${filename}" 2>&1`;
      return `if exist "${filename}" (echo ERROR: Log exists. Generate a new command. & cmd /c exit 2) else (${run})`;
    }
    // A subshell keeps locale, noclobber, and helper variables out of the user's shell.
    return `(if [ -e "${filename}" ] || [ -L "${filename}" ]; then printf '%s\\n' 'ERROR: Log exists. Generate a new command.' >&2; exit 2; fi; if command -v iperf3 >/dev/null 2>&1; then iperf_bin=iperf3; elif [ -x ./iperf3 ]; then iperf_bin=./iperf3; else printf '%s\\n' 'ERROR: iperf3 not found in PATH or current folder.' >&2; exit 127; fi; set -C; LC_ALL=C "$iperf_bin" ${args} > "${filename}" 2>&1)`;
  }

  function script(options, filename) {
    const o=validate(options),run=command(o,filename);
    if(o.platform==='windows'){
      return {name:'run-iperf.cmd',content:[
        '@echo off','cd /d "%~dp0"','if not exist "iperf3.exe" (',
        '  echo ERROR: Put this file next to iperf3.exe and its DLLs.','  pause','  exit /b 2',')',
        'echo Running iperf3. Please wait...',run,'set "IPERF_EXIT=%errorlevel%"',
        'echo Finished. iperf3 exit code: %IPERF_EXIT%',`echo Import ${filename} into the HTML tool.`,
        'pause','exit /b %IPERF_EXIT%',''].join('\r\n')};
    }
    // POSIX sh works in Ubuntu and macOS; no Bash-only features or GNU-only flags.
    return {name:'run-iperf.sh',content:[
      '#!/bin/sh',`# iperf3 monitor: ${o.platform}`,
      'CDPATH= cd -P "$(dirname "$0")" || exit 2',
      "printf '%s\\n' 'Running iperf3. Please wait...'",run,'iperf_exit=$?',
      'printf "Finished. iperf3 exit code: %s\\n" "$iperf_exit"',
      `printf '%s\\n' 'Import ${filename} into the HTML tool.'`,'exit "$iperf_exit"',''].join('\n')};
  }

  function analyze(text, warmup, threshold) {
    if(!Number.isFinite(warmup) || warmup<0 || !Number.isFinite(threshold) || threshold<=0)
      throw Error('忽略時間或門檻設定不合法。');
    const raw = [];
    const lines=String(text).replace(/^\uFEFF/,'').split(/\r?\n/);
    if(lines.filter(line=>/^Connecting to host /.test(line.trim())).length>1 || lines.filter(line=>line.trim()==='iperf Done.').length>1)
      throw Error('紀錄包含多次測試，請分別匯入每次測試的原始檔案。');
    let error=null, done=false, omitted=false, interrupted=false;
    for(const line of lines) {
      if(/iperf3:\s*error/i.test(line)) error=line.trim();
      if(/iperf3:\s*interrupt/i.test(line)) interrupted=true;
      if(line.trim()==='iperf Done.') done=true;
      if(/\(omitted\)/.test(line)) omitted=true;
      if(/\b(sender|receiver)\s*$/.test(line)) continue;
      const m=line.trim().match(interval);
      if(!m) continue;
      const sample={stream:m[1],start:Number(m[2]),end:Number(m[3]),mbps:Number(m[4])*units[m[5]]};
      if(sample.start===sample.end) continue;
      if(sample.end<sample.start || !Number.isFinite(sample.mbps)) throw Error('紀錄中有不合法的時間或速率。');
      raw.push(sample);
    }
    if(omitted) throw Error('此紀錄使用了 -O，時間軸會重設。請使用本頁產生的命令重新測試。');
    const hasSum=raw.some(s=>s.stream==='SUM');
    const samples=raw.filter(s=>(s.stream==='SUM')===hasSum).map(s=>({...s,status:s.start<warmup?'WARMUP':s.mbps<threshold?'LOW':'OK'}));
    if(!samples.length && !error) throw Error('找不到 iperf3 每秒速率。請匯入原始 .log/.txt，勿使用 -J 或 -O。');
    let gap=samples.length>0 && samples[0].start>0.011;
    for(let i=1;i<samples.length;i++) if(Math.abs(samples[i].start-samples[i-1].end)>0.011) gap=true;
    const measured=samples.filter(s=>s.status!=='WARMUP');
    const lows=measured.filter(s=>s.status==='LOW');
    const events=[];
    let previousLow=false;
    for(const s of samples) {
      if(s.status!=='LOW') {previousLow=false;continue;}
      const last=events.at(-1);
      if(previousLow && Math.abs(last.end-s.start)<0.011){last.end=s.end;last.min=Math.min(last.min,s.mbps);}
      else events.push({start:s.start,end:s.end,min:s.mbps});
      previousLow=true;
    }
    events.forEach(e=>e.seconds=e.end-e.start);
    const seconds=measured.reduce((n,s)=>n+s.end-s.start,0);
    const min=measured.length?measured.reduce((n,s)=>Math.min(n,s.mbps),Infinity):null;
    const average=seconds?measured.reduce((n,s)=>n+s.mbps*(s.end-s.start),0)/seconds:null;
    const peerMatch=String(text).match(/Connecting to host ([^,\s]+), port (\d+)/);
    const peer=peerMatch?{ip:peerMatch[1],port:Number(peerMatch[2]),reverse:/Reverse mode, remote host/.test(text)}:null;
    const verdict=error?'ERROR':!done||gap||interrupted?'INCOMPLETE':!measured.length?'NO_DATA':lows.length?'LOW':'PASS';
    return {samples,events,seconds,min,average,peer,lowSamples:lows.length,
      lowSeconds:lows.reduce((n,s)=>n+s.end-s.start,0),verdict,
      error:error||(gap?'資料含缺漏、重疊或多次測試；不判定為通過。':!done||interrupted?'測試未正常結束；僅顯示已取得資料。':null)};
  }
  const api={validate,command,script,analyze};
  if(typeof module!=='undefined' && module.exports) module.exports=api;
  root.IperfCore=api;
})(globalThis);
