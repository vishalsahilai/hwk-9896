# Local verification — 25 October 2026 (Asia/Karachi)

## Executed

Python 3.12.15, dependencies pinned in backend/uv.lock.

From backend/:

- `.venv/bin/python -m pytest -q` — **125 passed, 2 skipped, 0 failed**, 0.63 s on final run.
- `.venv/bin/ruff check app/ai --no-cache` — passed.
- `.venv/bin/ruff format app/ai --check --no-cache` — 28 Python files already formatted.
- `git diff --check` — passed; no staged files.
- Generated-source AST parsing and credential-pattern review — passed (tests contain deliberately fake credentials).

The first suite run found a missing import in a newly added SDK-compatibility test (123 passed, 1 failed, 2 skipped). The import was corrected; the full suite then passed. A final compatibility test for google-genai HTTP errors was added and passed. No failures are hidden.

## Skips

1. `test_real_backend_postgres_and_jwt`: repository has no real FastAPI app, JWT dependency, database models, services or migrations. No real PostgreSQL/JWT behavior was exercised.
2. `test_live_both_providers_tool_calling_and_structured_output`: live requests are opt-in; both provider keys are not present in the process environment. No secret files were loaded and no billable model calls were made.

Actual installed provider clients were instantiated with fake test keys and successfully bound tool schemas and structured output without making network requests. This checks SDK API compatibility, not authentication, regional model availability or model behavior.

## Acceptance status

| Requirement | Status |
|---|---|
| Organized implementation in backend/app/ai | Implemented and locally checked |
| LangGraph tool loop; maximum three calls | Implemented and tested |
| Seven read-only tool wrappers | Implemented and tested against service fixtures |
| Three API contracts | Implemented and tested through a FastAPI harness |
| Qwen primary / Gemini fallback | Configured; deterministic failover tests pass |
| Live compatible Qwen and Gemini models | Awaiting credentials and live verification |
| Grounded chat and policy replies | Implemented and tested with fixed evidence rendering |
| Dashboard summaries | Implemented and tested; authoritative dashboard adapter required |
| Smart leave | Implemented and tested; no save path exists |
| Role and own-employee scope | AI layer tested; independent real backend scope enforcement pending |
| Prompt/history isolation and sensitive field rejection | Implemented and tested |
| Overall deadline, malformed-output retry, safe errors | Implemented and tested |
| Shared rate limit and logging | Enforcement interfaces and injected tests pass; durable production callbacks pending |
| Real JWT, inactive account reload, database reads | Blocked by absent backend components |
| No SQL, HR writes, production seed fixtures | Source reviewed and architectural tests pass |
| Documentation and nonsecret env examples | Complete |
| Deployment | Not performed |
| Local-only Git restrictions | ai_agent; no staging, commits, pushes or remote mutations |

## Integration handoff

Bind the real current_user dependency, seven read services, department names, complete live policy projection, role-scoped dashboard aggregation, and atomic durable ai_logs reservation/completion callbacks. Detailed signatures and provisional output schemas are in README.md, services.py and schemas.py. Verify detailed chart mappings with the backend developer; API.md currently does not define them. No production backend files were fabricated.

Free-form generated prose and Roman Urdu answer prose are not implemented: the model chooses evidence, and the server renders English factual templates. Roman Urdu leave input is covered. Ambiguous day-only dates request clarification. Comparative chart narratives are not generated.

The pre-existing untracked root environment file was left untouched. Its contents were not read. The empty backend/ai directory was preserved; the implementation uses the specified backend/app/ai path.
