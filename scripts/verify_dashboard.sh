#!/bin/sh
# Requires the API and built frontend running, plus agent-browser and its browser.
set -eu
BROWSER_BIN=${AGENT_BROWSER_BIN:-agent-browser}
OUT=${ASTER_VERIFY_OUTPUT:-artifacts/dashboard-verification}
mkdir -p "$OUT"
ab() { "$BROWSER_BIN" --session aster-dashboard-check "$@"; }
ab open http://127.0.0.1:3000/dashboard
ab wait 800
ab snapshot -i -d 2
# A previous check may have left a user-imported campaign selected.
ab eval 'if(!Array.from(document.querySelectorAll("button")).some(b=>/Try a public|Start fresh/.test(b.textContent))){const s=document.querySelector("#campaign-select");const demo=Array.from(s?.options||[]).find(o=>o.text.includes("public replay"));if(!demo)throw Error("Create a public demo before running this check");s.value=demo.value;s.dispatchEvent(new Event("change",{bubbles:true}));}'
ab wait 800
ab eval 'const b=Array.from(document.querySelectorAll("button")).find(b=>/Try a public|Start fresh/.test(b.textContent)); if(!b)throw Error("No demo control");b.click()'
ab wait 800
ab eval 'if(!document.querySelector(".campaign-picker"))throw Error(document.body.innerText); Array.from(document.querySelectorAll("button")).find(b=>b.textContent.includes("Preview next batch")).click()'
ab wait 1500
ab eval 'if(document.querySelectorAll(".shortlist-row").length!==8)throw Error("Missing preview");if(document.querySelectorAll(".plot-point").length!==128)throw Error("Missing scored pool");Array.from(document.querySelectorAll("button")).find(b=>b.textContent.includes("Commit this batch")).click()'
ab wait 600
ab eval 'if(!document.querySelector(".results-panel"))throw Error("No pending batch");Array.from(document.querySelectorAll("button")).find(b=>b.textContent.includes("Replay public outcomes")).click()'
ab wait 600
ab eval 'if(!document.querySelector(".campaign-strip").innerText.includes("40"))throw Error("Round 1 outcomes missing");Array.from(document.querySelectorAll("button")).find(b=>b.textContent.includes("Refresh preview")).click()'
ab wait 1500
ab eval 'if(!document.querySelector(".window-top").innerText.includes("Round 2"))throw Error("Second preview missing");Array.from(document.querySelectorAll("button")).find(b=>b.textContent.includes("Commit this batch")).click()'
ab wait 600
ab eval 'Array.from(document.querySelectorAll("button")).find(b=>b.textContent.includes("Replay public outcomes")).click()'
ab wait 600
ab reload
ab wait 700
ab eval 'if(!document.querySelector(".campaign-strip").innerText.includes("48"))throw Error("Reload lost measurements");if(document.querySelectorAll(".history-row").length!==2)throw Error("Missing history"); if(document.querySelector("[data-nextjs-dialog]"))throw Error("Framework error");({measurements:48,completedRounds:2,rows:document.querySelectorAll(".shortlist-row").length})'
ab set viewport 1440 1100
ab screenshot "$OUT/desktop.png" --full
ab set viewport 390 844
ab screenshot "$OUT/mobile.png" --full
ab eval 'if(document.documentElement.scrollWidth>window.innerWidth+1)throw Error("Mobile horizontal overflow");"Mobile layout fits"'
ab errors
ab open http://127.0.0.1:3000/
ab wait 400
ab eval 'if(!document.querySelector("a[href=\"/dashboard\"]"))throw Error("Landing link missing");"Landing route linked"'
ab open http://127.0.0.1:3000/dashboard
ab set viewport 1440 1100
