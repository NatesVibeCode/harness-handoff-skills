"""Official Python SDK executors for the six authorized Python bindings.

Each executor lazily imports its vendor package, so this module imports cleanly
on machines where no SDK is installed. Availability is probed with
`available(harness)`; the server prefers an authorized SDK route and falls back
to the pinned CLI otherwise. Nothing here invents APIs: entry points match the
contract (`packages`/`entrypoints`) and vendor documentation.

Authorized Python resume/history coverage:
- claude: fresh, exact resume/fork, session listing and message retrieval.
- cursor: fresh, exact resume, run conversation retrieval.
- copilot: fresh, exact resume; history via CLI fallback.
- muse: fresh, exact resume; history via CLI fallback.
- antigravity: fresh, SDK-owned restore; native history via CLI fallback.
- openhands: fresh; resume/history via CLI fallback.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys

from mcp_bridge import cli_executor


def available(harness: str) -> bool:
    """True when the authorized Python SDK package is importable."""
    module = {
        "claude": "claude_agent_sdk",
        "cursor": "cursor_sdk",
        "copilot": "copilot",
        "muse": "muse_code",
        "antigravity": "google.antigravity",
        "openhands": "openhands.sdk",
    }.get(harness)
    if not module:
        return False
    if module in sys.modules:
        return True
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def _receipt(harness: str, session_id: str | None, output: str) -> dict:
    return {"harness": harness, "route": "sdk", "session_id": session_id, "output": cli_executor.redact(output[-8000:])}


# --- claude ---------------------------------------------------------------


async def claude_fresh(prompt: str, workspace: str | None, model: str | None, approval: str) -> dict:
    if model:
        raise RuntimeError("claude SDK adapter cannot bind the selected model")
    from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, SystemMessage, query

    options = ClaudeAgentOptions(
        cwd=workspace or ".",
    )
    session_id: str | None = None
    result_text = ""
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, SystemMessage) and message.subtype == "init":
            session_id = message.data.get("session_id", session_id)
        elif isinstance(message, ResultMessage):
            session_id = message.session_id
            result_text = str(message.result or "")
    return _receipt("claude", session_id, result_text)


async def claude_resume(session_id: str, prompt: str, workspace: str | None) -> dict:
    from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

    result_text = ""
    async for message in query(
        prompt=prompt,
        options=ClaudeAgentOptions(resume=session_id, cwd=workspace or "."),
    ):
        if isinstance(message, ResultMessage):
            result_text = str(message.result or "")
    return _receipt("claude", session_id, result_text)


async def claude_history(session_id: str, workspace: str | None, limit: int = 20) -> dict:
    from claude_agent_sdk import get_session_messages

    messages = await asyncio.to_thread(
        get_session_messages, session_id, {"dir": workspace or ".", "limit": limit}
    )
    return _receipt("claude", session_id, str(messages))


# --- cursor ---------------------------------------------------------------


async def cursor_fresh(prompt: str, workspace: str | None, model: str | None, approval: str) -> dict:
    if not model:
        raise RuntimeError("cursor SDK route needs an explicit model; discover it via the models listing first")
    from cursor_sdk import Agent, LocalAgentOptions

    with Agent.create(
        model=model,
        local=LocalAgentOptions(cwd=workspace or "."),
    ) as agent:
        run = agent.send(prompt)
        text = run.wait() if hasattr(run, "wait") else run.text()
        return _receipt("cursor", agent.agent_id, str(text))


async def cursor_resume(session_id: str, prompt: str, workspace: str | None) -> dict:
    if workspace:
        raise RuntimeError("cursor SDK resume cannot bind or verify the selected workspace")
    from cursor_sdk import Agent

    agent = Agent.resume(session_id)
    run = agent.send(prompt)
    text = run.wait() if hasattr(run, "wait") else run.text()
    return _receipt("cursor", agent.agent_id, str(text))


async def cursor_history(session_id: str, workspace: str | None, limit: int = 20) -> dict:
    if workspace:
        raise RuntimeError("cursor SDK history cannot verify the selected workspace")
    from cursor_sdk import Agent

    agent = Agent.resume(session_id)
    conversation = agent.conversation() if hasattr(agent, "conversation") else None
    return _receipt("cursor", session_id, str(conversation))


# --- copilot --------------------------------------------------------------


async def copilot_fresh(prompt: str, workspace: str | None, model: str | None, approval: str) -> dict:
    if approval != "unattended":
        raise RuntimeError("copilot SDK approve_all requires explicit unattended authorization")
    if workspace:
        raise RuntimeError("copilot SDK adapter cannot bind the selected workspace")
    if not model:
        raise RuntimeError("copilot SDK adapter requires an explicit model")
    from copilot import CopilotClient
    from copilot.session import PermissionHandler

    async with CopilotClient() as client:
        async with await client.create_session(
            on_permission_request=PermissionHandler.approve_all,
            model=model,
        ) as session:
            send = getattr(session, "send_and_wait", None)
            if send is None:
                await session.send(prompt)
                return _receipt("copilot", session.session_id, "(sent; watch session events)")
            response = await send(prompt)
            return _receipt("copilot", session.session_id, str(response))


async def copilot_resume(session_id: str, prompt: str, workspace: str | None,
                         approval: str = "default") -> dict:
    if approval != "unattended":
        raise RuntimeError("copilot SDK approve_all requires explicit unattended authorization")
    if workspace:
        raise RuntimeError("copilot SDK resume cannot bind or verify the selected workspace")
    from copilot import CopilotClient
    from copilot.session import PermissionHandler

    async with CopilotClient() as client:
        session = await client.resume_session(
            session_id, on_permission_request=PermissionHandler.approve_all
        )
        send = getattr(session, "send_and_wait", None)
        if send is None:
            await session.send(prompt)
            return _receipt("copilot", session_id, "(sent; watch session events)")
        response = await send(prompt)
        return _receipt("copilot", session_id, str(response))


# --- muse -----------------------------------------------------------------


async def muse_fresh(prompt: str, workspace: str | None, model: str | None, approval: str) -> dict:
    if model:
        raise RuntimeError("muse SDK adapter cannot bind the selected model")
    from muse_code import MuseClient, MuseClientSpawnOptions, SendUserTurnOptions, StartSessionOptions

    client = await MuseClient.spawn(
        MuseClientSpawnOptions(
            muse_bin="muse",
            args=("serve",),
            client_info={"name": "harness-handoff-mcp", "version": "1.0.0"},
        )
    )
    try:
        session = await client.start_session(StartSessionOptions(workspace_root=workspace or "."))
        session_id = getattr(session, "session_id", None) or getattr(session, "sessionId", None)
        turn = await session.send_user_turn(
            SendUserTurnOptions(input=[{"type": "text", "text": prompt}], composer_input=prompt)
        )
        chunks: list[str] = []
        async for item in turn.items():
            chunks.append(str(item))
        await turn.completed
        return _receipt("muse", session_id, "\n".join(chunks))
    finally:
        await client.close()


async def muse_resume(session_id: str, prompt: str, workspace: str | None) -> dict:
    if workspace:
        raise RuntimeError("muse SDK resume cannot bind or verify the selected workspace")
    from muse_code import MuseClient, MuseClientSpawnOptions, SendUserTurnOptions

    client = await MuseClient.spawn(
        MuseClientSpawnOptions(
            muse_bin="muse",
            args=("serve",),
            client_info={"name": "harness-handoff-mcp", "version": "1.0.0"},
        )
    )
    try:
        session = await client.resume_session(session_id)
        turn = await session.send_user_turn(
            SendUserTurnOptions(input=[{"type": "text", "text": prompt}], composer_input=prompt)
        )
        chunks: list[str] = []
        async for item in turn.items():
            chunks.append(str(item))
        await turn.completed
        return _receipt("muse", session_id, "\n".join(chunks))
    finally:
        await client.close()


# --- antigravity ----------------------------------------------------------


async def antigravity_fresh(prompt: str, workspace: str | None, model: str | None, approval: str) -> dict:
    if workspace or model:
        raise RuntimeError("antigravity SDK adapter cannot bind the selected workspace or model")
    from google.antigravity import Agent, LocalAgentConfig

    config = LocalAgentConfig()
    async with Agent(config) as agent:
        response = await agent.chat(prompt)
        return _receipt("antigravity", getattr(agent, "conversation_id", None), await response.text())


async def antigravity_resume(session_id: str, prompt: str, workspace: str | None, *, save_dir: str, app_data_dir: str | None = None) -> dict:
    """Restore an SDK-owned session only: matching save_dir/app_data_dir required."""
    if workspace:
        raise RuntimeError("antigravity SDK restore cannot bind or verify the selected workspace")
    from google.antigravity import Agent, LocalAgentConfig

    config = LocalAgentConfig(
        save_dir=save_dir, conversation_id=session_id, app_data_dir=app_data_dir or save_dir
    )
    async with Agent(config) as agent:
        response = await agent.chat(prompt)
        return _receipt("antigravity", session_id, await response.text())


# --- openhands ------------------------------------------------------------


async def openhands_fresh(prompt: str, workspace: str | None, model: str | None, approval: str) -> dict:
    if not model:
        raise RuntimeError("openhands SDK adapter requires an explicit model")
    import os

    from openhands.sdk import LLM, Agent, Conversation

    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        raise RuntimeError("openhands SDK route needs LLM_API_KEY in the server environment")
    llm = LLM(model=model, api_key=api_key)
    agent = Agent(llm=llm, tools=[])
    conversation = Conversation(agent=agent, workspace=workspace or "./workspace")
    conversation.send_message(prompt)
    conversation.run()
    return _receipt("openhands", getattr(conversation, "id", None), "(run completed; inspect workspace artifacts)")


EXECUTORS = {
    "claude": {"fresh": claude_fresh, "resume": claude_resume, "history": claude_history},
    "cursor": {"fresh": cursor_fresh, "resume": cursor_resume, "history": cursor_history},
    "copilot": {"fresh": copilot_fresh, "resume": copilot_resume, "history": None},
    "muse": {"fresh": muse_fresh, "resume": muse_resume, "history": None},
    "antigravity": {"fresh": antigravity_fresh, "resume": antigravity_resume, "history": None},
    "openhands": {"fresh": openhands_fresh, "resume": None, "history": None},
}
