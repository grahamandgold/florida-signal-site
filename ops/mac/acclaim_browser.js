/* Acclaim DOM checks: no requests, credentials, terms clicks or hidden app state. */
var FSClerkBrowser = (function () {
  function fresh(node) { return node && node.getAttribute('data-fs-previous-result') !== '1'; }
  function state() {
    if (location.origin !== 'https://officialrecords.broward.org') return 'WRONG_ORIGIN';
    if (/\/Disclaimer\/?$/i.test(location.pathname)) return 'TERMS';
    if (/Attention Required|Just a moment|Access denied/i.test(document.title)) return 'CF';
    if (!/^\/AcclaimWeb\/search\/SearchTypeRecordDate\/?$/i.test(location.pathname)) return 'WRONG_PATH';
    return document.getElementById('RecordDate') ? 'READY' : 'WAIT';
  }
  function begin(date) {
    var current = state();
    if (current !== 'READY') return current;
    if (!/^\d{1,2}\/\d{1,2}\/\d{4}$/.test(date)) return 'INVALID_DATE';
    var button = document.getElementById('btnSearch');
    if (!button) return 'MISSING_SEARCH';
    // A previous search can leave a grid/empty message visible while AJAX is pending.
    // Mark terminal nodes; require replacement rows and a real metadata DOM update.
    var old = document.querySelectorAll('#SearchGridContainer tbody tr, .t-status-text');
    for (var i=0; i<old.length; i++) old[i].setAttribute('data-fs-previous-result','1');
    var status=document.querySelector('.t-status-text');
    if(status && typeof MutationObserver!=='undefined') {
      if(status.__fsRefreshObserver) status.__fsRefreshObserver.disconnect();
      // Telerik may update this persistent element instead of replacing it.
      // Attribute changes cannot satisfy freshness; only text/child mutations do.
      var observer=new MutationObserver(function(changes){
        if(changes.some(function(c){return c.type==='childList'||c.type==='characterData';})) {
          status.removeAttribute('data-fs-previous-result'); observer.disconnect();
        }
      });
      status.__fsRefreshObserver=observer;
      observer.observe(status,{childList:true,characterData:true,subtree:true});
      setTimeout(function(){observer.disconnect();},45000);
    }
    var all = document.querySelectorAll('body *');
    for (var j=0; j<all.length; j++) {
      if (!all[j].children.length && /^no results to display$/i.test((all[j].innerText||'').trim()))
        all[j].setAttribute('data-fs-previous-result','1');
    }
    var input=document.getElementById('RecordDate');
    input.value=date; input.dispatchEvent(new Event('change',{bubbles:true}));
    button.click(); return 'SEARCHED';
  }
  function normalizedDate(value) {
    var m=String(value).trim().match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    return m ? Number(m[1])+'/'+Number(m[2])+'/'+m[3] : null;
  }
  function result(date) {
    var current=state(); if (current!=='READY') return current;
    if(normalizedDate(document.getElementById('RecordDate').value)!==normalizedDate(date)) return 'INPUT_DATE_CHANGED';
    var headers=Array.prototype.map.call(document.querySelectorAll('.t-grid th'),function(x){return x.innerText.trim().toLowerCase();});
    var di=headers.indexOf('record date'), ii=headers.indexOf('instrument #');
    var rows=document.querySelectorAll('#SearchGridContainer tbody tr'), count=0;
    for(var i=0;i<rows.length;i++) {
      if(!fresh(rows[i])) return 'WAIT';
      var cells=rows[i].querySelectorAll('td');
      if(!cells.length) continue;
      if(rows.length===1 && cells.length===1 && fresh(cells[0]) && cells[0].offsetParent!==null &&
         /^no results to display$/i.test((cells[0].innerText||'').trim())) return 'EMPTY';
      if(di<0 || ii<0 || !cells[di] || !cells[ii]) return 'MISSING_COLUMNS';
      if(!/^\d{7,}$/.test(cells[ii].innerText.trim())) return 'MALFORMED_ROW';
      if(normalizedDate(cells[di].innerText)!==normalizedDate(date)) return 'DATE_MISMATCH';
      count++;
    }
    var status=document.querySelector('.t-status-text');
    if(count) {
      if(!fresh(status)) return 'WAIT';
      var m=(status.innerText||'').match(/(\d[\d,]*)\s*-\s*(\d[\d,]*)\s*of\s*(\d[\d,]*)/);
      if(!m) return 'MISSING_TOTAL';
      var first=Number(m[1].replace(/,/g,'')),last=Number(m[2].replace(/,/g,'')),total=Number(m[3].replace(/,/g,''));
      if(first<1 || last<first || total<last || last-first+1!==count) return 'COUNT_MISMATCH';
      return 'GRID';
    }
    if(fresh(status) && /of\s*0\b/.test(status.innerText||'')) return 'EMPTY';
    var all=document.querySelectorAll('body *');
    for(var j=0;j<all.length;j++) {
      var e=all[j]; if(!fresh(e) || e.children.length || e.offsetParent===null) continue;
      if(/^no results to display$/i.test((e.innerText||'').trim())) return 'EMPTY';
    }
    return 'WAIT';
  }
  function page(date, expectedFirst, expectedTotal) {
    var valid=result(date);
    if(valid!=='GRID') return JSON.stringify({rows:[],firstInst:'',error:valid});
    var m=document.querySelector('.t-status-text').innerText.match(/(\d[\d,]*)\s*-\s*(\d[\d,]*)\s*of\s*(\d[\d,]*)/);
    var first=Number(m[1].replace(/,/g,'')),total=Number(m[3].replace(/,/g,''));
    if(first!==expectedFirst || total!==expectedTotal) return JSON.stringify({rows:[],firstInst:'',error:'RANGE_CHANGED'});
    var headers=Array.prototype.map.call(document.querySelectorAll('.t-grid th'),function(x){return x.innerText.trim().toLowerCase();});
    var rows=document.querySelectorAll('#SearchGridContainer tbody tr'),out=[];
    for(var i=0;i<rows.length;i++) {
      var cells=rows[i].querySelectorAll('td'); if(!cells.length)continue;
      function get(name){var n=headers.indexOf(name);return n>=0&&cells[n]?cells[n].innerText.trim():'';}
      var d=normalizedDate(get('record date')).split('/');
      out.push({record_date:d[2]+'-'+('0'+d[0]).slice(-2)+'-'+('0'+d[1]).slice(-2),instrument_number:get('instrument #'),doc_type:get('doc type'),first_direct_name:get('first direct name'),first_indirect_name:get('first indirect name'),book_type:get('book type'),book_page:get('book/page'),legal_snippet:get('legal').slice(0,500)});
    }
    return JSON.stringify({rows:out,firstInst:out[0].instrument_number});
  }
  function diagnostic() {
    return JSON.stringify({state:state(),route:location.origin!=='https://officialrecords.broward.org'?'other_origin':/^\/AcclaimWeb\/search\/SearchTypeRecordDate\/?$/i.test(location.pathname)?'record_date':/^\/AcclaimWeb\/Disclaimer\/?$/i.test(location.pathname)?'terms':'other_path',ready_state:document.readyState,has_date_form:!!document.getElementById('RecordDate'),grid_rows:document.querySelectorAll('#SearchGridContainer tbody tr').length});
  }
  return {state:state,begin:begin,result:result,page:page,diagnostic:diagnostic};
}());
