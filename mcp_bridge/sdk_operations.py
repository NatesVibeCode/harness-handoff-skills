"""Fresh SDK Node implementations. Settings are selected by the calling Process.

No package installation, CLI fallback, retries, or permission-profile selection
happens here. SDK-owned subprocesses remain part of the selected SDK binding.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def native_runtime(name):
    root = os.environ.get('PRAXIS_SDK_RUNTIME_ROOT')
    if not root:
        return name
    selected = json.loads((Path(root) / 'runtime.json').read_text())['native'][name]
    runtime = Path(root).resolve(strict=True)
    executable = (runtime / selected).resolve(strict=True)
    if not executable.is_relative_to(runtime) or not executable.is_file():
        raise RuntimeError('SDK executable leaves captured material')
    return str(executable)


def completed(session_id, output):
    if not isinstance(session_id, str) or not session_id.strip():
        raise RuntimeError('SDK completed without a session identity')
    if not isinstance(output, str) or not output.strip():
        raise RuntimeError('SDK completed without assistant output')
    return {'session_id': session_id, 'output': output}


async def claude(request):
    from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
    options = ClaudeAgentOptions(cwd=request['workspace'], **request['settings'])
    terminal = None
    async for message in query(prompt=request['prompt'], options=options):
        if isinstance(message, ResultMessage):
            terminal = message
    if terminal is None:
        raise RuntimeError('Claude SDK ended without a terminal result')
    if terminal.is_error:
        detail = {key: getattr(terminal, key, None)
                  for key in ('session_id', 'subtype', 'result', 'errors')}
        raise RuntimeError('Claude SDK returned an error result: ' + json.dumps(detail))
    return completed(terminal.session_id, terminal.result)


async def cursor(request):
    from cursor_sdk import Agent, LocalAgentOptions
    settings = request['settings']
    with Agent.create(model=settings['model'], local=LocalAgentOptions(
        cwd=request['workspace'], auto_review=settings['auto_review'],
        sandbox_options=settings['sandbox_options'],
    )) as agent:
        result = agent.send(request['prompt']).wait()
        if result.status != 'finished':
            raise RuntimeError('Cursor SDK run did not finish successfully')
        return completed(agent.agent_id, result.result)


async def copilot(request):
    from copilot import CopilotClient
    from copilot.session import PermissionHandler, PermissionNoResult
    settings = request['settings']
    handler = PermissionHandler.approve_all if settings['permission'] == 'unattended' else lambda *_: PermissionNoResult()
    options = {}
    if os.environ.get('PRAXIS_SDK_RUNTIME_ROOT'):
        from copilot import RuntimeConnection
        options['connection'] = RuntimeConnection.for_stdio(path=native_runtime('copilot-runtime'))
    session_options = dict(model=settings['model'], working_directory=request['workspace'],
                           on_permission_request=handler)
    if 'provider' in settings:
        provider = dict(settings['provider'])
        credential_name = provider.pop('api_key_env')
        provider['api_key'] = os.environ[credential_name]
        session_options['provider'] = provider
        options['use_logged_in_user'] = False
    async with CopilotClient(**options) as client:
        async with await client.create_session(**session_options) as session:
            # send_and_wait waits for root idle, rejects errors, and returns the
            # final assistant message. A send acknowledgment cannot be success.
            response = await session.send_and_wait(request['prompt'])
            data = getattr(response, 'data', None)
            return completed(session.session_id, getattr(data, 'content', None))


async def muse(request):
    from muse_code import MuseClient, MuseClientSpawnOptions, SendUserTurnOptions, StartSessionOptions
    client = await MuseClient.spawn(MuseClientSpawnOptions(
        muse_bin=native_runtime('muse'), args=('serve',),
        capabilities={'experimentalApi': True},
        client_info={'name': 'harness_handoff', 'version': '1.0.0'},
    ))
    try:
        session = await client.start_session(StartSessionOptions(
            workspace_root=request['workspace'], require_permission_profile=True,
            **request['settings'],
        ))
        turn = await session.send_user_turn(SendUserTurnOptions(
            input=[{'type': 'text', 'text': request['prompt']}], composer_input=request['prompt'],
        ))
        chunks = []
        async for item in turn.items():
            value = item.get('item', item) if isinstance(item, dict) else getattr(item, 'item', item)
            get = value.get if isinstance(value, dict) else lambda key: getattr(value, key, None)
            if get('kind') == 'agentMessage' and get('status') == 'completed' and isinstance(get('text'), str):
                chunks.append(get('text'))
        outcome = await turn.completed
        if getattr(outcome, 'kind', None) != 'completed' or getattr(outcome, 'params', {}).get('terminal') != 'completed':
            raise RuntimeError('Muse SDK turn did not complete successfully')
        return completed(session.session_id, '\n'.join(chunks))
    finally:
        await client.close()


async def antigravity(request):
    from google.antigravity import Agent, LocalAgentConfig, policy
    settings = request['settings']
    policies = [policy.allow_all()] if settings['permission'] == 'unattended' else policy.confirm_run_command()
    config = LocalAgentConfig(
        model=settings['model'], workspaces=[request['workspace']], policies=policies,
        save_dir=settings['save_dir'], app_data_dir=settings['app_data_dir'],
    )
    async with Agent(config) as agent:
        response = await agent.chat(request['prompt'])
        output = await response.text()
        if response.stop_reason != 'UNSPECIFIED':
            raise RuntimeError('Antigravity SDK stopped before normal completion')
        return completed(agent.conversation_id, output)


async def openhands(request):
    import os
    from openhands.sdk import LLM, Agent, Conversation
    from openhands.sdk.event import MessageEvent
    settings = request['settings']
    api_key = os.environ.get('LLM_API_KEY')
    if not api_key:
        raise RuntimeError('OpenHands requires LLM_API_KEY')
    agent = Agent(llm=LLM(model=settings['model'], api_key=api_key), tools=settings['tools'])
    conversation = Conversation(agent=agent, workspace=request['workspace'])
    try:
        conversation.send_message(request['prompt'])
        conversation.run()
        if conversation.state.execution_status != 'finished':
            raise RuntimeError('OpenHands conversation did not finish successfully')
        chunks = []
        for event in conversation.state.events:
            if isinstance(event, MessageEvent) and event.source == 'agent':
                chunks.extend(part.text for part in event.llm_message.content if isinstance(getattr(part, 'text', None), str))
        return completed(str(conversation.id) if conversation.id is not None else None, '\n'.join(chunks))
    finally:
        conversation.close()


async def invoke(request):
    # The runner validates the declaration before importing any SDK.
    return await {'claude': claude, 'cursor': cursor, 'copilot': copilot,
                  'muse': muse, 'antigravity': antigravity, 'openhands': openhands}[request['harness']](request)
