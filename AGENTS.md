# Repository instructions

- Keep code, documentation, CLI messages and generated reports in English. Public guides describe the product; test-environment details belong only in validation appendices.
- This is personal research software. Do not add broker connections, order execution or paid-plan upgrades.
- Work in the existing checkout and on main unless the user requests a different branch. Preserve pre-existing changes.
- Use `MASSIVE_API_KEY` only for authorized HTTPS requests to `api.massive.com`; provision it privately for each deployment. Never print, commit or persist its value. Never forward it to legacy provider hosts or other websites.
- Keep raw data, private reports, signal state, personal recipient addresses and mail permissions outside this public repository.
- Respect the shared persistent limit of at most five provider requests per minute. Stop on exact errors; do not add retry loops or bypass cooldowns, TLS verification or access policy.
- Do not describe missing, stale or blocked data as an absence of opportunities. Report actual coverage and research gaps. Never force a candidate count or describe signal observations as trading returns.
- Run the scanner tests with `.venv/bin/python -m unittest discover -s tests -v`, and server tests with `-s apps/server/tests` when server code changes. Distinguish synthetic tests from current real-data validation. Do not call a zero-test run validation.
- Temporary development processes and cron jobs are not durable schedulers. Prepared deployment templates do not establish an active mail or scheduling connection.
- Obtain the user's approval before any commit or push. Use only the user's Git identity. Do not include Codex in author, committer or `Co-authored-by` fields.
