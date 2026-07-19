-- Florida Signal — Acclaim preliminary harvester (drives the operator's real, Cloudflare-cleared Chrome).
-- Usage: osascript acclaim_harvest.applescript "M/D/YYYY" "/tmp/acclaim_out.ndjson" [maxPages]
-- Writes one JSON object per line (NDJSON) to the output file. No Claude, no node, no Playwright.
-- Depends only on Chrome + "Allow JavaScript from Apple Events" (verified enabled 2026-07-19).

on run argv
	set targetDate to item 1 of argv
	set outFile to item 2 of argv
	if (count of argv) > 2 then
		set maxPages to (item 3 of argv) as integer
	else
		set maxPages to 60
	end if

	set searchURL to "https://officialrecords.broward.org/AcclaimWeb/search/SearchTypeRecordDate"

	tell application "Google Chrome"
		set w to make new window
		set t to active tab of w
		set URL of t to searchURL
	end tell

	-- Wait for Cloudflare clearance + the real search form (up to ~40s).
	set ready to false
	repeat 20 times
		delay 2
		tell application "Google Chrome"
			set probe to execute t javascript "(function(){return document.getElementById('RecordDate')?'READY':(/Attention Required|Just a moment/i.test(document.title)?'CF':'WAIT');})()"
		end tell
		if probe is "READY" then
			set ready to true
			exit repeat
		end if
	end repeat
	if not ready then
		tell application "Google Chrome" to close w
		error "NOT_READY:" & probe
	end if

	-- Run the search for the target record date.
	tell application "Google Chrome"
		execute t javascript "(function(){var d=document.getElementById('RecordDate'); d.value='" & targetDate & "'; d.dispatchEvent(new Event('change',{bubbles:true})); document.getElementById('btnSearch').click(); return 'searched';})()"
	end tell

	-- Wait for the results grid to populate (Telerik AJAX). Up to ~28s.
	repeat 14 times
		delay 2
		tell application "Google Chrome"
			set gridReady to execute t javascript "(function(){var r=document.querySelectorAll('#SearchGridContainer tbody tr, .t-grid-content tbody tr');for(var i=0;i<r.length;i++){if(/\\b\\d{7,}\\b/.test(r[i].innerText))return 'GRID';}var s=(document.querySelector('.t-status-text')||{}).innerText||'';return /of\\s*0\\b/.test(s)?'EMPTY':'WAIT';})()"
		end tell
		if gridReady is "GRID" or gridReady is "EMPTY" then exit repeat
	end repeat
	if gridReady is "EMPTY" then
		tell application "Google Chrome" to close w
		return "EMPTY"
	end if
	-- Let the full page render (Telerik paints ~100 rows after first paint).
	delay 3

	-- Harvest per page. Column order from the results header (.t-grid th lists result columns
	-- before the calendar widget); rows from the Telerik content table.
	set harvestJS to "(function(){var ths=[].slice.call(document.querySelectorAll('.t-grid th')).map(function(x){return x.innerText.trim().toLowerCase();});function ci(n){return ths.indexOf(n);}var di=ci('record date'),ty=ci('doc type'),fn=ci('first direct name'),inm=ci('first indirect name'),bt=ci('book type'),bp=ci('book/page'),lg=ci('legal'),ins=ci('instrument #');var rows=[].slice.call(document.querySelectorAll('#SearchGridContainer tbody tr, .t-grid-content tbody tr'));if(!rows.length)rows=[].slice.call(document.querySelectorAll('#SearchGridContainer tr'));var out=[];rows.forEach(function(r){var c=r.querySelectorAll('td');if(c.length<6)return;function g(i){return i>-1&&c[i]?c[i].innerText.trim():'';}var inst=g(ins).replace(/\\D/g,'');if(!inst)return;var rd=g(di).replace(/(\\d{2})\\/(\\d{2})\\/(\\d{4})/,'$3-$1-$2');out.push({record_date:rd,instrument_number:inst,doc_type:g(ty),first_direct_name:g(fn),first_indirect_name:g(inm),book_type:g(bt),book_page:g(bp),legal_snippet:g(lg).slice(0,500)});});var pager=(document.querySelector('.t-status-text, .t-pager-info')||{}).innerText||'';return JSON.stringify({rows:out,pager:pager});})()"

	set allLines to ""
	set lastTotal to 0
	set gotSoFar to 0
	repeat with pageNum from 1 to maxPages
		tell application "Google Chrome"
			set pageJSON to execute t javascript harvestJS
		end tell
		-- Append rows via python (robust JSON handling) — write this page to a shard file.
		set shard to outFile & ".page"
		do shell script "/usr/bin/python3 - " & quoted form of pageJSON & " " & quoted form of outFile & " <<'PY'
import sys, json
data = json.loads(sys.argv[1]); rows = data.get('rows', [])
with open(sys.argv[2], 'a') as f:
    for r in rows:
        f.write(json.dumps(r) + '\\n')
print(len(rows))
PY"
		-- Advance pager if more remain.
		tell application "Google Chrome"
			set moreLeft to execute t javascript "(function(){var m=(document.querySelector('.t-status-text, .t-pager-info')||{}).innerText||'';var mm=m.match(/(\\d[\\d,]*)\\s*-\\s*(\\d[\\d,]*)\\s*of\\s*(\\d[\\d,]*)/);if(!mm)return 'DONE';var y=parseInt(mm[2].replace(/,/g,'')),tot=parseInt(mm[3].replace(/,/g,''));if(y>=tot)return 'DONE';var nx=document.querySelector('.t-arrow-next:not(.t-state-disabled), a.t-link .t-arrow-next');var anchor=document.querySelector('.t-arrow-next');if(anchor){var a=anchor.closest('a')||anchor;a.click();return 'NEXT';}return 'DONE';})()"
		end tell
		if moreLeft is "DONE" then exit repeat
		delay 3
	end repeat

	tell application "Google Chrome" to close w
	return "OK"
end run
