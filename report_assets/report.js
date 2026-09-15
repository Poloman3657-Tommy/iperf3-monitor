(function () {
  'use strict';
  const units = {seconds:{factor:1,label:'秒'},minutes:{factor:60,label:'分'},hours:{factor:3600,label:'時'},days:{factor:86400,label:'天'}};
  const clamp = (v,a,b) => Math.max(a,Math.min(b,v));
  function timeUnit(name,width) {
    return units[name === 'auto' ? (width<60?'seconds':width<3600?'minutes':width<86400?'hours':'days') : name];
  }
  class Viewport {
    constructor(total) { this.total=Math.max(1,total); this.all(); }
    all() { this.left=0; this.right=this.total; }
    window(left,width) { width=clamp(width,1,this.total); this.left=clamp(left,0,this.total-width); this.right=this.left+width; }
    zoom(factor,anchor=(this.left+this.right)/2) {
      anchor=clamp(anchor,this.left,this.right);
      const fraction=(anchor-this.left)/(this.right-this.left), width=clamp((this.right-this.left)*factor,1,this.total);
      this.window(anchor-fraction*width,width);
    }
    pan(seconds) { this.window(this.left+seconds,this.right-this.left); }
    focus(start,end) { const padding=Math.max(5,(end-start)*.5); this.window(start-padding,end-start+2*padding); }
  }
  function bound(rows,value,column,upper=false) {
    let lo=0,hi=rows.length;
    while(lo<hi) { const mid=(lo+hi)>>>1; if(rows[mid][column]<value || (upper && rows[mid][column]===value)) lo=mid+1; else hi=mid; }
    return lo;
  }
  function nearestSample(rows,seconds) {
    const i=bound(rows,seconds,1);
    return i<rows.length && rows[i][0]<=seconds ? rows[i] : null;
  }
  function selectPoints(rows,left,right,budget=4000) {
    const first=Math.max(0,bound(rows,left,1)-1), last=Math.min(rows.length,bound(rows,right,0,true)+1);
    const overview=last-first>budget, points=[], width=overview?Math.ceil((last-first)/Math.max(1,Math.floor(budget/5))):1;
    let group=0, start=first;
    while(start<last) {
      let finish=start+1;
      while(finish<last && Math.abs(rows[finish-1][1]-rows[finish][0])<.011) finish++;
      for(let a=start;a<finish;a+=width) {
        const b=Math.min(finish,a+width); let min=a,max=a,low=-1;
        for(let i=a;i<b;i++) { if(rows[i][2]<rows[min][2]) min=i; if(rows[i][2]>rows[max][2]) max=i; if(rows[i][3]==='LOW' && (low<0 || rows[i][2]<rows[low][2])) low=i; }
        const keep=new Set([a,b-1,min,max]); if(low>=0) keep.add(low);
        for(const index of [...keep].sort((x,y)=>x-y)) points.push({index,row:rows[index],group});
      }
      start=finish; group++;
    }
    return {points,overview};
  }
  if(typeof module !== 'undefined' && module.exports) module.exports={Viewport,timeUnit,selectPoints,nearestSample};
  if(typeof document === 'undefined') return;

  const $=id=>document.getElementById(id), number=v=>v==null?'—':Number(v).toLocaleString('en-US',{maximumFractionDigits:3});
  const date=v=>v?String(v).replace('T',' '):'未提供';
  function elapsed(t) { const d=Math.floor(t/86400); return (d?d+'天 ':'')+[Math.floor(t/3600)%24,Math.floor(t/60)%60].map(n=>String(n).padStart(2,'0')).join(':')+':'+(t%60).toFixed(2).padStart(5,'0'); }
  function fail(error) { $('error').hidden=false; $('error').textContent='報告無法顯示：'+error.message; }
  try {
    const data=JSON.parse($('report-data').textContent), rows=data.samples, cfg=data.config, summary=data.summary, events=summary.events;
    const view=new Viewport(rows.length?rows[rows.length-1][1]:1);
    const canvas=$('chart'), ctx=canvas.getContext('2d'), timeline=$('timeline');
    let selected=-1,page=0,drag=null,frame=0,geometry=null,desiredScroll=0;
    const pageSize=100;
    $('unit').value=cfg.time_unit;
    $('verdict').textContent=summary.verdict; $('verdict').dataset.state=summary.verdict;
    $('subtitle').textContent=`${cfg.protocol} · ${cfg.reverse?'下載 server → 本機':'上傳 本機 → server'} · ${cfg.server}:${cfg.port} · 忽略前 ${cfg.warmup} 秒 · 門檻 ${cfg.threshold} Mbps`;
    $('minimum').textContent=number(summary.min_mbps); $('average').textContent=number(summary.average_mbps);
    $('low-seconds').textContent=number(summary.low_seconds); $('event-count').textContent=number(events.length);
    if(summary.error) { $('error').hidden=false; $('error').textContent=summary.error; }
    $('footer').textContent=`產生時間 ${date(data.generated_at)} · ${number(rows.length)} 筆原始取樣完整內嵌 · 離線報告，不會連線或執行測速。圖表曲線僅為顯示插值，統計使用原始數據。Fail 日期為本機收到第一筆低速報告的時間。`;
    function schedule() { if(!frame) frame=requestAnimationFrame(()=>{frame=0;try{draw();}catch(e){fail(e);}}); }
    function draw() {
      const rect=canvas.getBoundingClientRect(), w=Math.max(300,rect.width),h=Math.max(250,rect.height),ratio=window.devicePixelRatio||1;
      canvas.width=Math.round(w*ratio); canvas.height=Math.round(h*ratio); ctx.setTransform(ratio,0,0,ratio,0,0);
      const area={x:72,y:20,w:w-90,h:h-76}, width=view.right-view.left, unit=timeUnit($('unit').value,width);
      const {points,overview}=selectPoints(rows,view.left,view.right);
      let maximum=Math.max(cfg.threshold,1); for(const p of points) maximum=Math.max(maximum,p.row[2]); maximum*=1.18;
      const x=t=>area.x+(t-view.left)/width*area.w, y=r=>area.y+area.h-r/maximum*area.h;
      geometry={area,x,y,w,h};
      ctx.fillStyle='#fff';ctx.fillRect(0,0,w,h);ctx.font='12px Segoe UI, sans-serif';ctx.lineWidth=1;
      for(let i=0;i<=5;i++) {
        const rate=maximum*i/5, py=y(rate);ctx.strokeStyle='#e5ecf3';ctx.beginPath();ctx.moveTo(area.x,py);ctx.lineTo(area.x+area.w,py);ctx.stroke();
        ctx.fillStyle='#5d7186';ctx.textAlign='right';ctx.fillText(number(rate),area.x-9,py+4);
      }
      ctx.textAlign='center';
      for(let i=0;i<=6;i++) { const t=view.left+width*i/6;ctx.fillStyle='#5d7186';ctx.fillText(number(t/unit.factor),x(t),area.y+area.h+22); }
      ctx.fillStyle='#182a3c';ctx.fillText(`經過時間（${unit.label}）`,area.x+area.w/2,h-7);
      ctx.save();ctx.translate(15,area.y+area.h/2);ctx.rotate(-Math.PI/2);ctx.fillText('速率（Mbps）',0,0);ctx.restore();
      ctx.save();ctx.beginPath();ctx.rect(area.x,area.y,area.w,area.h);ctx.clip();
      ctx.fillStyle='#94a3b833';ctx.fillRect(x(0),area.y,x(cfg.warmup)-x(0),area.h);
      if(!overview) for(const p of points) if(p.row[3]==='LOW') {ctx.fillStyle='#ef44441a';ctx.fillRect(x(p.row[0]),area.y,x(p.row[1])-x(p.row[0]),area.h);}
      ctx.strokeStyle='#c6373e';ctx.setLineDash([6,4]);ctx.beginPath();ctx.moveTo(area.x,y(cfg.threshold));ctx.lineTo(area.x+area.w,y(cfg.threshold));ctx.stroke();ctx.setLineDash([]);
      ctx.strokeStyle='#2466d6';ctx.lineWidth=1.7;ctx.beginPath();
      let previous=null;
      for(let i=0;i<points.length;i++) {
        const p=points[i], px=x((p.row[0]+p.row[1])/2),py=y(p.row[2]);
        if(!previous || p.group!==previous.group) {ctx.moveTo(x(p.row[0]),py);ctx.lineTo(px,py);}
        else {const oldx=x((previous.row[0]+previous.row[1])/2),oldy=y(previous.row[2]),dx=px-oldx;ctx.bezierCurveTo(oldx+dx/3,oldy,px-dx/3,py,px,py);}
        if(i===points.length-1 || points[i+1].group!==p.group) ctx.lineTo(x(p.row[1]),py);
        previous=p;
      }
      ctx.stroke();
      for(const p of points) {ctx.fillStyle=p.row[3]==='LOW'?'#c6373e':'#2466d6';ctx.beginPath();ctx.arc(x((p.row[0]+p.row[1])/2),y(p.row[2]),p.row[3]==='LOW'?3:1.5,0,Math.PI*2);ctx.fill();}
      ctx.restore();
      if(!rows.length) {ctx.textAlign='center';ctx.fillStyle='#687e91';ctx.fillText('沒有有效取樣；請查看測試結果與錯誤訊息。',w/2,h/2);}
      $('range').textContent=`${elapsed(view.left)} – ${elapsed(view.right)}`;
      $('sampling').textContent=overview?'總覽保留最高／最低與低速點；放大可看逐筆資料':'顯示區間內的原始取樣';
      canvas.dataset.left=String(view.left);canvas.dataset.right=String(view.right);canvas.dataset.unit=unit.label;canvas.dataset.points=String(points.length);
      const tw=timeline.clientWidth;
      $('track').style.width=Math.max(tw,Math.min(1e7,tw*view.total/width))+'px';
      desiredScroll=(view.total>width?view.left/(view.total-width):0)*(timeline.scrollWidth-tw);
      if(Math.abs(timeline.scrollLeft-desiredScroll)>.5) timeline.scrollLeft=desiredScroll;
    }
    function stationLabel(record) { return record?({OK:'已擷取',RUNNING:'查詢中',ERROR:'查詢錯誤',NO_PEERS:'無 peer',CANCELLED:'已取消',SKIPPED_BUSY:'略過：忙碌'}[record.status]||record.status):(cfg.ssh_enabled?'無 SSH 紀錄':'未啟用'); }
    function showEvent(index) {
      selected=index; const event=events[index],record=data.station[String(index)];
      view.focus(event.start,event.end);schedule();
      // Preserve keyboard focus and the table's scroll position when selecting a row.
      for(const row of $('events').children) row.setAttribute('aria-selected',String(Number(row.dataset.event)===index));
      $('detail-title').textContent=`事件 ${index+1} · Station 與日期時間`;
      const text=[`Fail 偵測日期時間（本機）: ${date(event.detected_at)}`,`區間: ${event.start}–${event.end} 秒；最低 ${number(event.min_mbps)} Mbps`,`SSH: ${stationLabel(record)}`];
      if(record) {
        for(const [key,label] of [['triggered_at','SSH 觸發時間'],['started_at','SSH 查詢開始'],['finished_at','SSH 查詢結束']]) if(record[key]) text.push(`${label}: ${date(record[key])}`);
        if(record.error) text.push('錯誤: '+record.error);
        for(const peer of record.peers||[]) {
          text.push('',`Station ${peer.mac} (on ${peer.vap||record.vap||'未提供'})`);
          if(peer.error) text.push('錯誤: '+peer.error);
          for(const [key,label] of [['inactive_time','inactive time'],['signal','signal'],['signal_avg','signal avg'],['tx_bitrate','tx bitrate'],['rx_bitrate','rx bitrate']]) text.push(`${label}: ${peer[key]||'未提供'}`);
        }
      }
      $('detail').textContent=text.join('\n'); $('raw').textContent=record?JSON.stringify(record,null,2):'此事件沒有 SSH 紀錄。';
    }
    function renderEvents() {
      $('events').replaceChildren(); const count=Math.max(1,Math.ceil(events.length/pageSize));page=clamp(page,0,count-1);
      for(let i=page*pageSize;i<Math.min(events.length,(page+1)*pageSize);i++) {
        const e=events[i],tr=document.createElement('tr'); tr.dataset.event=String(i);tr.tabIndex=0;tr.setAttribute('aria-selected',String(selected===i));
        for(const value of [i+1,date(e.detected_at),number(e.start),number(e.end),number(e.seconds),number(e.min_mbps),stationLabel(data.station[String(i)])]) {const td=document.createElement('td');td.textContent=value;tr.append(td);}
        tr.addEventListener('click',()=>showEvent(i));tr.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();showEvent(i);}});$('events').append(tr);
      }
      $('page').textContent=`${page+1} / ${count} 頁 · 共 ${events.length} 次`;$('previous').disabled=page===0;$('next').disabled=page===count-1;$('empty-events').hidden=events.length>0;
    }
    $('previous').onclick=()=>{page--;renderEvents();};$('next').onclick=()=>{page++;renderEvents();};
    $('unit').onchange=schedule;$('zoom-in').onclick=()=>{view.zoom(.5);schedule();};$('zoom-out').onclick=()=>{view.zoom(2);schedule();};
    $('all').onclick=()=>{view.all();schedule();};$('latest').onclick=()=>{const width=view.right-view.left===view.total?Math.min(60,view.total):view.right-view.left;view.window(view.total-width,width);schedule();};
    function point(event) {const r=canvas.getBoundingClientRect();return {x:event.clientX-r.left,y:event.clientY-r.top};}
    function inPlot(p) {const a=geometry.area;return p.x>=a.x&&p.x<=a.x+a.w&&p.y>=a.y&&p.y<=a.y+a.h;}
    canvas.addEventListener('wheel',event=>{const p=point(event);if(!geometry||!inPlot(p))return;event.preventDefault();const a=geometry.area,anchor=view.left+(p.x-a.x)/a.w*(view.right-view.left);view.zoom(Math.pow(.8,clamp(-event.deltaY/100,-10,10)),anchor);schedule();},{passive:false});
    canvas.addEventListener('pointerdown',event=>{const p=point(event);if(event.button!==0||!geometry||!inPlot(p))return;drag={x:p.x,left:view.left,width:view.right-view.left};canvas.setPointerCapture(event.pointerId);canvas.style.cursor='grabbing';$('tooltip').hidden=true;});
    canvas.addEventListener('pointermove',event=>{
      if(!geometry)return;const p=point(event),a=geometry.area;
      if(drag){view.window(drag.left+(drag.x-p.x)/a.w*drag.width,drag.width);schedule();return;}
      const sample=inPlot(p)?nearestSample(rows,view.left+(p.x-a.x)/a.w*(view.right-view.left)):null;
      $('tooltip').hidden=!sample;if(sample){$('tooltip').textContent=`${sample[0]}–${sample[1]} 秒 · ${number(sample[2])} Mbps · ${sample[3]}\n${date(sample[4])}`;$('tooltip').style.left=clamp(p.x+12,0,Math.max(0,geometry.w-330))+'px';$('tooltip').style.top=clamp(p.y+12,0,geometry.h-64)+'px';}
    });
    function endDrag(){drag=null;canvas.style.cursor='crosshair';}canvas.addEventListener('pointerup',endDrag);canvas.addEventListener('pointercancel',endDrag);canvas.addEventListener('lostpointercapture',endDrag);canvas.addEventListener('pointerleave',()=>{$('tooltip').hidden=true;});
    timeline.addEventListener('scroll',()=>{if(Math.abs(timeline.scrollLeft-desiredScroll)<1)return;const max=timeline.scrollWidth-timeline.clientWidth;if(max>0){const width=view.right-view.left;view.window(timeline.scrollLeft/max*(view.total-width),width);schedule();}});
    timeline.addEventListener('keydown',e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();view.pan((view.right-view.left)*.1*(e.key==='ArrowLeft'?-1:1));schedule();}});
    new ResizeObserver(schedule).observe(canvas);renderEvents();draw();
  } catch(error) { fail(error); }
})();
