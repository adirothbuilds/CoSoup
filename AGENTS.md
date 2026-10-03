# Repository instructions

- Keep code, documentation, CLI messages and generated reports in English.
- This is personal research software. Do not add broker connections, order execution or paid-plan upgrades.
- Reuse the existing cloud checkout. Cloud tasks are isolated; do not create a Git worktree unless the user explicitly requests one.
- Use `MASSIVE_API_KEY` only through the authorized HTTPS Network secret route to `api.massive.com`. Never print, commit or persist its value. Never forward it to legacy provider hosts or other websites.
- Keep raw data, private reports, signal state, personal recipient addresses and mail permissions outside this public repository.
- Respect the shared persistent limit of at most five provider requests per minute. Stop on exact errors; do not add retry loops or bypass cooldowns, TLS verification or access policy.
- Do not describe missing, stale or blocked data as an absence of opportunities. Report actual coverage and research gaps. Never force a candidate count or describe signal observations as trading returns.
- Run `.venv/bin/python -m unittest discover -v` after substantive changes. Distinguish synthetic tests from current real-data validation. Do not call a zero-test run validation.
- Temporary development processes and cron jobs are not durable schedulers. Prepared deployment templates do not establish an active mail or scheduling connection.
- Obtain the user's approval before any commit or push. Use only the user's Git identity. Do not include Codex in author, committer or `Co-authored-by` fields.
