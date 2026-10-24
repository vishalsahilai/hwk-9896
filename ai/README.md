# HCM Lite AI module

Read-only AI workflows for the existing HCM Lite backend. All work is local and uncommitted on `ai_agent`.

## Status and boundaries

The inspected checkout contains documentation and `.gitkeep` placeholders, **no real backend application, JWT dependency, models, migrations, dashboard services or PostgreSQL integration**. This module implements the AI side and exposes explicit integration contracts. It does not invent a second backend, database, authentication system or production fixture fallback. `create_router()` rejects all requests until real dependencies are supplied.

Implemented: LangGraph chat, seven validated tools, company policy retrieval, grounded response selection, dashboard summary, smart leave, provider switching, authorization, deadline, operational logging/rate-limit interfaces, deterministic contract tests. Production readiness still depends on backend bindings and live provider verification. The presence of test fixtures is not evidence of real integration.

## Architecture and files

```
JWT current_user -> /ai router -> AIService (account/role, reservation, deadline)
  chat -> StateGraph: START -> agent -> authorized tools -> agent -> END
       -> evidence selection -> server-rendered response
  summary -> authoritative dashboard -> evidence selection -> bullets
  smart_leave -> server date anchors -> structured model extraction -> validation
All inference -> ProviderManager -> Alibaba -> optional Alibaba backup -> Gemini
All HR reads -> ServiceAdapter -> backend services (independent authorization)
All operational writes -> OperationsAdapter -> backend ai_logs helper
```

`router.py`: three routes and shared validation error envelope; `guard.py`: shared workflow entry; `graph.py`: bounded graph; `tools.py`: schemas and authorized wrappers; `services.py`: protocols; `adapters.py`: callback bindings; `schemas.py`: request/result validation; `providers.py`: async inference/fallback; `policy.py` and `prompts.py`: policy and instructions; `dates.py`: tool date ranges; `smart_leave.py`: form extraction; `dashboard_summary.py`: summary; `render.py`: factual templates; `config.py` / `exceptions.py`: shared settings/errors; `tests/`: isolated fixtures, tests and opt-in live checks.

There are no persistent conversations. The browser owns history. Client assistant messages are reintroduced only as labelled untrusted user data, never trusted evidence.

## Installation

From `backend/`, with Python 3.12 and uv:

```sh
uv sync --python 3.12
uv run pytest
uv run ruff check app/ai
```

`pyproject.toml` declares FastAPI, Pydantic v2, pydantic-settings, LangGraph, LangChain Core, langchain-openai (Qwen compatible API), langchain-google-genai, plus pytest/pytest-asyncio/httpx/ruff development tools. `uv.lock` pins resolved versions. No Redis, Celery, vector store or database dependency is added.

## Provider configuration

Use the repository `.env.example` for names. Settings read process environment only; this module never discovers or reads secret files. Your deployment must load its chosen `.env` on the backend.

```dotenv
AI_PROVIDER=alibaba
ALIBABA_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
ALIBABA_API_KEY=
ALIBABA_TOOL_MODEL=qwen-plus
ALIBABA_FALLBACK_MODEL=
GEMINI_API_KEY=
GEMINI_MODEL=
AI_TIMEOUT_SECONDS=15
AI_RATE_LIMIT_PER_HOUR=20
AI_TIMEZONE=Asia/Karachi
```

`AI_API_KEY` remains a legacy alias for the selected provider; `AI_MODEL` overrides the selected provider's model. Provider-specific variables take precedence for keys. Do not use Character models for tool calls. `ALIBABA_MODELS` is intentionally ignored: a list of role-playing models is not a safe agent configuration. `qwen-plus` is a configurable candidate, not a promise of account/region availability; optional `qwen-flash` must be verified in your region. Gemini requires an explicit available model name. No model key or provider client belongs in frontend code.

References checked during implementation: [Alibaba Qwen Plus capabilities](https://help.aliyun.com/en/model-studio/qwen-plus), [LangGraph conditional edges](https://reference.langchain.com/python/langgraph/graph/state/StateGraph/add_conditional_edges), [LangChain tool binding](https://reference.langchain.com/python/langchain-openai/chat_models/base/BaseChatOpenAI/bind_tools), [Gemini structured output](https://reference.langchain.com/python/langchain-google-genai/chat_models/ChatGoogleGenerativeAI/with_structured_output). Regional capabilities and account access still require a live check.

SDK retries are disabled. Each inference attempt uses part of the remaining request budget, leaving time for fallback. Eligible failures: connections, timeouts, 408/429/404, 5xx and tool/model incompatibility. 401/403 fail closed; neither authorization errors nor output validation errors are retried through another provider. Invalid structured output receives one workflow-level validation retry. Tool results remain in the current graph messages, so switching providers does not restart successful reads. There are never HR write tools.

## Tools and service contracts

Every service is an async function taking `current_user: User` plus the following keyword arguments. The trusted user includes `id`, `role`, `employee_id`, `is_active`, `must_change_password`. Services must independently enforce authorization, scope and department filters; the AI wrapper is an additional layer.

| Service | Keyword arguments | Validated result | Roles |
|---|---|---|---|
| `get_headcount` | `department?: str` | `{total, departments:[{department,count}]}` | admin, hr |
| `get_attendance_summary` | `start_date: date, end_date: date, department?: str` | `{present,late,half_day,absent,on_leave,attendance_rate}` | admin, hr; employee own |
| `get_late_comers` | dates, department?, `limit: int` | `{employees:[{name,late_count}]}` | admin, hr |
| `get_leave_summary` | dates, department? | `{employees:[{name,leave_type}],counts:{type:count}}` | admin, hr |
| `get_my_leave_balance` | none | `{balances:[{leave_type,quota,used,pending,remaining}]}` | own linked employee only |
| `get_payroll_summary` | `month: YYYY-MM, department?: str` | `{total_gross,total_net,average_salary,employee_count}` | admin only |
| `search_employees` | `text: str` | `{employees:[{name,employee_code,department,designation}]}` | admin, hr |

No identity is accepted in tool arguments. Extra fields, including salary in directory results, fail validation. Attendance rate is the backend's percentage on a 0–100 scale; AI never recalculates it. Results are bounded (directory 50, late arrivals 20, department/leave rows 200). Backend services must supply complete aggregates, not silently truncate totals. The directory read should limit its result intentionally to 50.

`departments(current_user) -> list[str]` supplies authorized department names. Matching is case insensitive with optional ` team` suffix. Unknown/misspelled departments produce a notice listing actual departments; fuzzy matching never guesses a scope.

`policy(current_user) -> dict` must supply the **complete current policy projection** accepted by `Policy`: office_start (HH:MM:SS), grace_minutes, half_day_hours, weekend_days (0=Monday), leave_quotas (code -> quota or null). `Policy` defaults mirror the brief for first-run use only. An adapter must not return an empty projection once Admin has changed settings. The projection must be safe for employees, unlike unrestricted `/settings`. Static payroll/permission rules come from the official brief; live hours, grace and quotas replace defaults. Policy read failure never silently substitutes stale settings.

`dashboard(current_user, context: KPIContext) -> dict` must call the same aggregation service as REST. Ignore client KPI values as evidence and fetch authorized server values. Context has optional `start_date`, `end_date`, `department`. Validate/canonicalize department context in the backend, apply the same filters and enforce any organization scope. The provisional chart schemas are in `schemas.py`: actual backend chart JSON has not yet been agreed in API.md, so adapters must normalize it explicitly. Only scalar KPIs and headcount-by-department are currently summarized. Recent audit details are validated but never forwarded to the provider.

Persistent operational callbacks:

```python
async def reserve(*, current_user: User, feature: str, limit: int) -> str: ...
async def complete(*, request_id: str, record: dict) -> None: ...
```

`reserve` must atomically count **all three features and failed/reserved attempts** over a rolling hour, serialize concurrent reservations for a user across workers, insert an initial `ai_logs` row and return its ID. Reject excess with `AIError("AI_RATE_LIMIT", "Please try again later.", 429)`. A transaction-scoped per-user advisory lock or equivalent approved shared backend mechanism is appropriate. Counting completed rows alone is unsafe under concurrency. Never inject an in-memory implementation in production.

`complete` updates the reserved row using the MODELS.md fields: user_id, feature, prompt, tools_called, response, latency_ms, success. `attempts` contains safe provider/status metadata; the adapter may emit this to approved structured logs or discard it rather than invent a DB column. Prompt and answer bodies are always redacted here. Set retention in the backend. Reconcile stale reserved rows as failed if cleanup was interrupted. Default inference deadline leaves up to 250 ms **within** the overall 15 seconds for final persistence. Cleanup failure emits a content-free error and leaves the already durable reservation for reconciliation. Requests rejected before reservation are the auth/rate limiter's responsibility to log safely.

## FastAPI integration

No production app is created because the real backend app does not exist. A test harness exists only inside tests. When the backend is ready:

```python
from app.ai.router import create_router
from app.ai.guard import AIService
from app.ai.config import Settings
from app.ai.providers import ProviderManager
from app.ai.adapters import ServiceAdapter, OperationsAdapter

# Supply all seven real service callables and the three supporting reads.
backend = ServiceAdapter(
    reads, departments=department_names, policy=current_policy, dashboard=dashboard_kpis
)
operations = OperationsAdapter(reserve=reserve_ai_attempt, complete=complete_ai_log)
settings = Settings()
manager = ProviderManager.configured(settings)


# Make this dependency request-scoped if adapters hold a DB session.
async def get_ai_service():
    return AIService(backend, operations, manager, settings)


app.include_router(create_router(current_user, get_ai_service), prefix="/api")
```

`current_user` must verify JWT signature/expiry, reload the active database account, provide all account flags, and enforce the existing forced password rule. Do not derive trusted context from body/history. Module checks inactive/forced-password flags again. Mount `/api` exactly once; the router owns only `/ai`. The module wraps its own request validation in the shared error format, without changing global app handlers.

## API examples

All three endpoints use backend Bearer JWT authentication. Success contracts are unchanged from API.md; only chat includes `ai_generated` because summary and smart-leave have exact existing schemas.

`POST /api/ai/chat` (admin/hr/employee):

```json
{"message":"How many active employees are in Sales?","history":[]}
```

Fixture-only response example (not production seed data):

```json
{"answer":"Active employee count: 3.","tools_used":["get_headcount"],"ai_generated":true}
```

The model chooses tools and relevant evidence IDs. The server renders exact validated service facts and policy paragraphs, so model-authored sentences cannot introduce invented names or figures. Replies are concise English templates. Roman Urdu requests can be understood by the model, and smart-leave explicitly recognizes `kal`, `aaj`, `bukhar`; generated Roman Urdu prose is not implemented. Relevance still depends on model selection, so wrong evidence selection remains possible. There is no free-form model answer that can leak internal instructions. Out-of-scope questions select the safe unavailable-information response. History is capped at 10 messages, 2000 characters each. Current message is 1–2000 characters. Tool loop allows at most three calls total, including parallel batches.

`POST /api/ai/summary` (admin/hr):

```json
{"kpis":{"headcount":3,"present_today":2,"late_today":1,"pending_approvals":0,"context":{"start_date":"2026-10-01","end_date":"2026-10-24","department":"Sales"}}}
```

```json
{"bullets":["Active employee count: 3.","Employees present today: 2.","Employees late today: 1."]}
```

Actual filtered responses include the filter context. Backend values replace submitted metrics. HR never receives payroll summary evidence. A populated dashboard produces three to five validated source-derived bullets. Empty/insufficient dashboards return one honest insufficient-data bullet. Invalid model selections retry once, then use deterministic available facts. Trend claims are not generated without comparisons.

`POST /api/ai/smart-leave` (employee/hr):

```json
{"text":"Next Monday and Tuesday off for my sister's wedding"}
```

With frozen server date 2026-10-24:

```json
{"leave_type":"casual","start_date":"2026-10-26","end_date":"2026-10-27","reason":"sister's wedding"}
```

Production uses current date in Asia/Karachi. Relative dates resolve server-side: today/tomorrow/day after tomorrow, first following weekday, paired weekdays, calendar-day durations, ISO dates, and explicit `3rd to 5th November 2026`. Day-only ranges such as `from the 3rd to the 5th` require clarification because month/year are ambiguous. Wedding/personal -> casual; illness/fever/bukhar -> sick; vacation -> annual; unpaid overrides. Reason must be an exact excerpt. Model dates/type are checked against anchors, and leave type must exist in current policy. Invalid extraction retries once, then AI_PARSE_FAILED. This prepares a form only. Apply still calls normal `POST /api/leaves`; only that service checks holidays, balance, overlaps and working-day rules.

Shared error example:

```json
{"detail":{"code":"AI_PARSE_FAILED","message":"The assistant could not understand the request. Please use the normal form."}}
```

| Code | Status | Meaning |
|---|---|---|
| AUTH_REQUIRED | 401 | Missing/invalid trusted auth integration |
| AI_FORBIDDEN / ACCOUNT_INACTIVE / PASSWORD_CHANGE_REQUIRED | 403 | Role, scope or account restriction |
| AI_INVALID_REQUEST / AI_INVALID_DATES / AI_TOOL_INVALID | 422 | Input/result validation |
| AI_CLARIFICATION_REQUIRED / AI_PARSE_FAILED / AI_TOOL_LIMIT | 422 | Clarify, use normal form, or narrow question |
| AI_RATE_LIMIT | 429 | Shared quota exhausted (backend reservation helper) |
| AI_TIMEOUT | 504 | Overall workflow deadline |
| AI_UNAVAILABLE / AI_TOOL_FAILED / AI_INTEGRATION_REQUIRED | 503 | Provider/service/integration unavailable |

No exception strings, provider credentials or tracebacks are returned. Logs never contain provider exceptions, user text or model output. Do not enable SDK debug logs or LangSmith/environment tracing on HR data without an approved redaction policy; the provider necessarily receives the authorized evidence used for inference.

## Tests and live verification

```sh
cd backend
uv run pytest -q
uv run ruff check app/ai
# Optional billable verification; export both keys and valid model names first:
AI_RUN_LIVE=1 uv run pytest app/ai/tests/test_live.py -q
```

Tests use dependency-injected models and fixtures, not external calls by default. They cover all seven tools, roles, own scope, history/injection, exact routes, deadlines, shared limits, redacted logs, date anchors, invalid JSON, output validation, provider failures and preservation of successful tool results across switching. The real PostgreSQL/JWT test is explicitly skipped until a backend exists. The opt-in live check calls both configured providers for tool selection and structured output; default runs skip it. It does not simulate an outage on the live provider. Failover is tested using deterministic failures.

## Decisions, conflicts and limitations

- User request overrides older Gemini/Groq plan: Alibaba first, Gemini backup. Existing legacy env names are supported.
- API.md wins over the plan's blanket `ai_generated` instruction: only chat adds that field.
- Payroll tool is Admin-only; backend/AI plans' optional HR permission is not enabled.
- `docs/desisions.md` exists and is empty; `docs/decision.md` is absent. Neither is removed or renamed.
- No hackathon PDF is present in this repository. Repository rules supply policy defaults.
- No production stubs, seed data, raw SQL or HR business writes are implemented.
- Service result shapes here are explicit proposed contracts matching the plan. The team's detailed dashboard/chart schemas are not yet defined; backend adapters must normalize them, and API.md must be updated jointly when those shared shapes are finalized.
- Generated output uses fixed factual templates for safety; free-form explanations, Roman Urdu prose and comparative chart narratives are future enhancements.
- Live Qwen/Gemini access, regional model capabilities, real auth/database and multi-worker reservation atomicity require external integration verification.

## Troubleshooting

401 by default means no real `current_user` was bound. 503 AI_INTEGRATION_REQUIRED means no AIService dependency was bound. Missing configured keys yields AI_UNAVAILABLE. 401/403 from providers does not trigger fallback: correct credentials/permissions. Tool schema 422 indicates argument/result mismatch; inspect safe metadata, never dump HR records or keys. Character models are rejected. Unknown department is a scope clarification, not an invitation to broaden access. Summary errors commonly mean the adapter's chart fields differ from the provisional schemas. Use normal HR screens when providers are unavailable.

## Acceptance

Implemented and contract-tested status is recorded in `VERIFICATION.md` after execution. Real backend/JWT/PostgreSQL integration, persistent rate-limit atomicity and live provider compatibility remain unchecked until actually exercised. Nothing is deployed, staged, committed or pushed by this work.
