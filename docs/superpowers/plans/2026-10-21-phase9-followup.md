# Phase 9 follow-up

User authorized all three workstreams on separate branches on 2026-10-21.
Base: origin/main 9a8ecad5ca7d2c0a4f82670a4891df1fa5c0410a.

## Constraints
- Preserve the existing guarded FastAPI/SQLite Text2SQL architecture and offline mode.
- Do not publish, open a public tunnel, push, or make live paid model calls.
- Real data and API credentials can be supplied later. Never store credentials in reports.
- Each stream owns its implementation and tests; integrate locally after review.

## Task 1: Demo stability and documentation
Reconcile README and serving instructions with implemented features and reproducible local startup.
Validate offline demo and useful empty/missing-data feedback; fix concrete presentation defects found.
Do not claim archived raw resources are bundled. Leave public hosting opt-in.

## Task 2: Natural-language query quality
Audit out-of-corpus paraphrases and implement bounded, evidence-backed improvements to deterministic
routing/entity handling. Add independent regression questions and verify exact query results.
Preserve semantic guards, existing benchmarks, and refusal of unsupported energy calculations.

## Task 3: Online AI evaluation
Add an explicit opt-in evaluation command through the real guarded pipeline, with dry-run/preflight,
explicit model configuration, bounded calls, redacted errors, and separate online reports.
Use fake clients in tests; report live evaluation as pending when credentials are absent.

## Verification
Baseline: 197 tests pass; Ruff reports 5 lint errors and 7 files needing formatting.
Run targeted tests per stream, full pytest, Ruff lint/format, offline benchmark, and browser smoke.
Review task diffs and integrated changes before reporting completion.
