# Validation appendix: Steve on Apple Silicon, 2026-10-07

Continuation of [the October 6 snapshot](STEVE_MAC_VALIDATION_2026-10-06.md). **Completed:** Steve is connected and running, and an authenticated analysis succeeded and was opened in the actual application UI.

## Verified runtime

New native Docker containers started successfully without restarting Docker Desktop or changing unrelated workloads. The same rebuilt ARM64 worker image was used: `sha256:6c6d16e677ed420f5e9fb6bfb00526143cb4ff42ca7aac06cb0e6da4f36f1540`, Codex CLI `0.160.0`.

`tools/validate_steve_sandbox.py` passed under the actual development Compose settings, both with synthetic authentication and with the existing dedicated authentication file. Every check denied access to authentication, other profile files, wrapper secrets, private data, host env, another task and procfs. Task reads and writes succeeded. Home, temporary-directory and runtime writes were denied. Scratch cleanup succeeded. Credential tests opened and closed paths without reading contents.

A bounded authenticated model request through the deployed adapter also passed the same checks using the model's normal shell tool. The structured result was valid and scratch cleanup succeeded. The first validator invocation rejected a nonempty model coverage-note list after all tool checks had passed. That unnecessary prose restriction was removed; the exact tool checks remained unchanged, and the recorded follow-up passed. No raw model/tool diagnostics or authentication contents were retained in this public record.

## Activation and preservation

Only `CODEX_ENABLED` and `CODEX_SANDBOX_VERIFIED` changed among the original private master-env assignments. Following the user's explicit model choice, `CODEX_MODEL=gpt-6.1-sol` was added. All other original assignments and the dedicated authentication file matched the original preservation hashes. The operator's normal Codex profile was not mounted or modified.

The full setup command waited on remote registry metadata during its initial build. That task's build client was cancelled. The configuration renderer in the existing setup image, `sha256:2d6b863f1a1378b058548f0aee19dba7c9deeffa8d2aba171f04072a2df856a5`, was first matched against reviewed source by SHA256, then used without networking to rerender the same development root. Only the API and optional Codex worker were recreated/started from existing local images. PostgreSQL, web, other CoSoup workers and unrelated projects were preserved.

The API reports Steve ready. The API is healthy and the dedicated worker is running. No pending analyst jobs existed before worker activation.

## Model selection and database correction

The user explicitly requested GPT-6.1 Sol with medium reasoning. The worker's generated command was checked for `--model gpt-6.1-sol` and `model_reasoning_effort="medium"`. The adapter pins the latter explicitly; see the [official Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference). A minimal offline image update containing only the reviewed adapter produced native image `sha256:89370f7c7b27203408036599032fca0f0b5c8c8db223aa46d4fe334389b87d21`. The existing dedicated-auth sandbox checks passed again with that image.

The first application attempt stopped before model execution because the existing `scanner_codex` database role lacked `SELECT` on `signals`, which the authorized context builder reads. The fixed role definition grants that read permission without signal mutation privileges. The standard development admin migration applied it using existing credential references. Live PostgreSQL metadata then confirmed `SELECT=true` and `INSERT/UPDATE/DELETE=false` for that role on `signals`.

The reviewed role definition was retained in deployed source and in a minimal offline update of the existing server image: `sha256:4dc8828aa6af316ae858603ea1f4dda1a2361dc2772927e9bb0c2cca907a9cd8`. A regression test checks signal reads remain available to the analyst while signal mutation stays with the scanner. The full changed-source server suite passed **68 tests**. These tests are synthetic evidence; the PostgreSQL privilege probe and completed analyst job are separate live deployment evidence.

## Application context and completed analysis

The actual web UI successfully previewed one existing dated daily market report and its same-day signal observations. The selected report has partial coverage. Portfolio and uploaded-document permissions are false, and neither is included in the preview. No new provider scan was requested. Report contents and source identifiers remain outside this public repository.

Automated approval review initially rejected task submission pending explicit approval to transmit the selected private report payload to the external Codex model service. The user then explicitly approved that existing daily report and its two same-day signal observations through the existing ChatGPT account, and specified GPT-6.1 Sol medium. Submission proceeded through the actual web UI with that exact scope. After the database correction, the same approved task was resumed through the UI; no duplicate analysis task was created.

The real job finished with `succeeded`. Its saved report has `partial_coverage`, cites all three authorized source IDs, contains 4,844 Markdown characters and seven coverage gaps, and retains the original data date. Independent API checks confirmed the expected source provenance and false portfolio/document export flags. Private report contents and job/report identifiers remain outside this public repository.

A separate browser session verified the successful job in Activity, opened its saved report under Home → Saved servings, confirmed the report text was visible, and confirmed Markdown export was available. Task scratch and synthetic-test scratch were removed. The existing dedicated authentication file remained unchanged. Existing data and unrelated Docker workloads were preserved; Docker Desktop was not restarted. No new provider scan, commit or push was performed.
