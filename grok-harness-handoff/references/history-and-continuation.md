# Grok history and continuation

## Identify which Grok surface owns the history

Distinguish Grok on the web, Grok within X, API calls, and third-party local clients. A model name does not identify the application that retained its messages.

For the web product, use the authenticated native history UI to search by title/topic, open the selected conversation, and read relevant turns. Record its exact URL or ID, date, and last result. Do not create a public share link merely to read history. The official guide documents a history view, including conversations shared with the account: [Grok user guide](https://docs.x.ai/grok/user-guide).

For Grok within X, inspect that product's own history/export controls; do not assume the grok.com account exposes the same conversation.

## Local clients and exports

There is no universal Grok local transcript path established by this skill. If an installed client owns the conversation, resolve its executable/package and consult its help or source for session persistence. Search the identified client's application-data directory for session indexes, JSON/JSONL exports, or SQLite databases. Inspect filenames and schemas first, then only the selected conversation. In a user-selected export folder, locate conversation files and inspect their structure before interpreting them.

For an API workflow, find the selected application's request/response store or documented retained-response retrieval facility. Follow actual recorded IDs and retention settings; do not assume API credentials provide access to web-product chats. An application may not have persisted its history.

Browser cookies and authentication databases are not transcript discovery mechanisms. Use the signed-in UI or supported export instead of extracting credentials or replaying private endpoints.

## Continue

Continue the exact selected web conversation using its native message composer when sending is requested. For a client/API, use its supported continuation contract and retained context. Report separately whether history was found, read completely, and continued. If records were deleted, expired, or never stored, state the gap precisely; a local filesystem search cannot recover server-only history.

