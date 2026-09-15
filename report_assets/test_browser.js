async (page) => {
  // Run with playwright-cli after opening validation/html-report/report.html.
  const check=(value,message)=>{if(!value)throw new Error(message);};
  const errors=[],requests=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>requests.push(r.url()));
  await page.context().setOffline(true);
  const chart=page.locator('#chart');
  const state=()=>chart.evaluate(el=>({left:+el.dataset.left,right:+el.dataset.right,unit:el.dataset.unit}));
  for(const [value,label] of [['seconds','秒'],['minutes','分'],['hours','時'],['days','天'],['auto','天']]) {
    await page.getByRole('combobox').selectOption(value);
    await page.waitForFunction(label=>document.querySelector('#chart').dataset.unit===label,label);
  }
  check(await page.locator('#event-count').textContent()==='173','Missing fail events');
  check(await page.evaluate(()=>JSON.parse(document.querySelector('#report-data').textContent).samples.length)===345600,'Raw samples were reduced in the saved report');
  check(await page.evaluate(()=>globalThis.injected)===undefined,'Remote text ran as JavaScript');
  await page.locator('[data-event="0"]').click();
  await page.locator('[data-event="0"]').focus();await page.keyboard.press('Enter');
  check(await page.evaluate(()=>document.activeElement.dataset.event)==='0','Event selection lost keyboard focus');
  await page.waitForFunction(()=>+document.querySelector('#chart').dataset.left===16);
  check((await state()).right===27,'Event padding differs from desktop');
  check((await page.locator('#detail').textContent()).includes('HE-MCS 10 HE-NSS 2'),'Station PHY details missing');
  check((await page.locator('#detail').textContent()).includes('2026-09-15 10:00:22+08:00'),'Fail date missing');
  await chart.scrollIntoViewIfNeeded();let box=await chart.boundingBox();
  await page.mouse.move(box.x+box.width*.5,box.y+box.height*.5);
  await page.mouse.wheel(0,-100);
  await page.waitForFunction(()=>{const c=document.querySelector('#chart');return +c.dataset.right-Number(c.dataset.left)<10;});
  const before=await state();
  await page.mouse.down();await page.mouse.move(box.x+box.width*.5+50,box.y+box.height*.5,{steps:5});await page.mouse.up();
  await page.waitForFunction(left=>+document.querySelector('#chart').dataset.left<left,before.left);
  await page.locator('#timeline').evaluate(el=>{el.scrollLeft=(el.scrollWidth-el.clientWidth)/2;});
  await page.waitForFunction(()=>+document.querySelector('#chart').dataset.left>100000);
  await page.getByRole('button',{name:'下一頁'}).click();
  await page.locator('[data-event="100"]').click();
  await page.waitForFunction(()=>+document.querySelector('#chart').dataset.left===200016);
  await page.getByRole('button',{name:'顯示全部'}).click();
  await page.waitForFunction(()=>+document.querySelector('#chart').dataset.right===345600);
  check((await state()).left===0,'Show all failed');
  await page.getByRole('button',{name:'查看最後一段'}).click();
  await page.waitForFunction(()=>+document.querySelector('#chart').dataset.left===345540);
  await page.getByRole('button',{name:'上一頁'}).click();
  await page.locator('[data-event="0"]').click();
  await page.waitForFunction(()=>+document.querySelector('#chart').dataset.left===16);
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:'output/playwright/html-report.png',fullPage:true});
  check(errors.length===0,errors.join('; '));check(requests.length===0,'Report made network requests: '+requests.join(', '));
  return {passed:true,samples:345600,events:173,offline:true,wheel:true,drag:true,scrollbar:true,eventFocus:true,station:true};
}
