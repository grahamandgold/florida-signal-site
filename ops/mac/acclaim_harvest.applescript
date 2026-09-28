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
	-- Reuse the operator's one existing official search session. Never open or
	-- close windows, navigate away, or silently accept renewed terms.
	if (count of argv) < 4 then return "INCOMPLETE|0|0|browser_helpers_missing"
	set helperDir to item 4 of argv
	set browserJS to read (POSIX file (helperDir & "/acclaim_browser.js")) as «class utf8»
	if not (application "Google Chrome" is running) then return "SOURCE_WAIT|0|0|accepted_search_session_missing"
	set inventory to ""
	tell application "Google Chrome"
		repeat with browserWindow in windows
			repeat with browserTab in tabs of browserWindow
				set tabURL to URL of browserTab
				if tabURL starts with "https://officialrecords.broward.org/" then
					set inventory to inventory & (id of browserWindow as text) & tab & (id of browserTab as text) & tab & tabURL & linefeed
				end if
			end repeat
		end repeat
	end tell
	set selectionLine to do shell script "/usr/bin/python3 " & quoted form of (helperDir & "/acclaim_browser_session.py") & " " & quoted form of inventory
	set AppleScript's text item delimiters to "|"
	set chosen to text items of selectionLine
	set AppleScript's text item delimiters to ""
	set choice to item 1 of chosen
	if choice is "MISSING" then return "SOURCE_WAIT|0|0|accepted_search_session_missing"
	if choice is "AMBIGUOUS" then return "SOURCE_WAIT|0|0|ambiguous_search_sessions"
	if choice is "TERMS" then return "SOURCE_WAIT|0|0|terms_acceptance_required"
	set windowID to (item 2 of chosen) as integer
	set tabID to (item 3 of chosen) as integer
	tell application "Google Chrome"
		set w to window id windowID
		set t to tab id tabID of w
	end tell

	set probe to "WAIT"
	repeat 20 times
		tell application "Google Chrome" to set probe to execute t javascript (browserJS & ";FSClerkBrowser.state();")
		if probe is not "WAIT" then exit repeat
		delay 2
	end repeat
	if probe is not "READY" then
		my logDiagnostic(t, browserJS, "readiness")
		if probe is "TERMS" then return "SOURCE_WAIT|0|0|terms_acceptance_required"
		return "INCOMPLETE|0|0|not_ready_" & probe
	end if
	tell application "Google Chrome" to set searched to execute t javascript (browserJS & ";FSClerkBrowser.begin('" & targetDate & "');")
	if searched is not "SEARCHED" then
		my logDiagnostic(t, browserJS, "submit")
		if searched is "TERMS" then return "SOURCE_WAIT|0|0|terms_acceptance_required"
		return "INCOMPLETE|0|0|search_not_submitted_" & searched
	end if

	-- Wait for results, a POSITIVELY-detected empty result, or a distinguishable failure.
	-- States: GRID (rows present) · EMPTY (explicit no-results signature) · CF (Cloudflare)
	--         WAIT (still loading). Anything unresolved after the window is a timeout, never EMPTY.
	set gridState to "WAIT"
	repeat 14 times
		delay 2
		tell application "Google Chrome" to set gridState to execute t javascript (browserJS & ";FSClerkBrowser.result('" & targetDate & "');")
		if gridState is not "WAIT" and gridState is not "READY" then exit repeat
	end repeat
	if gridState is "EMPTY" then
		-- Verified zero-record date: Acclaim positively reported "No Results to Display".
		return "EMPTY|0|0"
	end if
	if gridState is "TERMS" then
		my logDiagnostic(t, browserJS, "results")
		return "SOURCE_WAIT|0|0|terms_acceptance_required"
	end if
	if gridState is "CF" then
		my logDiagnostic(t, browserJS, "results")
		return "INCOMPLETE|0|0|cloudflare_block"
	end if
	if gridState is not "GRID" then
		my logDiagnostic(t, browserJS, "results")
		if gridState is not "WAIT" and gridState is not "READY" then return "INCOMPLETE|0|0|result_" & gridState
		-- No grid AND no positive empty-state message: treat as timeout/failure, never as empty.
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


	set pagesDone to 0
	set prevFirst to ""
	set reason to ""
	repeat with pageNum from 1 to maxPages
		tell application "Google Chrome" to set pageState to execute t javascript (browserJS & ";FSClerkBrowser.result('" & targetDate & "');")
		if pageState is not "GRID" then
			my logDiagnostic(t, browserJS, "page")
			set reason to "page_state_" & pageState
			exit repeat
		end if
		set expectedFirst to pagesDone * pageSize + 1
		set harvestJS to browserJS & ";FSClerkBrowser.page('" & targetDate & "'," & expectedFirst & "," & totalRecords & ");"
		tell application "Google Chrome"
			set pageJSON to execute t javascript harvestJS
		end tell
		-- Persist this page, capture its first instrument for change-detection.
		set curFirst to do shell script "/usr/bin/python3 - " & quoted form of pageJSON & " " & quoted form of outFile & " <<'PY'
import sys, json
d = json.loads(sys.argv[1]); rows = d.get('rows', [])
if d.get('error'):
    print('ERROR:' + d['error'])
    raise SystemExit(0)
with open(sys.argv[2], 'a') as f:
    for r in rows:
        f.write(json.dumps(r) + '\\n')
print(d.get('firstInst',''))
PY"
		if curFirst starts with "ERROR:" then
			set reason to "page_validation_" & curFirst
			exit repeat
		end if
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


	if reason is not "" then
		return "INCOMPLETE|" & pagesDone & "|" & totalRecords & "|" & reason
	end if
	if pagesDone < expectedPages then
		return "INCOMPLETE|" & pagesDone & "|" & totalRecords & "|cap_reached_expected_" & expectedPages
	end if
	return "OK|" & pagesDone & "|" & totalRecords
end run

-- Bounded, non-record diagnostic; no query strings, names, cookies or page body.
on logDiagnostic(browserTab, browserJS, stageName)
	try
		tell application "Google Chrome" to set snapshot to execute browserTab javascript (browserJS & ";FSClerkBrowser.diagnostic();")
		log ("ACCLAIM_BROWSER_DIAGNOSTIC " & stageName & " " & snapshot)
	on error
		log ("ACCLAIM_BROWSER_DIAGNOSTIC " & stageName & " unavailable")
	end try
end logDiagnostic
