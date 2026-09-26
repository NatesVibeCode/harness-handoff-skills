---
name: harness-session-review
description: Review existing Codex, Muse, and OpenCode sessions over an explicit period, report evidence and open work with confidence, and diagnose local CLI/auth visibility without continuing sessions.
---

# Cross-harness session review

Use this skill to review existing Codex, Muse, and OpenCode work. This is a
separate read-only workflow from the fresh-only handoff skills. It does not
authorize session continuation, forking, deletion, messaging, sharing, or new
agent runs.

## Collect deterministic observations

Run the bundled `session_review.py` from this skill directory, or use
`scripts/session_review.py` from the repository checkout. By default,
inventory and search use the current filetree: the current directory and its
descendants, matched against recorded session working paths. This is a
filesystem path scope, not a requirement that the harness have a workspace
object. Use `--tree /absolute/path` to choose another filetree or `--scope all`
to include all discoverable local trees. `HARNESS_SESSION_REVIEW_SCOPE` sets
the default scope; a command-line `--scope` overrides it.

```sh
python3 session_review.py doctor
python3 session_review.py inventory \
  --from 2026-09-01 --through 2026-09-25 \
  --timezone America/Los_Angeles
```

Replace the example dates and timezone with the operator's requested inclusive
calendar window. The default timezone is UTC. The tool records both the local
boundaries and the equivalent UTC half-open interval, including daylight-saving
changes. A malformed date or unknown timezone is an error; an absent CLI, data
store, or usable timestamp is a coverage result, not an empty proof.

Add one or more `--harness codex|muse|opencode` flags to select a subset. Muse is
discovered from its local read-only session index by default; use exact IDs only
when you intentionally want a subset. Use `--muse-index` or the
`MUSE_SESSION_INDEX` environment variable when Muse stores its index elsewhere.
OpenCode resolves its database with `opencode db path`; use `--opencode-db` for
an explicitly selected local database. Codex reads both active and archived
session roots under `$CODEX_HOME` (or `~/.codex`).

```sh
python3 session_review.py inventory \
  --from 2026-09-01 --through 2026-09-25 \
  --timezone America/Los_Angeles --harness muse
```

The inventory emits metadata only. It never emits transcript text, reads
credential files, calls inference, or changes session state. Codex scans all
JSONL files incrementally, including archived sessions. Muse and OpenCode
query only metadata columns from local SQLite databases opened read-only. There
is no session-count cap or CLI-list output buffer; unsupported schemas,
unreadable stores, and uncaptured external stores are reported as coverage
gaps.

## Full-text search

Search covers visible user/assistant text from Codex and OpenCode, OpenCode
tool output, and Muse's locally indexed `search_text`. It builds an ephemeral
SQLite FTS5 index in memory and discards it after the query. Results are
metadata-only by default. Use `--show-excerpts` only when matching text is needed;
the short excerpt may contain sensitive content despite best-effort pattern
redaction. Search does not persist transcripts, send them to a provider, or
index private reasoning fields.

```sh
python3 session_review.py search "invoice workflow" --mode all \
  --from 2026-09-16 --through 2026-09-26 \
  --timezone America/Los_Angeles
python3 session_review.py search "session AND index" --mode fts --scope all
python3 session_review.py search "rate limit" --mode phrase --tree /path/to/project
```

`all` requires every word somewhere in the session, `any` accepts any word,
`phrase` matches an exact phrase within a message, and `fts` accepts an FTS5
expression. The default scope is the current
filetree; `--tree` selects another directory and `--scope all` opts into every
local tree. Results contain a session ID, timestamp, and hashed filetree group.
The report omits the query text, which can itself contain sensitive data.
With `--show-excerpts`, they also contain a maximum 480-character excerpt. Search
excludes model reasoning, developer/system prompts, and remote histories absent
from local stores.

### Supported discovery and inspection sources

| Harness | Discovery | Content inspection | Coverage limit |
| --- | --- | --- | --- |
| Codex | `$CODEX_HOME/sessions` and `$CODEX_HOME/archived_sessions` (or `~/.codex` equivalents); scans every local JSONL record. | Searches visible user/assistant text and inspects selected JSONL records by exact ID. Do not use `codex agents`, resume, fork, app-server, or an API thread lookup. | Filetree filtering uses the session's recorded working path; a session rooted above the selected tree is not inferred from files it may have touched. Filesystem modification time is a fallback only when event timestamps are absent. |
| Muse | Local `session-index.db`, default `~/.local/share/muse/session-index.db`; reads IDs, paths, timestamps, status, and indexed `search_text` in SQLite read-only mode. | Search uses indexed text only. For full content inspection, export a selected ID using Muse's redacted export into a private temporary directory. Do not inspect or copy encrypted reasoning fields. | The index is a discovery/search cache and can lag retained logs. Override with `--muse-index` or `MUSE_SESSION_INDEX`. |
| OpenCode | Resolve the local database with `opencode db path`, then query session metadata and visible message/tool text in SQLite read-only mode. | Search covers visible user/assistant text and tool output; selected-session inspection uses the installed CLI's sanitizing export surface. Version 1.18.32 uses `opencode export ID --sanitize`; check local help. Do not attach to a remote server. | Filetree filtering uses recorded project directories; sessions rooted above the selected tree are not inferred from files they may have touched. Remote histories outside the resolved local database are not included. Override with `--opencode-db`. |

Before any content inspection, confirm that the resolved source is local and
belongs to the operator-selected account/workspace. If the CLI is configured
for a remote backend, stop content inspection and mark that coverage as
unavailable. Inspect only the turns needed to substantiate claims. Never print
or paste a full transcript, raw event stream, credentials, secret values,
encrypted reasoning, or large quoted passages. In the report use paraphrases
and exact source references (harness plus session ID and timestamp/turn where
available). Do not send session content to another provider or helper.

Locate selected Codex records by parsing their leading metadata line; emit
paths, not matching transcript lines. For OpenCode and Muse, direct sanitized or
redacted exports to a mode-0700 temporary directory, chmod the export to 0600,
and remove the directory after the review. The current OpenCode 1.18.32 command
is `opencode export ID --sanitize`; check local help before using a different
version. Muse redaction does not remove its encrypted reasoning blobs. Read only
the needed message/tool-result fields with the current local review surface; do
not print the export to the terminal or paste it into the final report. If the
current review environment would transmit these contents to an unapproved
provider, use metadata-only inventory and mark semantic findings unknown.

For a selected Codex `SESSION_ID`, this local locator prints exact matching
JSONL paths only:

```sh
python3 - "$SESSION_ID" "${CODEX_HOME:-$HOME/.codex}" <<'PY'
import json, os, sys

wanted, home = sys.argv[1:3]
for root in (os.path.join(home, 'sessions'), os.path.join(home, 'archived_sessions')):
    for parent, dirs, files in os.walk(root):
        dirs.sort()
        for name in sorted(files):
            if not name.endswith('.jsonl'):
                continue
            path = os.path.join(parent, name)
            try:
                with open(path, 'rb') as stream:
                    meta = json.loads(stream.readline())
            except (OSError, ValueError):
                continue
            payload = meta.get('payload', {}) if isinstance(meta, dict) else {}
            if meta.get('type') == 'session_meta' and (payload.get('session_id') or payload.get('id')) == wanted:
                print(path)
PY
```

Use the selected file with the local file reader, not `cat` or `rg` output.
For other exports, use an isolated temp directory and keep its path private:

```sh
scratch=$(mktemp -d)
chmod 700 "$scratch"
muse export --session "$SESSION_ID" --out "$scratch/muse.json" --redacted >/dev/null 2>&1
chmod 600 "$scratch/muse.json"
# After inspecting only the needed fields:
rm -rf "$scratch"
```

Use the equivalent `opencode export "$SESSION_ID" --sanitize >
"$scratch/opencode.json"` for an OpenCode session on CLI 1.18.32. Check the
installed help first when the command surface differs.

## Build the review

First separate observed facts from interpretations:

- **Deterministic observations:** discovered IDs, timestamp and timestamp
  source, workspace identity, available parent/child IDs, recorded terminal
  event, exact duplicate IDs, current artifact existence, and command exit
  status. Preserve which surface supplied each fact.
- **Judgment:** whether separate threads belong to the same thematic
  workstream; whether an accomplishment is meaningful; whether a weakness is
  supported; and whether a task is still open. Label the basis and confidence.
- **Open work:** mark `explicitly_open` only when the reviewed record contains
  direct evidence that the task is unfinished, blocked, or awaiting a named
  action and no later inspected evidence resolves it. Use `unknown` if the
  relevant ending, artifact, or later session is missing or ambiguous. A stale
  session, missing session, incomplete inventory, empty artifact search, or
  lack of a completion message does not prove that work remains open.
- **Deduplication:** exact harness/session identity is deterministic. Shared
  workspace, close timestamps, similar titles, common artifacts, or commit
  hashes are candidate signals; do not merge threads without human/model
  judgment and evidence. Keep aliases separate from exact IDs if the report is
  intended to leave the machine.
- **Evidence:** cite a local source reference, observation time, and artifact
  path/commit only when it was actually observed. Do not treat chat text alone
  as proof that an artifact exists or a test passed. Report conflicting or
  missing evidence.
- **Strengths and weaknesses:** support each with a specific observed example.
  Distinguish process quality (planning, verification, recovery) from outcome
  quality (artifact or task result); do not rate either from session count or
  length.
- **Next actions:** make each recommendation concrete, assign an owner only
  when the record supports one, and say when operator confirmation is needed.

Follow `review-output.schema.json` for the report fields. Do not save a report,
write a persistent closure ledger, or change repository/workspace state unless
the operator separately asks for that artifact or action. Any closure record
must be explicitly operator-confirmed and separate from deterministic session
observations.

## CLI and provider health

`doctor` checks CLI presence/version, Codex's local `login status`, OpenCode's
`auth list` command result, Muse's local configuration status, and only the
presence (never the value) of a small set of known credential environment
variables. The helper does not open credential files or emit credentials; a
native CLI status command may read its own local auth/config store, and its
output is suppressed when it could reveal account/config details.
This is local readiness visibility, not a provider connectivity test. No API
request, model turn, spend, or new session is created. Report provider
connectivity as `not_probed` and do not claim that a successful CLI/auth check
proves the selected model can answer.

Report missing CLIs, unsupported discovery, command errors, timeouts,
unreadable indexes, unknown timestamps, remote-context exclusions, and sessions that could not be
inspected. Distinguish “no matching sessions found in the checked source” from
“no work happened.” State review confidence against coverage, not against how
conclusive the prose sounds.

## Work Coordination and Praxis boundary

Work Coordination is an optional advisory/share surface, not the session
inventory or review control plane. If the operator asks to share a sanitized
summary, use only its existing `message <text> --work <ref> --from <label>
--status milestone` interface. Do not send transcripts or infer closure from a
Work Coordination status; its status is self-reported presence and does not
control or complete work. The review tool does not read or write its store.

Praxis Forge owns build-time Node/Block/Process readiness and admission checks.
This review may point to session evidence, but chat history is not real-use
proof bound to an exact implementation and test. Forge should validate and
retain its own authorized passing evidence; this workflow does not alter Forge
or certify a capability.

## Required report sections

Return all fields required by `review-output.schema.json`, in this order:

1. Window and timezone.
2. Coverage and confidence, including checked sources and gaps.
3. Workstreams and their thread references.
4. Accomplishments with evidence.
5. Open work, blocked work, and unknown status kept distinct.
6. Strengths and weaknesses with evidence.
7. Recommended next actions.
8. CLI/auth visibility and the explicit provider-probe status.
9. Cost record: zero provider probes/new harness sessions from the helper; say
   when the current review model's inference cost is not visible.
10. Limitations and any operator-confirmed closure notes.

Use concise paraphrases, never transcript excerpts. If no evidence supports a
section, return an empty list with a reason in coverage/limitations rather than
inventing a finding.
