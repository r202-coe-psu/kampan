---
name: pr-code-review
description: Comprehensive code review checklist and guidelines for evaluating Pull Requests in Kampan. Uses Flask best practices, MongoEngine/MongoDB query best practices, multi-tenancy isolation, and PEP 8 standards. Use when asked to review code, analyze a PR, or check code quality before merging.
---

# PR Code Review Guidelines (Kampan)

## Trigger Commands

**Default — analyze only (never auto-post):**
- `/pr-code-review <PR_LINK_OR_NUMBER>`
- `@[pr-code-review] review <PR>`
- Any request to review a PR or local changes

For these triggers you MUST analyze the changes and **display the review in chat only**. Do **not** call `gh pr review`, `gh pr comment`, or any other command that writes to GitHub unless the user explicitly asks you to post (see below).

**Local staged changes (pre-PR):**
- `@[pr-code-review] review staged`
- Review local / unstaged diff when asked

Use `git diff --cached` (staged) or `git diff` (unstaged) as appropriate, evaluate, and output the review in chat.

**Post to GitHub — explicit command only:**
- `/pr-code-review post <PR_LINK_OR_NUMBER>`
- User says e.g. "post this review", "submit review to GitHub", "approve/request-changes on PR #N"
- Batch: "post reviews for PR #12, #15" — load one artifact per PR (see **Review Artifacts**)

Only then may you run `gh pr review`. **Always read the review body from the artifact file** for that project + PR (not from chat memory). Never post without an explicit post command in the same or a follow-up message.

## Review Artifacts (mandatory)

Every completed review MUST be persisted as a **temporary artifact outside the workspace** so post steps are reliable across turns and support multiple PRs.

### Storage location

```
$HOME/.cursor/pr-code-review/
```

- **Outside the workspace** — never under the project repo.
- Create the directory if missing (`mkdir -p`).
- Mode `0700` on the directory when you create it.

### Filename

```
{owner}__{repo}__pr-{number}.md
```

Resolve `{owner}` and `{repo}` from the current git remote (`gh repo view --json nameWithOwner`) or `git remote get-url origin`. Example: `saktanuthpeak__kampan__pr-12.md`.

**Local / pre-PR reviews** (no GitHub PR yet):

```
{owner}__{repo}__local-{staged|unstaged|diff}.md
```

### File format

Markdown with YAML frontmatter. The body (below the closing `---`) is what gets posted to GitHub.

```markdown
---
project_owner: saktanuthpeak
project_repo: kampan
project_full_name: saktanuthpeak/kampan
pr_number: 12
pr_title: "feat(items): add item inventory check"
pr_url: https://github.com/saktanuthpeak/kampan/pull/12
verdict: Request changes
review_action: request-changes
merge_ready: false
attempt_count: 2
escalation_required: false
created_at: 2026-08-18T14:00:00+07:00
workspace: /home/saktanuthpeak/kampan
---

## PR Review — feat(items): add item inventory check

**Verdict:** Request changes
**Merge readiness:** ❌ ยังไม่พร้อม merge

### Blockers
- …

### Warnings
- …

### Suggestions
- …

### Nitpicks
- …

### Merge readiness (summary)

- **Status:** ❌ ยังไม่พร้อม merge / ✅ พร้อม merge / ⚠️ พร้อม merge (มีข้อควรระวัง)
- **สรุป:** <1–2 ประโยค อธิบายว่าทำไมพร้อมหรือยังไม่พร้อม>
- **ก่อน merge:** <สิ่งที่ต้องทำก่อน merge — หรือ `—` ถ้าพร้อมแล้ว>
```

**`review_action`** — one of `comment` | `approve` | `request-changes`. Set from verdict:
- Approve, no blockers → `approve`
- Blockers remain → `request-changes`
- Otherwise → `comment`

**`verdict`** — human-readable label for chat context only.

**`merge_ready`** — `true` | `false` (artifact frontmatter only; not posted). Set from **Merge readiness** rules below.

### Merge readiness (mandatory)

Every review MUST state clearly whether the change is **ready to merge**. Include:

1. **One-line badge** immediately after **Verdict** (visible at a glance):
   - `**Merge readiness:** ✅ พร้อม merge`
   - `**Merge readiness:** ❌ ยังไม่พร้อม merge`
   - `**Merge readiness:** ⚠️ พร้อม merge (มีข้อควรระวัง)` — only when allowed (see table)
2. **`### Merge readiness (summary)`** section at the **end** of every review (chat + artifact body) with **Status**, **สรุป**, and **ก่อน merge**.

| Status | `merge_ready` | Condition |
| --- | --- | --- |
| ✅ พร้อม merge | `true` | No blockers, verdict `Approve`, `escalation_required` is false |
| ❌ ยังไม่พร้อม merge | `false` | Any blocker, verdict `Request changes`, or `escalation_required` is true |
| ⚠️ พร้อม merge (มีข้อควรระวัง) | `true` | No blockers, verdict `Comment`, only warnings/suggestions/nitpicks — merge acceptable but note follow-ups in **สรุป** |

**สรุป** must answer in plain language: *พร้อม merge แล้วหรือยัง และทำไม* (1–2 sentences). Use Thai for **Status** / **สรุป** / **ก่อน merge**; English summary optional in parentheses.

When **ยังไม่พร้อม merge**, **ก่อน merge** must list concrete next steps (e.g. แก้ blockers, รอ senior verify). When **พร้อม merge**, write `—`.

### After review (write artifact)

1. **Load / update attempt state** — see **Review Attempt Threshold** (increment on fail, reset on pass).
2. Finish analysis and format the review (see **Output Format**).
3. Display the review in chat (include escalation notice when `attempt_count >= 3`).
4. **Write the artifact file** to `$HOME/.cursor/pr-code-review/{owner}__{repo}__pr-{number}.md` — include `merge_ready`, `attempt_count`, and `escalation_required` in frontmatter.
5. **Write / update / delete** the matching `.state.json` file.
6. Tell the user the artifact path so they can edit it before posting.
7. If an artifact for the same project + PR already exists, **overwrite** it (latest review wins).

### Before post (read artifact)

1. Resolve target PR number from the user's command.
2. Resolve `{owner}` / `{repo}` from the current repo; confirm they match the artifact frontmatter (warn if mismatch).
3. **Read the artifact file** — use the markdown body as the `gh pr review -b` payload.
4. Honor `review_action` in frontmatter unless the user explicitly overrides (e.g. "post as approve").
5. If `escalation_required: true`, apply **Posting under escalation** rules before posting.
6. If the artifact is missing, stop and ask the user to re-run the review or provide the path.

### After successful post (delete artifact)

1. Run `gh pr review` with the body from the artifact.
2. **Only on success** (exit code 0): delete the artifact file (`rm`) **and** the matching `.state.json` if the posted review was an **Approve**.
3. Confirm in chat which PR was posted and that the artifact was removed.

### On post failure

- **Do not delete** the artifact.
- Report the error; the user can fix the artifact or retry.

### Multiple PRs

- Each PR gets its **own artifact file** — safe to review many PRs in one session.
- Posting multiple PRs: load and post **one artifact per PR** sequentially; delete each only after its post succeeds.
- Never merge multiple PR reviews into one GitHub comment.

## Human Review First (mandatory)

1. Analyze → display findings in chat grouped by severity.
2. **Save artifact** to `$HOME/.cursor/pr-code-review/`.
3. Human reads chat output and/or **edits the artifact file** directly.
4. Human explicitly commands post → read artifact → post to GitHub → delete artifact on success.

If the user has not said to post, end your response with a short note that the review is for human review only, include the artifact path, and that they can ask you to post when ready.

## Review Attempt Threshold (3 attempts)

Track consecutive **non-passing** reviews per PR (or local review target). When a target fails **3 times**, escalate — a **senior developer** or **tech lead** must verify manually before merge.

**Constant:** `MAX_REVIEW_ATTEMPTS = 3`

### Pass / fail

| Result | Condition |
| --- | --- |
| **Pass** | Verdict is `Approve` — no blockers |
| **Fail** | Verdict is `Request changes`, **or** the review lists one or more **Blockers** (even if verdict is `Comment`) |

### State file

Persist attempt count alongside artifacts (same directory, same `{owner}__{repo}__` prefix):

```
$HOME/.cursor/pr-code-review/{owner}__{repo}__pr-{number}.state.json
```

Local / pre-PR reviews:

```
$HOME/.cursor/pr-code-review/{owner}__{repo}__local-{staged|unstaged|diff}.state.json
```

```json
{
  "project_full_name": "saktanuthpeak/kampan",
  "review_target": "pr-12",
  "attempt_count": 2,
  "last_verdict": "Request changes",
  "last_review_at": "2026-08-18T14:00:00+07:00",
  "escalation_required": false
}
```

- Create the directory with mode `0700` if missing.
- `review_target` — e.g. `pr-12`, `local-staged`.

### Counter workflow (every analyze review)

1. **Load state** — read `.state.json` for this target; if missing, treat `attempt_count` as `0`.
2. **Analyze** — run the normal review checklist.
3. **Update counter:**
   - **Pass** → set `attempt_count = 0`, **delete** `.state.json`.
   - **Fail** → increment `attempt_count`, write `.state.json` with `last_verdict`, `last_review_at`, and `escalation_required: attempt_count >= 3`.
4. **Escalation** — when `attempt_count >= 3` after a fail:
   - Set `escalation_required: true` in state **and** artifact frontmatter.
   - Display the **Escalation notice** (below) at the top of chat output and in the artifact body (immediately after the verdict line).
   - Do **not** auto-post (existing rule). Warn that senior/tech lead sign-off is required before merge.

### Escalation notice (mandatory when `attempt_count >= 3`)

```markdown
> ⚠️ **ต้องให้ Senior / Tech Lead ตรวจสอบเอง (ครบ {attempt_count}/3 ครั้ง)**
>
> PR นี้ยังไม่ผ่านการ review หลังพยายามแก้ไขครบ 3 ครั้งแล้ว กรุณาให้ **senior developer** หรือ **tech lead** เข้ามา verify และตรวจสอบด้วยตัวเองก่อน merge
>
> *This change has not passed review after 3 attempts. A senior developer or tech lead must manually verify before merge.*
```

### Posting under escalation

If artifact frontmatter has `escalation_required: true` and the user requests post:

1. Warn that senior/tech lead manual verification is expected.
2. Post **only** if the user explicitly confirms in the same or follow-up message (e.g. "post anyway", "senior approved").

## Output Format (chat)

Always structure the in-chat review with these four severity levels:

| Level | When to use |
| --- | --- |
| **Blocker** | Must fix before merge — security holes (tenant leak, missing ACL), financial precision bugs (Float for money), DB integrity issues, unhandled exceptions in critical paths |
| **Warning** | Should fix — inefficient Mongo queries (N+1, missing index/only), missing WTForms validation, weak error handling, missing guard clauses |
| **Suggestion** | Nice to have — cleaner abstraction, moving logic from views to controllers/repositories, better Jinja/DaisyUI semantic usage |
| **Nitpick** | Optional polish — PEP 8 style, import order, minor naming, trivial formatting |

Template (chat display **and** artifact body below frontmatter):

```markdown
## PR Review — <title or number>

**Verdict:** <Approve / Request changes / Comment — for human context only; not posted>
**Merge readiness:** <✅ พร้อม merge / ❌ ยังไม่พร้อม merge / ⚠️ พร้อม merge (มีข้อควรระวัง)>
**Attempt:** <attempt_count>/3> *(omit line when attempt_count is 0)*

<!-- Escalation notice here when attempt_count >= 3 — see Review Attempt Threshold -->

### Blockers
- …

### Warnings
- …

### Suggestions
- …

### Nitpicks
- …

### Merge readiness (summary)

- **Status:** <same as one-line badge above>
- **สรุป:** <1–2 ประโยค — พร้อม merge แล้วหรือยัง และทำไม>
- **ก่อน merge:** <ขั้นตอนที่ต้องทำ หรือ `—` ถ้าพร้อมแล้ว>
```

When suggesting code changes, use **Markdown diff blocks** (` ```diff `) with `-` / `+` lines, not plain code blocks.

If a section has no items, write `None.`

End chat output with:

```markdown
---
*Review saved to `~/.cursor/pr-code-review/{owner}__{repo}__pr-{number}.md` (attempt {attempt_count}/3). Edit that file if needed, then say "post review to GitHub" (or `/pr-code-review post <PR>`) when ready.*
```

When `escalation_required: true`, add:

```markdown
*⚠️ ครบ 3 ครั้งแล้ว — ต้องให้ senior dev หรือ tech lead ตรวจสอบเองก่อน merge*
```

---

## Kampan Specific Review Checklist

### 1. Multi-Tenancy & Security (RBAC / ACL)
- **Organization Scoping:** Are all tenant document queries explicitly filtered by `organization=...` (from authenticated context e.g. `current_user.organization` or `g.organization`)?
- **No Client Tenant Injection:** Does the code avoid trusting `organization_id` supplied in request parameters without verifying `acl.organization_roles_required` or membership?
- **ACL Decorators:** Are routes protected with `@login_required` and `@acl.organization_roles_required(...)` where appropriate?
- **CSRF Protection:** Do POST requests use WTForms / Flask-WTF CSRF validation?
- **Safe References:** When saving `created_by` or `updated_by` reference fields, is `current_user._get_current_object()` used?

### 2. MongoDB & MongoEngine Query Best Practices
- **DecimalField for Money:** Are all monetary values, budgets, amounts, and prices stored using `me.DecimalField(precision=2)` instead of `FloatField` or `IntField`?
- **Arithmetic Casting:** Are database decimal fields cast to `float` in calculation loops and written back properly to avoid Python `TypeError` between float and Decimal?
- **Query Optimization:** Are queries over large collections restricted using `.only(...)` or `.exclude(...)`?
- **Avoid N+1 Queries:** Does the code avoid looping over querysets and dereferencing relations one-by-one?
- **Atomic Mutations:** Are state mutations and counter increments performed using atomic Mongo operations (`.update_one()`, `.modify()`, `$inc`, `$push`) rather than read-save race-prone steps where needed?
- **Indexing:** Are query filter fields (e.g. `status`, `created_date`, `organization`) properly indexed in `meta = {"indexes": [...]}`?

### 3. Flask & Route Organization Standards
- **Blueprint Modularity:** Are routes defined inside feature Blueprints with appropriate URL prefixes?
- **WTForms Validation:** Is input validated using WTForms schemas in `kampan/web/forms/` with `form.validate()` before processing?
- **Guard Clauses:** Do route handlers use early returns for validation failures / permissions, keeping the happy path at the bottom?
- **Business Logic Separation:** Is heavy business logic decoupled from views into `kampan/controllers/` or `kampan/repositories/`?
- **Template Hygiene (DaisyUI & Tailwind):** Do Jinja templates use DaisyUI semantic classes (`btn-primary`, `bg-base-200`) and the `format_amount` filter instead of raw hardcoded colors or ad-hoc styles?
- **User Feedback:** Are feedback messages shown via `flash(message, category)`?

### 4. Code Quality, Testing & Hygiene
- **PEP 8 & Formatting:** Are imports ordered (standard lib, 3rd party, local `kampan`), variables in `snake_case`, and classes in `PascalCase`?
- **Type Hints:** Are helper and controller functions annotated with clear Python type hints?
- **Testing:** Are new features, calculations, and permission gates covered by Unit/Integration tests?
- **Clean Code & Leftovers:** Is the diff free of `print()`, `breakpoint()`, `import pdb`, `console.log`, and commented-out dead code?

---

## Fetching PR Data (GitHub CLI — read-only)

When reviewing a GitHub Pull Request, use `gh` to **fetch only**:

- `gh pr view <number>` — PR description, title, labels, checks
- `gh pr diff <number>` — full diff
- `gh repo view --json nameWithOwner,url` — project identity for artifact naming

Do **not** write to GitHub during the analyze step.

## Posting to GitHub (explicit command only)

After the human approves posting:

1. Read artifact: `$HOME/.cursor/pr-code-review/{owner}__{repo}__pr-{number}.md`
2. Extract body (markdown below frontmatter) and `review_action` from frontmatter
3. Post using the body file (prefer `--body-file` over inline `-b` for long reviews):

```bash
gh pr review <number> --comment --body-file "$HOME/.cursor/pr-code-review/{owner}__{repo}__pr-{number}.md"
```

For `--approve` or `--request-changes`, pass only the **body** (not frontmatter). Strip frontmatter before posting.

Mapping:
- `review_action: comment` → `gh pr review <n> --comment --body-file <body-only-file>`
- `review_action: approve` → `gh pr review <n> --approve --body-file <body-only-file>`
- `review_action: request-changes` → `gh pr review <n> --request-changes --body-file <body-only-file>`

4. On success: `rm` the artifact
5. On failure: keep artifact, report error

---

## Review Process Workflow

1. **Fetch and analyze the diff**
   - **PRs:** `gh pr view` + `gh pr diff` + `gh repo view`
   - **Local:** `git diff --cached` or `git diff`
2. **Load attempt state** — read `.state.json` for this review target (see **Review Attempt Threshold**).
3. **Load related skills** (read and apply before concluding):
   - `flask-bestpractices` — routing, blueprints, WTForms, views vs controllers
   - `mongodb-query-bestpractices` — MongoEngine ODM, org scoping, DecimalField, `.only()`
   - `security-rbac-bestpractices` — ACL, multi-tenant isolation, session security
   - `project-structure-architecture` — MVC/Repository layers, directory placement
   - `testing-bestpractices` — test coverage, mocking, fixtures
   - `daisyui-tailwind-bestpractices` — Jinja2 UI, DaisyUI semantic themes
4. **Check the checklist** — sections 1–4 above.
5. **Formulate feedback** — Blocker / Warning / Suggestion / Nitpick; use diff blocks for fixes.
6. **Determine merge readiness** — set one-line badge, summary section, and `merge_ready` frontmatter.
7. **Update attempt counter** — pass resets, fail increments; escalate at 3.
8. **Display in chat** and **write artifact + state** to `~/.cursor/pr-code-review/`.
9. **Post to GitHub** (explicit command only) — read artifact → post → delete artifact on success.
