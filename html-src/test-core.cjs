// Test measurement intent independently of the browser UI.
const assert = require('node:assert/strict');
const {test} = require('node:test');
const core = require('./core.js');
const row = (a,b,v,unit='M',id='5',bytes='1 MBytes') => `[ ${id}] ${a}-${b} sec ${bytes} ${v} ${unit}bits/sec`;
test('warm-up and crossing intervals are excluded; exactly 100 passes', () => {
  const result = core.analyze([row(0,19,1),row(19,20.01,1),row(20.01,21,100),row(21,22,99.999),'iperf Done.'].join('\n'),20,100);
  assert.equal(result.samples[1].status,'WARMUP');
  assert.equal(result.samples[2].status,'OK');
  assert.equal(result.lowSamples,1);
  assert.equal(result.verdict,'LOW');
});
test('zero Bytes stays a sample; summary rows are not counted twice', () => {
  const result = core.analyze([row(0,1,0,'K','5','0.00 Bytes'),row(0,1,0)+' sender','iperf Done.'].join('\n'),0,100);
  assert.equal(result.samples.length,1);
  assert.equal(result.min,0);
  assert.equal(result.lowSeconds,1);
});
test('parallel traffic uses SUM only and Gbits uses decimal conversion', () => {
  const result = core.analyze([row(0,1,600),row(0,1,600,'M','7'),row(0,1,1.2,'G','SUM'),'iperf Done.'].join('\n'),0,100);
  assert.equal(result.samples.length,1);
  assert.equal(result.average,1200);
});
test('only adjacent low intervals merge; average is time weighted', () => {
  const result = core.analyze([row(0,1,50),row(1,3,80),row(3,4,200),row(4,5,90),'iperf Done.'].join('\n'),0,100);
  assert.equal(result.events.length,2);
  assert.equal(result.events[0].seconds,3);
  assert.equal(result.average,100);
});
test('error, incomplete, missing, and warm-up-only data cannot pass', () => {
  assert.equal(core.analyze(row(0,1,900),0,100).verdict,'INCOMPLETE');
  assert.equal(core.analyze(row(0,1,900)+'\niperf3: error - lost\niperf Done.',0,100).verdict,'ERROR');
  assert.equal(core.analyze('iperf3: error - refused',20,100).verdict,'ERROR');
  assert.equal(core.analyze(row(0,1,900)+'\niperf Done.',20,100).verdict,'NO_DATA');
  assert.equal(core.analyze([row(0,1,900),row(2,3,900),'iperf Done.'].join('\n'),0,100).verdict,'INCOMPLETE');
  assert.throws(()=>core.analyze('not an iperf log',20,100));
});
test('log metadata identifies actual peer and download direction', () => {
  const result=core.analyze('Connecting to host 192.168.137.57, port 4477\nReverse mode, remote host 192.168.137.57 is sending\n'+row(0,1,900)+'\niperf Done.',0,100);
  assert.equal(result.peer.ip,'192.168.137.57');
  assert.equal(result.peer.port,4477);
  assert.equal(result.peer.reverse,true);
});
test('command accepts editable IP/port and reverses only on request', () => {
  const opts={ip:'192.168.137.57',port:4477,duration:60,warmup:20,threshold:100,parallel:1,reverse:false};
  assert.match(core.command(opts,'test.log'),/-c 192\.168\.137\.57 -p 4477/);
  assert.ok(!core.command(opts,'test.log').includes(' -R'));
  assert.ok(core.command({...opts,reverse:true},'test.log').includes(' -R'));
  assert.match(core.command({...opts,ip:'10.0.0.2',port:5201},'test.log'),/-c 10\.0\.0\.2 -p 5201/);
});
test('reject invalid settings and shell metacharacters instead of executing them', () => {
  const opts={ip:'192.168.137.57',port:4477,duration:60,warmup:20,threshold:100,parallel:1,reverse:false};
  for(const change of [{ip:'1.2.3.4 & calc'},{ip:'999.1.2.3'},{port:0},{port:65536},{duration:20},{threshold:NaN},{parallel:0}]){
    assert.throws(()=>core.command({...opts,...change},'test.log'));
  }
  assert.throws(()=>core.command(opts,'bad"&calc.log'));
});
test('reject mixed runs before SUM filtering and never pass interrupted data', () => {
  const mixed=['Connecting to host 1.1.1.1, port 4477',row(0,1,50),'iperf Done.',
    'Connecting to host 2.2.2.2, port 4477',row(0,1,900,'M','SUM'),'iperf Done.'].join('\n');
  assert.throws(()=>core.analyze(mixed,0,100));
  assert.throws(()=>core.analyze(row(0,1,900)+'\niperf Done.\nConnecting to host 1.1.1.1, port 4477\nConnecting to host 2.2.2.2, port 4477',0,100));
  assert.equal(core.analyze(row(0,1,900)+'\niperf3: interrupt - the client has terminated\niperf Done.',0,100).verdict,'INCOMPLETE');
});
test('generated command guards existing result files', () => {
  const cmd=core.command({ip:'127.0.0.1',port:4477,duration:60,warmup:20,threshold:100,parallel:1},'test.log');
  assert.ok(cmd.startsWith('if exist "test.log"'));
});
test('Ubuntu and macOS commands use POSIX shell, keep arguments, and preserve existing logs', () => {
  const opts={ip:'10.0.0.2',port:5201,duration:60,warmup:20,threshold:100,parallel:2,reverse:true};
  for(const platform of ['ubuntu','macos']){
    const command=core.command({...opts,platform},'test.log');
    assert.ok(!command.includes('iperf3.exe'));
    assert.ok(command.includes('command -v iperf3'));
    assert.ok(command.includes('[ -x ./iperf3 ]'));
    assert.ok(command.includes('set -C'));
    assert.ok(command.includes('-c 10.0.0.2 -p 5201'));
    assert.ok(command.includes(' -R'));
  }
  assert.throws(()=>core.command({...opts,platform:'unknown'},'test.log'));
});
test('downloaded scripts match the platform and preserve process exit status', () => {
  const opts={ip:'127.0.0.1',port:4477,duration:60,warmup:20,threshold:100,parallel:1};
  const windows=core.script({...opts,platform:'windows'},'test.log');
  assert.equal(windows.name,'run-iperf.cmd');
  assert.ok(windows.content.includes('@echo off\r\n'));
  assert.ok(windows.content.includes('exit /b %IPERF_EXIT%'));
  for(const platform of ['ubuntu','macos']){
    const shell=core.script({...opts,platform},'test.log');
    assert.equal(shell.name,'run-iperf.sh');
    assert.ok(shell.content.startsWith('#!/bin/sh\n'));
    assert.ok(!shell.content.includes('\r'));
    assert.ok(shell.content.includes('exit "$iperf_exit"'));
  }
});
