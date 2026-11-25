const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const test = require('node:test');
const path = require('node:path');

const appFile = process.env.APP_UNDER_TEST || path.join(__dirname, '../app.js');
const source = fs.readFileSync(appFile, 'utf8');
const keys = ['permits', 'deeds', 'easements', 'fdep', 'faa'];
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

// Exercise the actual application renderers. The stub supplies only their DOM sinks and
// already-returned source results; it makes no requests and contains no real records.
function renderer(name) {
  const start = source.indexOf('  function ' + name + '(');
  assert.ok(start >= 0, 'application renderer exists');
  const tail = source.slice(start);
  const next = /\n  (?:async )?function /.exec(tail);
  assert.ok(next, 'next top-level function bounds extraction');
  return tail.slice(0, next.index);
}

function render({failed = [], records = [], active = keys, capped = [], estimates = {}} = {}) {
  const controls = {innerHTML:''};
  const readout = {innerHTML:''};
  const empty = {hidden:true,textContent:'No Signals match these filters. Widen the window or re-enable a source.'};
  const mapCount = {textContent:''};
  const counts = Object.fromEntries(keys.map(k => [k, {
    loaded: records.filter(r => r.source === k).length,
    filteredTotal: estimates[k] ?? 0,
    failed: failed.includes(k),
    hasMore: capped.includes(k)
  }]));
  const state = {
    all:records, counts, totals:{all:1234}, errors:failed.map(source => ({source,message:'source request failed'})),
    filters:{sources:Object.fromEntries(keys.map(k => [k,active.includes(k)])),status:'all',days:30,minAmount:0,municipality:''},
    search:{query:'',ran:false}, service:{PAGE_CAP:600}
  };
  const context = {
    window:{FloridaSignalV1:{SOURCE_FAMILIES:[
      {key:'development',label:'Development',status:'live'},
      {key:'property-money',label:'Property',status:'live'},
      {key:'environment',label:'Environment',status:'live'},
      {key:'skyline',label:'Skyline',status:'live'}
    ],LAYER_LABEL:{},LAYER_COLOR:{}}},
    signalState:state, SIGNAL_SOURCE_KEYS:keys, SITUS_CITY_NOTE:'Synthetic city note',
    state:{map:{removeLayer(){}}},
    L:{layerGroup:() => ({addLayer(){},addTo(){}}),circleMarker:() => ({bindPopup(){}})},
    signalCardHtml:() => '',signalPopupOptions:() => ({}),
    el: selector => selector === '[data-signal-controls]' ? controls : selector === '#signal-count-readout' ? readout :
      selector === '#signal-empty-state' ? empty : selector === '#signal-layer-count' ? mapCount : null,
    els: () => [], escapeHtml, formatNumber:n => Number(n).toLocaleString('en-US'),
    uniqueTags:a => [...new Set(a)].filter(Boolean), signalSourceKey:s => s.source,
    visibleSignals:() => records.filter(s => s.public_eligibility && active.includes(s.source))
  };
  vm.createContext(context);
  vm.runInContext(renderer('renderSignalControls') + '\nrenderSignalControls();\n' +
    renderer('renderSignalCounts') + '\nrenderSignalCounts();\n' +
    renderer('drawSignalLayer') + '\ndrawSignalLayer();', context);
  return {controls:controls.innerHTML,readout:readout.innerHTML,empty,mapCount:mapCount.textContent};
}

test('a failed source is unavailable, even when its independent count query returned a number', () => {
  const html = render({failed:['permits'],estimates:{permits:27}});
  assert.match(html.controls,/Permits, demolition &amp; storm work \(unavailable\)/);
  assert.doesNotMatch(html.controls,/Permits, demolition &amp; storm work \(0\)/);
  assert.match(html.controls,/Temporarily unavailable: permits/);
  assert.match(html.readout,/27 match these filters countywide \(planner estimate\)/);
  assert.match(html.readout,/their rows are not shown/);
  assert.doesNotMatch(html.readout,/their records are not counted/);
});

test('all failed active sources show unavailable rather than a zero-record result', () => {
  const html = render({failed:keys});
  assert.match(html.readout,/<strong>Signals unavailable<\/strong>/);
  assert.doesNotMatch(html.readout,/<strong>0<\/strong> Signals shown/);
  for (const key of keys) assert.ok(html.controls.includes('data-signal-source="'+key+'"'));
});

test('partial failure preserves successful records and identifies the unavailable contribution', () => {
  const html = render({failed:['permits'],records:[{source:'faa',public_eligibility:true}],active:['permits','faa']});
  assert.match(html.readout,/<strong>1<\/strong> Signals shown from available sources/);
  assert.match(html.readout,/Unavailable sources: permits/);
  assert.match(html.controls,/FAA cases &amp; cranes \(1\)/);
});

test('a successful empty source remains a genuine zero and disabled failures do not taint active counts', () => {
  const empty = render({active:['permits']});
  assert.match(empty.controls,/Permits, demolition &amp; storm work \(0\)/);
  assert.match(empty.readout,/<strong>0<\/strong> Signals shown/);
  assert.doesNotMatch(empty.readout,/unavailable/i);
  const disabled = render({failed:['permits'],active:['faa']});
  assert.match(disabled.readout,/<strong>0<\/strong> Signals shown/);
  assert.doesNotMatch(disabled.readout,/Unavailable sources/);
});

test('capped results retain the cap disclosure without promising complete coverage after zoom', () => {
  const html = render({capped:['faa'],active:['faa']});
  assert.match(html.readout,/per-request cap of 600/);
  assert.match(html.readout,/results can still be capped/);
  assert.match(html.readout,/Results may be limited/);
  assert.doesNotMatch(html.readout,/More records exist/);
  assert.doesNotMatch(html.readout,/complete coverage/);
});

test('an empty map with a failed enabled source does not claim a complete no-match result', () => {
  const result = render({failed:['permits'],active:['permits','faa']});
  assert.equal(result.empty.hidden,false);
  assert.match(result.empty.textContent,/enabled sources are unavailable/);
  assert.doesNotMatch(result.empty.textContent,/match these filters/);
  const healthy = render({failed:['permits'],active:['faa']});
  assert.match(healthy.empty.textContent,/No Signals match these filters/);
});

if (process.env.SAVE_RENDER_FIXTURES) {
  const cases = {
    'partial-source-error':render({failed:['permits'],records:[{source:'faa',public_eligibility:true}],active:['permits','faa'],capped:['faa']}),
    'all-sources-error':render({failed:keys}),
    'successful-empty':render({active:['permits']})
  };
  fs.mkdirSync(process.env.SAVE_RENDER_FIXTURES,{recursive:true});
  for (const [name,html] of Object.entries(cases)) fs.writeFileSync(path.join(process.env.SAVE_RENDER_FIXTURES,name+'.json'),JSON.stringify(html,null,2)+'\n');
}
