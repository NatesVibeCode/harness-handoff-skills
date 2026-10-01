"""Resolve native inputs for legacy behavioral tests; production has no raw executor API."""
from pathlib import Path
from mcp_bridge import cli_executor, control, launch_plan, model_settings


def make_cli_plan(entry, *, prompt, workspace=None, model=None, extra_argv=None,
                  extra_at=0, model_capabilities=None, settings_control=None):
    # Old isolated mocks used /w without creating it. Resolution now requires
    # a real directory, so those tests use their selected checkout cwd instead.
    workspace = str(Path.cwd()) if workspace == "/w" else workspace
    native = dict(settings_control["requested_settings"] if settings_control else {"model": model})
    if entry["skill"] == "codex-harness-handoff" and not settings_control:
        native.update(model_settings.launch_receipt(extra_argv or [], "")["requested"])
    requested = {"model": native.get("model"), "reasoning_effort": native.get("reasoning_effort"),
                 "approval": "default", "use": "cli"}
    context = None
    if control.CONFIG_ENV in __import__('os').environ:
        context = control.access_gate(entry["skill"].removesuffix("-harness-handoff"), workspace,
            action="project", profile=(settings_control or {}).get("profile"), controls=requested)
    return launch_plan.resolve(entry, route="cli", prompt=prompt, workspace=workspace,
        requested=requested, native_settings=native, extra_argv=extra_argv or [], extra_at=extra_at,
        model_capabilities=model_capabilities, profile=settings_control, context=context)


def execute_cli(entry, **kwargs):
    plan = make_cli_plan(entry, **kwargs)
    try:
        return cli_executor.run_cli(plan, authorization=control.authorize_launch_plan(plan))
    finally:
        plan.cleanup()
