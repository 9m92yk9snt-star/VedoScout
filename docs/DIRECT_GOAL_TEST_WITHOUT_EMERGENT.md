# Original goal test without Emergent

Prepared: direct OpenAI image transport, an isolated single-contact runner and a Python 3.12 Codespaces container. This does not merge, deploy, write production reports or prove full five-action acceptance. Original video and saved contact evidence remain private in ScoutMePlay-direct-test-input.zip, provided separately. Do not commit that ZIP or result JSON.

## Setup

1. Create a project API key at https://platform.openai.com/api-keys and ensure the API project has billing/access for gpt-4o. API requests have their own usage charges. Model availability, quota, latency and billing have not been verified for your account.
2. On GitHub, open your account Settings > Codespaces > Codespaces secrets > New secret. Name: OPENAI_API_KEY. Value: the API key. Under Repository access select 9m92yk9snt-star/VedoScout. Add secret. Never send the value in chat or commit it.
3. Open the repository's codex-r6-contact-seed-handoff-20261013 branch. Code > Codespaces > Create with options. Select the configuration ScoutMePlay Direct Goal Test and a 4-core machine where available. Creating a Codespace may use your GitHub allowance or incur charges. Container dependencies install automatically; this remote installation has not been executed here.
4. Upload ScoutMePlay-direct-test-input.zip into direct-test-work in the Codespace file explorer. This folder is git-ignored. It contains the same video, a saved original trace and checksums, not new taps or a new production upload.
5. In the Codespace terminal, from the repository root, check readiness:

```bash
python backend/scripts/run_direct_goal_review.py --bundle direct-test-work/ScoutMePlay-direct-test-input.zip
```

Preflight checks the archive hashes, exact contact, qualified six-point native path, detector and presence of OPENAI_API_KEY. It makes no model calls. Missing prerequisites return exit 2. api_key_configured and native_detector_available should both be true.

6. Run the real image review:

```bash
python backend/scripts/run_direct_goal_review.py --bundle direct-test-work/ScoutMePlay-direct-test-input.zip --run
```

This allows one direct Chat Completions request to api.openai.com using the existing goal-reader prompt and up to 64 original images. It preserves native scan, camera, identity, goal geometry, direction and final proof checks. It does not supply an expected goal result. The isolated transport survives the existing supporting-reader subprocess boundary. It does not require the Emergent SDK or OpenAI SDK. HTTP errors have no automatic retry; incomplete/refused responses cannot supply evidence. The transport timeout remains 55 seconds, with existing worker lifecycle/deadline checks retained.

Result: direct-test-work/result.json. Share that file back for review. original_goal_proof_verified is true only when the physical goal crossing and final ball proof gate both verify. Exit 3 means original goal proof did not verify; it is not permission to loosen the gates. Exit 2 means configuration/execution error. This runner does not build a new canonical full report/PDF and does not establish 1 goal + 1 saved shot + 3 assists. Stop the Codespace when finished.

## What has actually been verified

- Local original-input preflight: same video hash, selected source contact at 30,915 ms, six measured native positions, available detector. API key absent locally.
- 1,616 offline regression cases passed, 28 SDK-dependent cases skipped; the direct transport has six new tests with zero live API/network/video-decoding attempts in the regression process.
- Live API request, account quota, remote Codespace image/dependency installation and original independent goal recognition have not been run. No automatic original goal PASS is claimed.

References: https://developers.openai.com/api/docs/guides/images-vision ; https://developers.openai.com/api/docs/models/gpt-4o ; https://docs.github.com/en/codespaces/managing-your-codespaces/managing-your-account-specific-secrets-for-github-codespaces
