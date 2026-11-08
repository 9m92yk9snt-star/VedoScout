# Actual MatchRoomPlayer browser review harness

Status: BLOCKED before browser playback, 2026-11-07. No visual approval granted.

Uses actual MatchRoomPlayer.jsx, matchRoomModel.js and matchroom.css from frontend/src/components/report-v2. React 19.0.0, React DOM 19.0.0, lucide-react 0.516.0, esbuild. Browser harness uses Playwright 1.51.1 / Chromium 134 build 1161. Bundle succeeded. Canonical source remains local, not published.

Copy these three component files here, provide data.json from the integrated-mask-review experiment, and source.mp4 as the canonical source. Install dependencies in an isolated folder. Bundle app.jsx with esbuild --bundle --outfile=app.js --loader:.css=css; serve folder on port 8765. Run check.cjs with an installed Chromium executable (adjust local executablePath). Test seeks before, during and after the arrow, repeats a seek, and records half-speed playback frame callbacks plus page errors. Check the player screenshot and result.json before approving anything.

IMPORTANT: app.jsx sets VERIFIED only on an isolated structuredClone render fixture so the approval-gated component can be reviewed. This is NOT an approval or writeback of source data. The original sourceStatus remains PENDING. No approved export or production-data mutation has been performed.

Observed blocker: local Chromium fails during launch with process_singleton_posix.cc socket() failed: Operation not permitted (1). The separate cloud browser cannot reach http://127.0.0.1:8765 (ERR_CONNECTION_REFUSED). Consequently seeking/playback checks and browser screenshot were not obtained. Earlier offline masks, video reviews and code tests remain distinct from this missing web check. No merge/deploy.
