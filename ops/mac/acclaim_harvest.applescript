-- Florida Signal — Acclaim preliminary harvester (drives the operator's real, Cloudflare-cleared Chrome).
-- Usage: osascript acclaim_harvest.applescript "M/D/YYYY" "/tmp/out.ndjson" [maxPages]
-- Writes NDJSON rows. Returns a structured status line:
--   OK|<pagesProcessed>|<totalRecords>      every page processed, count verified
--   EMPTY|0|0                                verified zero-result date
--   INCOMPLETE|<pages>|<total>|<reason>      cap hit / repeat / stall  (caller must NOT mark complete)
-- Sets the grid page size to 500 (max offered: 25/50/100/150/200/250/500) so a heavy
-- ~2,900-record day is 6 pages instead of 582 at the default page size of 5.
-- No Claude, no node, no Playwright. Requires Chrome + "Allow JavaScript from Apple Events".

on run argv
	set targetDate to item 1 of argv
	set outFile to item 2 of argv
	if (count of argv) > 2 then
		set maxPages to (item 3 of argv) as integer
	else
		set maxPages to 40
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
			set probe to execute t javascript "(function(){return document.getElementById('RecordDate')?'READY':(/\\/Disclaimer(?:\\?|$)/i.test(location.pathname)?'TERMS':(/Attention Required|Just a moment/i.test(document.title)?'CF':'WAIT'));})()"
		end tell
		if probe is "READY" or probe is "TERMS" then
			set ready to true
			exit repeat
		end if
	end repeat
	if probe is "TERMS" then
		-- Broward periodically expires the disclaimer acceptance cookie. This is an
		-- operator gate, not a collector crash; never click an acceptance control.
		tell application "Google Chrome" to close w
		return "SOURCE_WAIT|0|0|terms_acceptance_required"
	end if
	if not ready then
		tell application "Google Chrome" to close w
		return "INCOMPLETE|0|0|not_ready_" & probe
	end if

	-- Search the target record date.
	tell application "Google Chrome"
		execute t javascript "(function(){var d=document.getElementById('RecordDate'); d.value='" & targetDate & "'; d.dispatchEvent(new Event('change',{bubbles:true})); document.getElementById('btnSearch').click(); return 'searched';})()"
	end tell

	-- Wait for results, a POSITIVELY-detected empty result, or a distinguishable failure.
	-- States: GRID (rows present) · EMPTY (explicit no-results signature) · CF (Cloudflare)
	--         WAIT (still loading). Anything unresolved after the window is a timeout, never EMPTY.
	set gridState to "WAIT"
	repeat 14 times
		delay 2
		tell application "Google Chrome"
			set gridState to execute t javascript "(function(){
if(/Attention Required|Just a moment|Access denied/i.test(document.title))return 'CF';
var r=document.querySelectorAll('#SearchGridContainer tbody tr');
for(var i=0;i<r.length;i++){if(/\\b\\d{7,}\\b/.test(r[i].innerText))return 'GRID';}
var s=(document.querySelector('.t-status-text')||{}).innerText||'';
if(/of\\s*0\\b/.test(s))return 'EMPTY';
var all=document.querySelectorAll('body *');
for(var j=0;j<all.length;j++){var e=all[j];if(e.children.length)continue;
 var txt=(e.innerText||'').trim();
 if(/^no results to display$/i.test(txt)&&e.offsetParent!==null)return 'EMPTY';}
return 'WAIT';})()"
		end tell
		if gridState is "GRID" or gridState is "EMPTY" or gridState is "CF" then exit repeat
	end repeat
	if gridState is "EMPTY" then
		-- Verified zero-record date: Acclaim positively reported "No Results to Display".
		tell application "Google Chrome" to close w
		return "EMPTY|0|0"
	end if
	if gridState is "CF" then
		tell application "Google Chrome" to close w
		return "INCOMPLETE|0|0|cloudflare_block"
	end if
	if gridState is not "GRID" then
		-- No grid AND no positive empty-state message: treat as timeout/failure, never as empty.
		tell application "Google Chrome" to close w
		return "INCOMPLETE|0|0|timeout_no_result_state"
	end if
	delay 2

	-- Raise the page size to 500 (Telerik custom dropdown: open, then click the 500 item).
	tell application "Google Chrome"
		execute t javascript "(function(){var w=document.querySelector('.t-page-size .t-dropdown-wrap'); if(w){w.click(); return 'opened';} return 'no-dropdown';})()"
	end tell
	delay 1
	tell application "Google Chrome"
		execute t javascript "(function(){var li=[].slice.call(document.querySelectorAll('.t-animation-container li, .t-popup.t-group li')).filter(function(x){return x.innerText.trim()==='500';})[0]; if(li){li.click(); return 'set500';} return 'no500';})()"
	end tell
	-- Wait for the grid to reload at the new page size.
	repeat 12 times
		delay 2
		tell application "Google Chrome"
			set sized to execute t javascript "(function(){var s=(document.querySelector('.t-status-text')||{}).innerText||'';var m=s.match(/(\\d[\\d,]*)\\s*-\\s*(\\d[\\d,]*)\\s*of\\s*(\\d[\\d,]*)/);if(!m)return 'WAIT';var y=parseInt(m[2].replace(/,/g,'')),tot=parseInt(m[3].replace(/,/g,''));return (y>=500||y>=tot)?'SIZED':'WAIT';})()"
		end tell
		if sized is "SIZED" then exit repeat
	end repeat

	-- Read total records + page size actually in effect; compute expected page count.
	tell application "Google Chrome"
		set meta to execute t javascript "(function(){var s=(document.querySelector('.t-status-text')||{}).innerText||'';var m=s.match(/(\\d[\\d,]*)\\s*-\\s*(\\d[\\d,]*)\\s*of\\s*(\\d[\\d,]*)/);if(!m)return '0|0';var y=parseInt(m[2].replace(/,/g,'')),tot=parseInt(m[3].replace(/,/g,''));return y+'|'+tot;})()"
	end tell
	set AppleScript's text item delimiters to "|"
	set metaParts to text items of meta
	set AppleScript's text item delimiters to ""
	set pageSize to (item 1 of metaParts) as integer
	set totalRecords to (item 2 of metaParts) as integer
	if pageSize is 0 then set pageSize to 500
	set expectedPages to (totalRecords + pageSize - 1) div pageSize
	if expectedPages < 1 then set expectedPages to 1

	set harvestJS to "(function(){var ths=[].slice.call(document.querySelectorAll('.t-grid th')).map(function(x){return x.innerText.trim().toLowerCase();});function ci(n){return ths.indexOf(n);}var di=ci('record date'),ty=ci('doc type'),fn=ci('first direct name'),inm=ci('first indirect name'),bt=ci('book type'),bp=ci('book/page'),lg=ci('legal'),ins=ci('instrument #');var rows=[].slice.call(document.querySelectorAll('#SearchGridContainer tbody tr'));var out=[],firstInst='',malformed=0;rows.forEach(function(r){var c=r.querySelectorAll('td');if(c.length<6){return;}function g(i){return i>-1&&c[i]?c[i].innerText.trim():'';}var inst=g(ins).replace(/\\D/g,'');if(!inst){malformed++;return;}if(!firstInst)firstInst=inst;var rd=g(di).replace(/(\\d{2})\\/(\\d{2})\\/(\\d{4})/,'$3-$1-$2');out.push({record_date:rd,instrument_number:inst,doc_type:g(ty),first_direct_name:g(fn),first_indirect_name:g(inm),book_type:g(bt),book_page:g(bp),legal_snippet:g(lg).slice(0,500)});});return JSON.stringify({rows:out,firstInst:firstInst,malformed:malformed});})()"

	set pagesDone to 0
	set prevFirst to ""
	set reason to ""
	repeat with pageNum from 1 to maxPages
		tell application "Google Chrome"
			set pageJSON to execute t javascript harvestJS
		end tell
		-- Persist this page, capture its first instrument for change-detection.
		set curFirst to do shell script "/usr/bin/python3 - " & quoted form of pageJSON & " " & quoted form of outFile & " <<'PY'
import sys, json
d = json.loads(sys.argv[1]); rows = d.get('rows', [])
with open(sys.argv[2], 'a') as f:
    for r in rows:
        f.write(json.dumps(r) + '\\n')
print(d.get('firstInst',''))
PY"
		if curFirst is prevFirst and curFirst is not "" then
			set reason to "repeated_page_" & pageNum
			exit repeat
		end if
		set prevFirst to curFirst
		set pagesDone to pagesDone + 1
		if pagesDone ≥ expectedPages then exit repeat

		-- Advance using the PAGER's next arrow (the calendar has one too — scope it).
		tell application "Google Chrome"
			set clicked to execute t javascript "(function(){var a=document.querySelector('.t-pager .t-arrow-next');if(!a)return 'NOARROW';var link=a.closest('a')||a;if(link.className.indexOf('t-state-disabled')>-1)return 'DISABLED';link.click();return 'CLICKED';})()"
		end tell
		if clicked is not "CLICKED" then
			set reason to "advance_" & clicked & "_page_" & pageNum
			exit repeat
		end if
		-- Wait until the first row's instrument actually changes (true AJAX completion).
		set advanced to false
		repeat 15 times
			delay 1
			tell application "Google Chrome"
				set nowFirst to execute t javascript "(function(){var r=document.querySelectorAll('#SearchGridContainer tbody tr');for(var i=0;i<r.length;i++){var c=r[i].querySelectorAll('td');if(c.length<6)continue;var m=r[i].innerText.match(/\\b\\d{7,}\\b/);if(m)return m[0];}return '';})()"
			end tell
			if nowFirst is not prevFirst and nowFirst is not "" then
				set advanced to true
				exit repeat
			end if
		end repeat
		if not advanced then
			set reason to "stalled_after_page_" & pagesDone
			exit repeat
		end if
	end repeat

	tell application "Google Chrome" to close w

	if reason is not "" then
		return "INCOMPLETE|" & pagesDone & "|" & totalRecords & "|" & reason
	end if
	if pagesDone < expectedPages then
		return "INCOMPLETE|" & pagesDone & "|" & totalRecords & "|cap_reached_expected_" & expectedPages
	end if
	return "OK|" & pagesDone & "|" & totalRecords
end run
