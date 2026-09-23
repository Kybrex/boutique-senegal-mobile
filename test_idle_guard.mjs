import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const source=await fs.readFile(new URL('./idle_guard.js',import.meta.url),'utf8');
const {default:render}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
let now=100000;
Date.now=()=>now;
let nextTimer=0;
const timers=new Map(), listeners=new Map(), overlays=[];
globalThis.setInterval=fn=>{timers.set(++nextTimer,fn);return nextTimer};
globalThis.clearInterval=id=>timers.delete(id);
globalThis.document={
  createElement:()=>({style:{},setAttribute(){},append(){},remove(){this.removed=true}}),
  body:{append:el=>overlays.push(el)},
  addEventListener:(name,fn)=>listeners.set(name,fn),
  removeEventListener:(name,fn)=>{if(listeners.get(name)===fn)listeners.delete(name)}
};
let signals=[];
const data={nonce:'one',remaining_ms:60000,timeout_ms:60000};
let cleanup=render({data,setTriggerValue:(...v)=>signals.push(v)});
const event=name=>listeners.get(name)({isTrusted:true});
const tick=()=>[...timers.values()].forEach(fn=>fn());
now+=10000;event('keydown');
assert.equal(signals.filter(x=>x[0]==='activity').length,1);
cleanup();
cleanup=render({data:{...data,remaining_ms:60000},setTriggerValue:(...v)=>signals.push(v)});
now+=1000;event('input');
assert.equal(signals.filter(x=>x[0]==='activity').length,1,'rerender must not reset throttling');
now+=9000;tick();
assert.equal(signals.filter(x=>x[0]==='activity').length,2,'trailing activity reaches server');
now=171001;tick();
assert.equal(signals.filter(x=>x[0]==='locked').length,1);
assert.equal(overlays.length,1);
event('pointerdown');
assert.equal(signals.filter(x=>x[0]==='activity').length,2,'late click cannot unlock');
cleanup();
assert.equal(listeners.size,0);
assert.equal(timers.size,0);
assert.equal(overlays[0].removed,true);
cleanup=render({data:{...data,nonce:'two'},setTriggerValue:(...v)=>signals.push(v)});
event('keydown');
assert.equal(signals.filter(x=>x[0]==='activity').length,3,'new authenticated session works');
cleanup();
console.log('PASS: idle browser deadline, trusted input throttle, rerender cleanup, late activity rejection and fresh login');
