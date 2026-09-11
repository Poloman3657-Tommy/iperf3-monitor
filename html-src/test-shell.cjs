// Exercise generated POSIX scripts with a local executable fixture, never a network test.
const fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process'),assert=require('node:assert/strict');
const core=require('./core.js');
const shell=process.platform==='win32'?'C:\\Program Files\\Git\\usr\\bin\\sh.exe':'/bin/sh';
const base=path.resolve(__dirname,'../validation/portable');fs.mkdirSync(base,{recursive:true});
const root=fs.mkdtempSync(path.join(base,'shell-check-'));
const env={...process.env};delete env.Path;env.PATH='/usr/bin:/bin';
for(const platform of ['ubuntu','macos']){
  for(const exitCode of [0,7]){
    const cwd=path.join(root,platform+' path with spaces '+exitCode);fs.mkdirSync(cwd);
    const options={platform,ip:'10.0.0.2',port:5201,duration:60,warmup:20,threshold:100,parallel:2,reverse:true};
    const script=core.script(options,'test.log');fs.writeFileSync(path.join(cwd,script.name),script.content);
    fs.writeFileSync(path.join(cwd,'iperf3'),`#!/bin/sh\nprintf '%s\\n' "$@" > invoked-args.txt\nprintf '%s\\n' 'fixture output'\nexit ${exitCode}\n`);
    let result=cp.spawnSync(shell,['-n',script.name],{cwd,env,encoding:'utf8',windowsHide:true});assert.equal(result.status,0,result.stderr);
    result=cp.spawnSync(shell,['-c','chmod +x ./iperf3 && sh ./run-iperf.sh'],{cwd,env,encoding:'utf8',windowsHide:true});assert.equal(result.status,exitCode,result.stderr);
    const args=fs.readFileSync(path.join(cwd,'invoked-args.txt'),'utf8');assert.ok(args.includes('10.0.0.2\n-p\n5201'));assert.ok(args.includes('-R'));
    assert.equal(fs.readFileSync(path.join(cwd,'test.log'),'utf8'),'fixture output\n');
    result=cp.spawnSync(shell,[script.name],{cwd,env,encoding:'utf8',windowsHide:true});assert.equal(result.status,2,result.stderr);
    assert.equal(fs.readFileSync(path.join(cwd,'test.log'),'utf8'),'fixture output\n');
  }
}
const missing=path.join(root,'missing executable');fs.mkdirSync(missing);
fs.writeFileSync(path.join(missing,'run-iperf.sh'),core.script({platform:'ubuntu',ip:'127.0.0.1',port:4477,duration:60,warmup:20,threshold:100,parallel:1},'test.log').content);
const result=cp.spawnSync(shell,['run-iperf.sh'],{cwd:missing,env,encoding:'utf8',windowsHide:true});assert.equal(result.status,127,result.stderr);
console.log('PASS: POSIX syntax, spaced paths, local executable fallback, direction/port, success/failure exit status, collision guard, missing executable.');
