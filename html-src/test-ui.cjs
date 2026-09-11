// Offline DOM integration checks. No browser, external URLs, or network requests.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {JSDOM,VirtualConsole}=require('./.test-tools/node_modules/jsdom');
const {createCanvas}=require('./.test-tools/node_modules/@napi-rs/canvas');
const root=path.resolve(__dirname,'..');
const html=fs.readFileSync(path.join(root,'portable/iperf-monitor.html'),'utf8');
// Synthetic fixture is versioned so a fresh clone does not require private lab logs.
const raw=fs.readFileSync(path.join(__dirname,'fixtures/download.txt'),'utf8');

function open(source){
  const downloads=[],errors=[],canvases=new WeakMap(),blobs=new Map();
  const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));
  const dom=new JSDOM(source,{runScripts:'dangerously',pretendToBeVisual:true,virtualConsole:vc,beforeParse(w){
    w.ResizeObserver=class{observe(){}};
    w.HTMLCanvasElement.prototype.getBoundingClientRect=function(){return {width:820,height:350,left:0,top:0};};
    w.HTMLCanvasElement.prototype.getContext=function(){const c=createCanvas(this.width,this.height);canvases.set(this,c);return c.getContext('2d');};
    w.HTMLCanvasElement.prototype.toBlob=function(callback){callback(new w.Blob([canvases.get(this).toBuffer('image/png')],{type:'image/png'}));};
    w.URL.createObjectURL=blob=>{const id='blob:offline-test-'+blobs.size;blobs.set(id,blob);return id;};
    w.URL.revokeObjectURL=()=>{};
    w.HTMLAnchorElement.prototype.click=function(){downloads.push({name:this.download,blob:blobs.get(this.href)});};
  }});
  const w=dom.window,$=id=>w.document.getElementById(id);
  const set=(id,value)=>{$(id).value=String(value);$(id).dispatchEvent(new w.Event('input',{bubbles:true}));};
  return {dom,w,$,set,downloads,errors,canvases};
}
function readBlob(w,blob,asText=true){return new Promise((resolve,reject)=>{const reader=new w.FileReader();reader.onerror=reject;reader.onload=()=>resolve(reader.result);if(asText)reader.readAsText(blob);else reader.readAsArrayBuffer(blob);});}

(async()=>{
  const a=open(html);
  assert.equal(a.$('badge').textContent,'尚未匯入');
  a.set('ip','10.0.0.2');a.set('port',5201);a.set('direction','download');
  assert.match(a.$('command').value,/-c 10\.0\.0\.2 -p 5201/);
  assert.ok(a.$('command').value.includes(' -R'));
  a.set('port',0);assert.equal(a.$('copy').disabled,true);assert.equal(a.$('run').disabled,true);a.set('port',4477);a.set('ip','192.168.137.57');
  a.$('paste').value=raw;a.$('analyzepaste').click();
  assert.equal(a.$('badge').textContent,'PASS');
  assert.equal(a.$('min').textContent,'600.000');
  assert.equal(a.$('average').textContent,'892.500');
  assert.ok(a.$('meta').textContent.includes('下載'));
  a.set('threshold',900);assert.equal(a.$('badge').textContent,'LOW');assert.ok(a.$('eventrows').children.length>0);
  a.set('threshold',100);assert.equal(a.$('badge').textContent,'PASS');
  assert.ok(a.$('run').closest('header'));assert.equal(a.$('run').disabled,false);
  a.$('run').click();const batch=await readBlob(a.w,a.downloads.at(-1).blob);assert.ok(batch.includes(' -R'));assert.ok(batch.includes('-c 192.168.137.57 -p 4477'));assert.ok(batch.includes('if exist "iperf_'));assert.ok(a.$('runhelp').textContent.includes('雙擊執行'));
  for(const platform of ['ubuntu','macos']){
    a.set('platform',platform);
    assert.equal(a.$('batch').textContent,'下載 .sh');
    assert.ok(!a.$('command').value.includes('iperf3.exe'));
    a.$('run').click();assert.equal(a.downloads.at(-1).name,'run-iperf.sh');
    const script=await readBlob(a.w,a.downloads.at(-1).blob);
    assert.ok(script.startsWith('#!/bin/sh\n'));assert.ok(!script.includes('\r'));assert.ok(script.includes(' -R'));
    assert.ok(a.$('runhelp').textContent.includes('sh run-iperf.sh'));
  }
  a.$('report').click();const platformReport=open(await readBlob(a.w,a.downloads.at(-1).blob));
  assert.equal(platformReport.$('platform').value,'macos');assert.equal(platformReport.$('badge').textContent,'PASS');
  assert.deepEqual(platformReport.errors,[]);platformReport.dom.window.close();a.set('platform','windows');
  a.$('png').click();const png=Buffer.from(await readBlob(a.w,a.downloads.at(-1).blob,false));assert.equal(png.subarray(1,4).toString(),'PNG');
  const validation=path.join(root,'validation','portable');fs.mkdirSync(validation,{recursive:true});fs.writeFileSync(path.join(validation,'download-export.png'),png);
  a.$('csv').click();const csv=await readBlob(a.w,a.downloads.at(-1).blob);assert.equal(csv.trim().split(/\r?\n/).length,61);
  a.$('report').click();const report=await readBlob(a.w,a.downloads.at(-1).blob);
  const b=open(report);assert.equal(b.$('badge').textContent,'PASS');assert.equal(b.$('min').textContent,'600.000');assert.equal(b.$('direction').value,'download');
  fs.writeFileSync(path.join(validation,'fixture-report.html'),report,'utf8');
  // Untrusted strings must survive export as text, without becoming HTML/script.
  a.$('paste').value=raw+'\n</script><img id="untrusted" src=x onerror=alert(1)>';a.$('analyzepaste').click();a.$('report').click();
  const hostile=await readBlob(a.w,a.downloads.at(-1).blob);const c=open(hostile);assert.equal(c.$('untrusted'),null);assert.equal(c.$('badge').textContent,'PASS');
  assert.deepEqual(a.errors,[]);assert.deepEqual(b.errors,[]);assert.deepEqual(c.errors,[]);
  a.dom.window.close();b.dom.window.close();c.dom.window.close();
  console.log('PASS: settings, direction, invalid port, fixture import, threshold recalculation, CMD/PNG/CSV export, standalone report reload, safe text embedding.');
})().catch(e=>{console.error(e);process.exitCode=1;});
