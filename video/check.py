import asyncio, json
from playwright.async_api import async_playwright

S = json.load(open('build/scenes.json'))
JS = """(sid)=>{
  const sc=document.getElementById(sid); const out=[];
  const vis=e=>getComputedStyle(e).visibility!=='hidden'&&parseFloat(getComputedStyle(e).opacity)>0.5;
  const R=e=>e.getBoundingClientRect();
  for(const e of sc.querySelectorAll('.bub,.step,.node,.card,.chip')){
    if(!vis(e)) continue;
    if(e.scrollWidth>e.clientWidth+2||e.scrollHeight>e.clientHeight+2) out.push('overflow '+e.className+' | '+(e.textContent||'').trim().slice(0,40));
  }
  const els=[...sc.querySelectorAll('.card,.node,.step,.phone,.chip,.serif,.lab,svg.abs')].filter(vis);
  const tops=els.filter(e=>!els.some(o=>o!==e&&o.contains(e)));
  const name=e=>((e.textContent||'').trim().replace(/\\s+/g,' ').slice(0,28)||e.getAttribute('class')||e.tagName);
  for(let i=0;i<tops.length;i++)for(let j=i+1;j<tops.length;j++){
    const a=R(tops[i]),b=R(tops[j]);
    const ix=Math.min(a.right,b.right)-Math.max(a.left,b.left), iy=Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top);
    if(ix>8&&iy>8) out.push('overlap ['+name(tops[i])+'] x ['+name(tops[j])+']');
  }
  for(const e of tops){const a=R(e); if(a.left<60||a.right>1860||a.top<96||a.bottom>935) out.push('margin ['+name(e)+'] '+[a.left|0,a.top|0,a.right|0,a.bottom|0]);}
  return out;}"""

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={'width': 1920, 'height': 1080})
        errs = []
        pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        pg.on('pageerror', lambda e: errs.append(str(e)))
        await pg.goto('http://127.0.0.1:8765/page.html')
        await pg.wait_for_function('window.READY===true')
        for s in S['scenes']:
            for lab, t in (('mid', s['dur'] * 0.5), ('end', s['dur'] - 0.5)):
                await pg.evaluate(f"seek({s['start'] + t})")
                await pg.screenshot(path=f"build/still_{s['id']}_{lab}.png")
            await pg.evaluate(f"seek({s['start'] + s['dur'] - 0.5})")
            res = await pg.evaluate(JS, s['id'])
            print(s['id'], res if res else 'ok')
        print('console errors:', errs)
        await b.close()

asyncio.run(main())
