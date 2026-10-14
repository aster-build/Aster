#!/bin/sh
# Requires API/UI, and the saved DAT example jobs for :713 / :698.
set -eu
BROWSER_BIN=${AGENT_BROWSER_BIN:-agent-browser}
ab() { "$BROWSER_BIN" --session aster-docking "$@"; }
ab open "http://127.0.0.1:3000/replay?campaign=${ASTER_DOCKING_CAMPAIGN:?Set the DAT campaign ID with saved docking jobs}&compound=CHEMBL238_Ki%3A713"
ab wait 1500
ab eval '(()=>{if(document.querySelector(".molecular-canvas").getAttribute("data-candidate")!=="true")throw Error("Saved pose not restored");if(document.querySelector(".scene-status"))throw Error("Viewer failure");document.querySelector(".dock-shortcut").click();})()'
ab wait 500
ab screenshot artifacts/docking/verified-desktop.png --full
ab eval '(()=>{const select=document.querySelector("#dock-pose");select.value="1";select.dispatchEvent(new Event("change",{bubbles:true}));})()'
ab wait 500
ab eval '(()=>{if(document.querySelector(".scene-status"))throw Error("Alternative pose failed");document.querySelector(".dock-overlay input").click();})()'
ab wait 300
ab eval '(()=>{if(document.querySelector(".molecular-canvas").getAttribute("data-candidate")!=="false")throw Error("Overlay did not hide");Array.from(document.querySelectorAll(".replay-ranking button")).find(b=>b.textContent.includes("Ki:698")).click();})()'
ab wait 1000
ab eval '(()=>{if(!document.querySelector(".docking-panel").textContent.includes("Ki:698"))throw Error("Compound not switched");if(document.querySelector(".molecular-canvas").getAttribute("data-candidate")!=="true")throw Error("Second pose missing");})()'
ab set viewport 390 844
ab eval '(()=>{if(document.documentElement.scrollWidth>innerWidth+1)throw Error("Mobile overflow");})()'
ab screenshot artifacts/docking/verified-mobile.png --full
ab errors
ab set viewport 1600 1100
