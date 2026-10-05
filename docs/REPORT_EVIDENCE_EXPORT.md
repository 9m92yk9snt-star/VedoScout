# Persisted report evidence export

Export a single saved report without rerunning analysis, touching report data,
calling models, regenerating frames, changing taps, merging, or deploying.
This is diagnostic access, not a fix for missed goals, shots, or assists.

## Use on the existing live deployment without a deployment

An operator with existing live database/storage access can run the standalone
CLI. Do **not** run it against preview or staging for a live report. The
`--environment` argument is an operator label, not proof of the database's
environment. The package retains the current hostname, source commit when
available, and stored report provenance separately.

Use the Python environment already used by the live application (the CLI uses
its installed `python-dotenv`, `pymongo` and `boto3`). Place **only** these new
files from the draft branch in a private directory, retaining their structure:

```
/tmp/scout-export/backend/report_evidence_export.py
/tmp/scout-export/backend/scripts/export_report_evidence.py
```

No replacement of `/app/backend/server.py`, checkout of a different live
branch, service restart, or public upload is needed. The CLI reads the deployed
application's R2 adapter and source through `--source-root`.

Example for the requested live report (adjust `/app` only if the live application
has a different root):

```bash
python /tmp/scout-export/backend/scripts/export_report_evidence.py \
  --report-id 5df7c569-b6af-4f93-8b2a-c8c134baf2a6 \
  --environment live \
  --source-root /app \
  --upload-dir /app/backend/uploads \
  --env-file /app/backend/.env \
  --output /tmp/scout-export/5df7c569-b6af-4f93-8b2a-c8c134baf2a6-evidence.zip
```

Add `--deployment-id` only if the operator knows the current deployment ID.
Add `--no-video` for a smaller package with one-hour signed R2 download links
where available. External video bytes have no asserted SHA-256 in that mode.
The output filename must be new; existing files are not overwritten. Inherited
environment variables take precedence over `.env`, so check that the process
already has the **live** `MONGO_URL` and `DB_NAME`. Never paste them into a chat.

The CLI performs exactly one `reports.find_one({"id": report_id})`, then reads
`analysis_runs` and `analysis_model_calls` with the selected `report_id`. It does
not read users, credentials or payments collections. Any sharing/download link
for the ZIP must be supplied through the operator's existing authenticated
file delivery mechanism. The exporter does not publish the ZIP to R2, create
public routes, or put the ZIP under `/api/uploads`.

## Admin download after this PR is reviewed and deployed

The Reports table adds **Download analysis evidence ZIP**. Its authenticated
GET is `/api/admin/reports/{report_id}/evidence-export`. The existing
`get_current_admin` dependency protects it; scouts and ordinary users do not
receive export access. `?include_video=false` offers the same smaller package.
This button is not available on the current live deployment before deployment.

The ZIP is built in a private temporary directory, sent with `Cache-Control:
no-store`, and removed after sending, including a failed/disconnected send.
One export/download per server process is allowed at a time; additional
requests receive 429. No export log is added to MongoDB.

## Contents and interpretation

| File | What it establishes |
| --- | --- |
| `report.json` | The entire persisted report snapshot, with credential fields, bearer values and signed URL queries redacted. |
| `anchors.json` | Both raw original tap fields and processed anchors, without retapping or converting times. |
| `canonical.json` | Stored canonical events, event ledger, scoring scan, preview and full report. |
| `analysis_runs.json` | Available run snapshots for this report, including stored outputs and configuration. |
| `analysis_model_calls/*.json` | Available raw model responses and call metadata for this report, plus an index. |
| `traces/*.json` | Referenced FIX10A traces, decompressed and checked against the persisted JSON SHA-256 when present. |
| `video/*` | Available canonical and original referenced bytes, streamed into the archive. |
| `video_metadata.json` | Saved references/time-offset fields and ffprobe metadata on the exact exported bytes when ffprobe is available. |
| `video_links.json` | Intentional private one-hour media download capabilities for omitted R2 video. |
| `runtime.json` | Current export runtime separately from whatever historical run provenance the report actually retained. |
| `source/current/*` | An explicit allowlist of current analysis modules and three server analysis functions, not `.env`, user data or the whole server. |
| `missing_data.json` | Missing, unavailable, size-limited, corrupt or unsupported evidence. |
| `redactions.json` | Field paths changed during credential redaction. |
| `manifest.json`, `SHA256SUMS` | SHA-256 for every payload file; the checksum file also hashes the manifest. |

The complete ZIP is verified before delivery. CLI output includes its byte
size and SHA-256. Hashes apply to the **exported** bytes; source gzip and source
trace JSON hashes are recorded separately before redaction. Neither metadata
file can contain its own recursive checksum.

Production currently stores some `football_sequence_raw` / `event_discovery_raw`
fields as `FIX09B_SEQUENCE_RESPONSE_SUMMARY` with `raw_actions_persisted: false`.
Those are summaries, not recoverable original model responses. The original
upload may already have been removed after transcoding. The package reports
these limitations and never reconstructs missing historical evidence.

No historical video hash, historical deployment ID, historical configuration,
or original-to-web timing transform is inferred from current files. Current
container FPS metadata is not a frame-index timing authority; actual media PTS
and the stored analysis timebase remain authoritative.

Per-file output is limited to 128 MiB; total payload to 512 MiB. Trace JSON
expansion is limited to 64 MiB and at most 200 trace references. Missing/capped
audit reads are listed explicitly: each collection is read one document per
batch and retained up to 64 MiB or 2,000 records. Additional records, unavailable
collections and partial read failures appear in `missing_data.json`. Admin
requests acquire the single export slot before loading audits, and audit reads
have a ten-second timeout. Mongo queries, record filtering and credential
redaction remain report-scoped; no user/payment collections are read. Missing/capped
optional artifacts are listed explicitly. A required metadata failure aborts
the export rather than returning a misleading success.

## Offline verification

```bash
pytest -q backend/tests/test_report_evidence_export.py
python -m py_compile backend/report_evidence_export.py backend/report_export_routes.py \
  backend/scripts/export_report_evidence.py backend/server.py
```

Tests exercise snapshot immutability, exact video bytes, trace hash corruption,
gzip expansion bounds, secret-field redaction, cross-report references,
directory traversal and symlink escape, missing historical evidence, output
permissions and non-overwrite, checksums, admin denial before database access,
read-only route downloads and cleanup on disconnect. These checks do not claim
that the football golden video passes.
