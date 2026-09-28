const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const modulePath = path.join(__dirname,'../ops/mac/acclaim_browser.js');
function fixture({fresh=true, rowDate='09/28/2026', empty=false, terms=false, challenge=false,inputDate='9/28/2026',mixed=false,staleStatus=false,placeholder=false}={}) {
  const node=(text,stale=false)=>({innerText:text,children:[],offsetParent:{},getAttribute:k=>k==='data-fs-previous-result'&&stale?'1':null,setAttribute(k,v){if(k==='data-fs-previous-result')stale=v==='1';},removeAttribute(k){if(k==='data-fs-previous-result')stale=false;}});
  const cells=[node(rowDate),node('121000001')];const row=node(rowDate+' 121000001',!fresh);row.querySelectorAll=()=>cells;
  const status=node(empty?'Displaying items 0 - 0 of 0':'Displaying items 1 - 1 of 1',!fresh||staleStatus);
  const staleRow=node('09/27/2026 121000000',true);staleRow.querySelectorAll=()=>[node('09/27/2026'),node('121000000')];
  const leaf=node(empty?'No Results to Display':'',!fresh);
  const emptyRow=node('No Results to Display',!fresh);emptyRow.querySelectorAll=()=>[leaf];
  const input={value:inputDate,dispatchEvent(){}};let clicks=0;const button={click(){clicks++;}};
  return {clicks:()=>clicks,title:challenge?'Just a moment':'Broward',readyState:'complete',getElementById:id=>id==='RecordDate'?input:id==='btnSearch'?button:null,querySelector:()=>status,querySelectorAll:s=>s==='.t-grid th'?[node('Record Date'),node('Instrument #')]:s==='#SearchGridContainer tbody tr'?(empty?(placeholder?[emptyRow]:[]):mixed?[staleRow,row]:[row]):s==='body *'?[leaf]:s==='#SearchGridContainer tbody tr, .t-status-text'?[row,status]:[],location:{origin:'https://officialrecords.broward.org',pathname:terms?'/AcclaimWeb/Disclaimer':'/AcclaimWeb/search/SearchTypeRecordDate'}};
}
function result(options) {
 const document=fixture(options), context={document,location:document.location};vm.createContext(context);
 if(fs.existsSync(modulePath)) {vm.runInContext(fs.readFileSync(modulePath,'utf8'),context);return vm.runInContext("FSClerkBrowser.result('9/28/2026')",context);}
 const source=fs.readFileSync(path.join(__dirname,'../ops/mac/acclaim_harvest.applescript'),'utf8');
 const match=source.match(/set gridState to execute t javascript "([\s\S]*?)"\n/);
 return vm.runInContext(match[1].replace(/\\\\/g,'\\').replace(/\\"/g,'"'),context);
}
assert.equal(result({fresh:false}),'WAIT','Previous grid must not satisfy a new search');
assert.equal(result({mixed:true}),'WAIT','Mixed stale/new rows cannot pass export gate');
assert.equal(result({staleStatus:true}),'WAIT','Old count cannot complete a new result');
assert.equal(result({fresh:false,empty:true}),'WAIT','Previous empty status must not satisfy a new search');
assert.equal(result({rowDate:'09/27/2026'}),'DATE_MISMATCH','Different record date must not be harvested');
assert.equal(result({terms:true}),'TERMS','Terms outrank cached rows and form');
assert.equal(result({challenge:true}),'CF');
assert.equal(result({inputDate:'9/27/2026'}),'INPUT_DATE_CHANGED');
assert.equal(result({}),'GRID');
assert.equal(result({empty:true}),'EMPTY');
assert.equal(result({empty:true,placeholder:true}),'EMPTY','Exact fresh Telerik empty row is valid empty');
assert.equal(result({fresh:false,empty:true,placeholder:true}),'WAIT','Stale empty row cannot complete search');
const document=fixture(), c={document,location:document.location,Event:function(){}};vm.createContext(c);vm.runInContext(fs.readFileSync(modulePath,'utf8'),c);
assert.equal(vm.runInContext("FSClerkBrowser.begin('9/28/2026')",c),'SEARCHED');
assert.equal(document.clicks(),1);
assert.equal(vm.runInContext("FSClerkBrowser.result('9/28/2026')",c),'WAIT','Begin marks old same-date results stale');
assert.equal(vm.runInContext("FSClerkBrowser.begin('invalid')",c),'INVALID_DATE');
assert.equal(document.clicks(),1,'Invalid date never submits');
assert.equal(JSON.parse(vm.runInContext("FSClerkBrowser.page('9/28/2026',1,1)",c)).rows.length,0,'Atomic export rejects old result');
for (const options of [{mixed:true},{staleStatus:true},{rowDate:'09/27/2026'},{terms:true}]) {
 const d=fixture(options),ct={document:d,location:d.location};vm.createContext(ct);vm.runInContext(fs.readFileSync(modulePath,'utf8'),ct);
 assert.equal(JSON.parse(vm.runInContext("FSClerkBrowser.page('9/28/2026',1,1)",ct)).rows.length,0);
}
const d=fixture(),ct={document:d,location:d.location};vm.createContext(ct);vm.runInContext(fs.readFileSync(modulePath,'utf8'),ct);
const exported=JSON.parse(vm.runInContext("FSClerkBrowser.page('9/28/2026',1,1)",ct));
assert.equal(exported.rows.length,1);assert.equal(exported.rows[0].record_date,'2026-09-28');
assert.equal(JSON.parse(vm.runInContext("FSClerkBrowser.page('9/28/2026',2,1)",ct)).error,'RANGE_CHANGED');
assert.equal(JSON.parse(vm.runInContext("FSClerkBrowser.page('9/28/2026',1,2)",ct)).error,'RANGE_CHANGED');

const persistent=fixture();let mutations, observed, disconnects=0;
const mc={document:persistent,location:persistent.location,Event:function(){},setTimeout(){},MutationObserver:function(fn){mutations=fn;this.observe=(node,opts)=>{observed=opts;};this.disconnect=()=>{disconnects++;};}};
vm.createContext(mc);vm.runInContext(fs.readFileSync(modulePath,'utf8'),mc);
vm.runInContext("FSClerkBrowser.begin('9/28/2026')",mc);
assert.equal(observed.attributes,undefined,'Attribute changes cannot prove a new response');
const originalRows=persistent.querySelectorAll;const freshRows=fixture().querySelectorAll('#SearchGridContainer tbody tr');
persistent.querySelectorAll=s=>s==='#SearchGridContainer tbody tr'?freshRows:originalRows(s);
assert.equal(vm.runInContext("FSClerkBrowser.result('9/28/2026')",mc),'WAIT');
mutations([{type:'attributes'}]);
assert.equal(vm.runInContext("FSClerkBrowser.result('9/28/2026')",mc),'WAIT');
mutations([{type:'characterData'}]);
assert.equal(vm.runInContext("FSClerkBrowser.result('9/28/2026')",mc),'GRID','Persistent status text update supports same-date rerun');
assert.equal(disconnects,1);
persistent.querySelectorAll=originalRows;
assert.equal(vm.runInContext("FSClerkBrowser.result('9/28/2026')",mc),'WAIT','Status mutation alone cannot freshen stale rows');
console.log('32 Acclaim browser freshness, source-gate, submission and atomic export assertions passed');
