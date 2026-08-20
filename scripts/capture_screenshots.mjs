import { chromium } from 'playwright';
const URL='https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app';
const OUT='docs/screenshots';
const b=await chromium.launch({channel:'chrome'});
const p=await b.newPage({viewport:{width:1600,height:1000},deviceScaleFactor:2,colorScheme:'dark'});
await p.goto(URL,{waitUntil:'networkidle'});
const shots=[
 ['01-gate-console',null],
 ['02-showroom-topology','POLE BARN SHOWROOM TOPOLOGY'],
 ['03-curator-challenge',"Curator's Negotiation"],
 ['04-memory-and-questions','ANSWERED FROM MEMORY'],
 ['05-the-sheet','BT-001',150],
 ['06-skip-reasoning','BT-003',80],
];
for(const [name,anchor,off=24] of shots){
  if(anchor){
    const y=await p.evaluate(([t,o])=>{
      const all=[...document.querySelectorAll('body *')];
      const hits=all.filter(e=>e.textContent&&e.textContent.toLowerCase().includes(t.toLowerCase()));
      if(!hits.length) return null;
      let el=hits[hits.length-1];
      let n=el; while(n&&n.getBoundingClientRect().width<400) n=n.parentElement;
      if(!n) n=el;
      return Math.max(0,n.getBoundingClientRect().top+window.scrollY-o);
    },[anchor,off]);
    if(y===null){console.log('MISS',name);continue;} console.log('  y=',y,name);
    await p.evaluate(v=>scrollTo(0,v),y);
    await p.waitForTimeout(400);
  }
  await p.screenshot({path:`${OUT}/${name}.png`});
  console.log('ok',name);
}
await b.close();
