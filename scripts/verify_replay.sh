#!/bin/sh
# Requires running API/frontend and at least one recorded two-round campaign.
set -eu
BROWSER_BIN=${AGENT_BROWSER_BIN:-agent-browser}
OUT=${ASTER_REPLAY_OUTPUT:-artifacts/replay-verification}
mkdir -p "$OUT"
ab() { "$BROWSER_BIN" --session aster-molecular "$@"; }
ab open http://127.0.0.1:3000/replay
ab set viewport 1600 1100
ab wait 1200
ab eval '(()=>{if(document.querySelector(".molecular-canvas")?.dataset.ready!=="true")throw Error(document.querySelector(".scene-status")?.textContent||"Viewer unavailable");if(document.querySelectorAll(".contact-list>button").length!==10)throw Error("Contact list missing");if(document.querySelectorAll(".outcome-row").length)throw Error("Outcomes revealed too early");document.querySelector(".contact-list>button").click();})()'
ab wait 800
ab screenshot "$OUT/contact.png" --full
ab eval '(()=>{if(!document.querySelector(".contact-detail")?.textContent.includes("2.83"))throw Error("Residue selection failed");document.querySelectorAll(".replay-steps button")[4].click();})()'
ab wait 200
ab eval '(()=>{if(document.querySelectorAll(".outcome-row").length!==9)throw Error("Eight outcomes missing");Array.from(document.querySelectorAll(".playback-controls button")).find(b=>b.textContent.includes("Step")).click();})()'
ab wait 200
ab eval '(()=>{if(!document.querySelector(".replay-stats").textContent.includes("40"))throw Error("Second fit missing");if(document.querySelectorAll(".outcome-row").length)throw Error("Second-round outcomes leaked into measurement step");document.querySelectorAll(".replay-steps button")[2].click();})()'
ab wait 200
ab eval '(()=>{if(!document.querySelector(".prediction-change"))throw Error("Recorded prediction differences missing");document.querySelectorAll(".replay-steps button")[4].click();})()'
ab wait 200
ab screenshot "$OUT/desktop.png" --full
ab eval '(()=>{Array.from(document.querySelectorAll(".playback-controls button")).find(b=>b.textContent==="Restart").click();})()'
ab wait 100
ab eval 'document.querySelector(".play-button").click()'
ab wait 2600
ab eval '(()=>{if(!document.querySelector(".replay-steps button[aria-current=step]").textContent.includes("Fit model"))throw Error("Playback failed");document.querySelector(".play-button").click();Array.from(document.querySelectorAll(".camera-controls button")).find(b=>b.textContent.includes("Guided tour")).click();})()'
ab wait 2500
ab eval '(()=>{if(!document.querySelector(".camera-controls .active")?.textContent.includes("Pocket"))throw Error("Camera tour failed");Array.from(document.querySelectorAll(".camera-controls button")).find(b=>b.textContent.includes("Stop tour")).click();})()'
ab set viewport 390 844
ab screenshot "$OUT/mobile.png" --full
ab eval '(()=>{if(document.documentElement.scrollWidth>innerWidth+1)throw Error("Mobile overflow");return "Mobile fits"})()'
ab errors
# Disable WebGL in a separate browser; numerical evidence must remain usable.
AGENT_BROWSER_INIT_SCRIPTS="$PWD/scripts/browser/no-webgl.js" "$BROWSER_BIN" --session aster-no-webgl open http://127.0.0.1:3000/replay
"$BROWSER_BIN" --session aster-no-webgl wait 1200
"$BROWSER_BIN" --session aster-no-webgl eval '(()=>{if(!document.querySelector(".scene-status")?.textContent.includes("remain available"))throw Error("No WebGL fallback");if(document.querySelectorAll(".contact-list>button").length!==10)throw Error("Fallback lost contacts");document.querySelectorAll(".replay-steps button")[4].click();})()'
"$BROWSER_BIN" --session aster-no-webgl wait 200
"$BROWSER_BIN" --session aster-no-webgl eval '(()=>{if(document.querySelectorAll(".outcome-row").length!==9)throw Error("Fallback lost replay");return "WebGL-disabled fallback passed"})()'
"$BROWSER_BIN" --session aster-no-webgl close
ab set viewport 1600 1100
ab reload
ab wait 1200
