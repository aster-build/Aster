# Campaign workflow integration

The active `/dashboard` now renders `components/workflow/CampaignWorkflow.tsx` in the approved white/purple theme:

**Set up → Predict → Select → Results → Learn**

This is native React in the existing Next.js frontend, using the existing `/api/backend` proxy and saved campaign API. No iframe, separate prototype server, or static prediction/outcome fixture is required. The original prototype remains under `output/prototypes/campaign-flow` for reference.

- Setup supports saved campaigns, public DAT campaign creation, candidate scope, and batch size.
- Predict fits from observed outcomes and scores candidates; the animation is an explanatory playback, not internal reasoning or a compute-time meter. Saved jobs reconnect on retry.
- Select supports map/table inspection, manually edited batches, three-compound comparisons, live molecular properties and saved/new docking poses. Existing locked/excluded constraints are respected.
- Commit accepts optional `selected_ids`, validates eligibility, capacity and locks, and records the exact manual selection with original preview predictions and training provenance. Revision checks and idempotent retries remain in place.
- Results commits to the actual campaign. Public replay and CSV imports persist. Partial imports and failed assays remain supported.
- Learn compares original predictions with measured outcomes and refits; failed assays never become training values.
- Refresh restores the last campaign and pending results. A valid saved preview can be reopened through Select. Uncommitted manual selection edits are not persisted across refresh.
- Only verified DAT campaigns get the experimental 8Y2G structural viewer; imported campaigns keep their own endpoint and predictions without a misleading DAT overlay.

## Preserved but not rendered

These files remain available without being mounted by the active routes:

| Component / feature | Location | Notes |
| --- | --- | --- |
| Original dashboard and sidebar | `apps/web/src/components/Dashboard.tsx` + `dashboard.css` | Includes its empty state and previous workspace composition. |
| New-campaign CSV import dialog | `ImportDialog` inside `Dashboard.tsx` | Existing imported campaigns remain selectable. New measured/candidate CSV campaign creation is deferred. Result CSV import is active. |
| Lock/exclude editing controls | `Dashboard.tsx` | Existing saved constraints still apply; their editing controls are deferred. |
| Full library status filters and pagination | `Dashboard.tsx` | Replaced onscreen by the Select candidate/batch table. |
| Decision history and event summary | `Dashboard.tsx` | Saved rounds/events remain in the backend. Historical navigation is deferred. |
| Literature evidence search, citations, and attachment panel | `LiteraturePanel.tsx` + `literature.css` | Backend/index and saved evidence are preserved. |
| Resizable workspace | `ResizableWorkspace.tsx` | Approved full-screen layout currently takes its place. |
| Previous workflow strip and keyboard hints | `WorkflowSteps.tsx`, `ui.tsx` | Replaced onscreen by the five-stage navigation. |
| Original evidence replay/tour and residue/contact inspection | `EvidenceReplay.tsx` + `replay.css` | `/replay` redirects to `/dashboard`; component is preserved. |
| Full Mol* scene and old docking panel | `MolecularScene.tsx`, `DockingPanel.tsx` | The active comparison uses the lighter approved canvas viewer and live docking API. Backend validation, saved pose checks and pose selection remain active; old detailed report/contact UI is deferred. |

The previous blue/yellow styling remains only in preserved, unmounted component files. Global and active workflow styling use white and purple.

## Local operation

Start the API with `.venv/bin/python -m uvicorn aster.api:app --host 127.0.0.1 --port 8000` and the frontend from `apps/web` using `npm run dev` (or build and start). `ASTER_API_URL` selects the backend for the existing proxy. Restart an already-running API after updating to enable manual selections and molecular properties.
