"""
CLI module for claude-hooks package.
Provides commands to initialize hook templates and manage settings.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import click

HOOK_TEMPLATES = {
    "notification.py": '''"""
Notification hook example for claude-hooks.
This hook responds to various Claude Code notifications.
"""

from claude_hooks import run_hooks


def log_event(event):
    return None


if __name__ == "__main__":
    run_hooks(log_event)
''',
    "pre_tool_use.py": '''"""
Pre-tool-use hook example for claude-hooks.
This hook can validate and potentially block tool execution.
"""

from claude_hooks import run_hooks


def log_event(event):
    return event.undefined()


if __name__ == "__main__":
    run_hooks(log_event)
''',
    "post_tool_use.py": '''"""
Post-tool-use hook example for claude-hooks.
This hook processes tool results after execution.
"""

from claude_hooks import run_hooks


def log_event(event):
    return event.undefined()


if __name__ == "__main__":
    run_hooks(log_event)
''',
    "stop.py": '''"""
Stop hook example for claude-hooks.
This hook runs when Claude finishes a conversation.
"""

from claude_hooks import run_hooks


def log_event(event):
    return event.undefined()


if __name__ == "__main__":
    run_hooks(log_event)
''',
    "subagent_stop.py": '''"""
Subagent stop hook example for claude-hooks.
This hook runs when a Claude subagent stops.
"""

from claude_hooks import run_hooks


def log_event(event):
    return event.undefined()


if __name__ == "__main__":
    run_hooks(log_event)
''',
    "pre_compact.py": '''"""
Pre-compact hook example for claude-hooks.
This hook runs before conversation compaction.
"""

from claude_hooks import run_hooks


def log_event(event):
    return event.undefined()


if __name__ == "__main__":
    run_hooks(log_event)
''',
}


DEFAULT_SETTINGS = {
    "hooks": {
        "PreToolUse": [
            {
                "matcher": "",
                "hooks": [{"type": "command", "command": "uv run pre_tool_use.py"}],
            }
        ],
        "PostToolUse": [
            {
                "matcher": "",
                "hooks": [{"type": "command", "command": "uv run post_tool_use.py"}],
            }
        ],
        "Notification": [
            {
                "matcher": "",
                "hooks": [{"type": "command", "command": "uv run notification.py"}],
            }
        ],
        "Stop": [
            {"matcher": "", "hooks": [{"type": "command", "command": "uv run stop.py"}]}
        ],
        "SubagentStop": [
            {
                "matcher": "",
                "hooks": [{"type": "command", "command": "uv run subagent_stop.py"}],
            }
        ],
        "PreCompact": [
            {
                "matcher": "",
                "hooks": [{"type": "command", "command": "uv run pre_compact.py"}],
            }
        ],
    }
}


@click.group()
@click.version_option()
def main():
    """Claude Hooks CLI - Initialize and manage Claude Code hooks."""


def is_global_config_location(target_dir: Path) -> bool:
    """Check if target directory is a global configuration location."""
    global_locations = [
        Path.home() / ".claude",
        Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "claude",
    ]

    return any(target_dir.is_relative_to(loc) for loc in global_locations)


def get_hook_command_path(
    filename: str, target_dir: Path, force_global: bool | None = None
) -> str:
    """Generate appropriate command path based on context."""

    # Hook files are always in the hooks subdirectory
    hook_path = target_dir / "hooks" / filename

    # Use --project flag to ensure uv runs in hooks directory context
    # Override detection if explicitly specified for backwards compatibility
    if force_global is True:
        return f"uv run --project {target_dir}/hooks {hook_path}"
    elif force_global is False:
        # Calculate relative path from likely Claude execution directory to hooks directory
        hooks_dir = target_dir / "hooks"
        relative_hooks_dir = _calculate_relative_path_for_claude(target_dir, hooks_dir)
        return f"uv run --project {relative_hooks_dir} {relative_hooks_dir}/{filename}"

    # Auto-detect based on location
    if is_global_config_location(target_dir):
        # Global: use absolute path with project directory
        return f"uv run --project {target_dir}/hooks {hook_path}"
    else:
        # Project: use relative path from likely Claude execution directory to hooks directory
        hooks_dir = target_dir / "hooks"
        relative_hooks_dir = _calculate_relative_path_for_claude(target_dir, hooks_dir)
        return f"uv run --project {relative_hooks_dir} {relative_hooks_dir}/{filename}"


def _calculate_relative_path_for_claude(target_dir: Path, hooks_dir: Path) -> str:
    """Calculate the relative path from where Claude will likely be run to the hooks directory."""
    # If target_dir is named '.claude', Claude will likely be run from its parent
    if target_dir.name == ".claude":
        # Claude runs from parent directory, so path is .claude/hooks
        return ".claude/hooks"

    # If we're currently in a .claude directory, assume Claude runs from parent
    current_dir = Path.cwd()
    if current_dir.name == ".claude":
        # We're in .claude, Claude runs from parent, calculate relative path
        try:
            claude_run_dir = current_dir.parent
            relative_hooks_dir = hooks_dir.relative_to(claude_run_dir)
            return str(relative_hooks_dir)
        except ValueError:
            # Fallback to absolute path if calculation fails
            return str(hooks_dir)

    # Default case: calculate from current working directory
    try:
        relative_hooks_dir = hooks_dir.relative_to(Path.cwd())
        return str(relative_hooks_dir)
    except ValueError:
        # Fallback to absolute path if calculation fails
        return str(hooks_dir)


def merge_settings(
    existing_settings: dict[str, Any], new_hooks: dict[str, Any]
) -> dict[str, Any]:
    """Merge new hook configurations with existing settings."""
    result = existing_settings.copy()

    # Initialize hooks section if it doesn't exist
    if "hooks" not in result:
        result["hooks"] = {}

    # Merge each hook type
    for hook_type, hook_config in new_hooks.items():
        if hook_type not in result["hooks"]:
            result["hooks"][hook_type] = hook_config
        else:
            # Append to existing hooks for this type
            result["hooks"][hook_type].extend(hook_config)

    return result


@main.command()
@click.argument(
    "hook_types",
    nargs=-1,
    type=click.Choice(
        [
            "notification",
            "pre-tool-use",
            "post-tool-use",
            "stop",
            "subagent-stop",
            "pre-compact",
        ]
    ),
)
@click.option(
    "--dir",
    "-d",
    default=".",
    help="Directory to initialize (default: current directory)",
)
@click.option("--force", "-f", is_flag=True, help="Overwrite existing files")
@click.option(
    "--global",
    "force_global",
    is_flag=True,
    help="Force global config (absolute paths)",
)
@click.option(
    "--project",
    "force_project",
    is_flag=True,
    help="Force project config (relative paths)",
)
@click.option(
    "--local",
    "use_local",
    is_flag=True,
    help="Use settings.local.json instead of settings.json",
)
def init(
    hook_types: tuple[str, ...],
    dir: str,
    force: bool,
    force_global: bool,
    force_project: bool,
    use_local: bool,
):
    """Initialize a directory with Claude Code hook templates.

    HOOK_TYPES: Optional hook types to create (notification, pre-tool-use, post-tool-use, stop, subagent-stop).
    If none specified, creates all hook types.
    """
    target_dir = Path(dir).resolve()

    # Validate conflicting flags
    if force_global and force_project:
        click.echo("Error: Cannot use both --global and --project flags")
        return

    if not target_dir.exists():
        target_dir.mkdir(parents=True)
        click.echo(f"Created directory: {target_dir}")

    # Determine path resolution mode
    path_mode = None
    if force_global:
        path_mode = True
    elif force_project:
        path_mode = False

    # Determine which hooks to create
    requested_hooks = {}

    # Map hook type names to filenames
    hook_type_map = {
        "notification": "notification.py",
        "pre-tool-use": "pre_tool_use.py",
        "post-tool-use": "post_tool_use.py",
        "stop": "stop.py",
        "subagent-stop": "subagent_stop.py",
        "pre-compact": "pre_compact.py",
    }

    if hook_types:
        # Create only specified hooks
        for hook_type in hook_types:
            filename = hook_type_map[hook_type]
            requested_hooks[filename] = HOOK_TEMPLATES[filename]
    else:
        # If no specific hooks requested, create all
        requested_hooks = HOOK_TEMPLATES.copy()

    # Create hooks subdirectory
    hooks_dir = target_dir / "hooks"
    hooks_dir.mkdir(exist_ok=True)

    # Create pyproject.toml in hooks directory to ensure claude-hooks dependency is available
    pyproject_path = hooks_dir / "pyproject.toml"
    if not pyproject_path.exists():
        pyproject_content = """[project]
name = "claude-hooks-config"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "claude-hooks",
]
"""
        pyproject_path.write_text(pyproject_content)
        click.echo(f"Created: {pyproject_path}")
    else:
        click.echo("Skipping pyproject.toml (already exists)")

    # Create hook template files in hooks subdirectory
    for filename, content in requested_hooks.items():
        file_path = hooks_dir / filename

        if file_path.exists() and not force:
            click.echo(
                f"Skipping {filename} (already exists, use --force to overwrite)"
            )
            continue

        file_path.write_text(content)
        click.echo(f"Created: {file_path}")

    # Handle settings file - merge with existing if present
    settings_filename = "settings.local.json" if use_local else "settings.json"
    settings_path = target_dir / settings_filename

    # Build new settings based on requested hooks
    new_settings = {"hooks": {}}

    # Map hook files to settings entries using context-aware paths
    hook_to_settings = {
        "notification.py": "Notification",
        "pre_tool_use.py": "PreToolUse",
        "post_tool_use.py": "PostToolUse",
        "stop.py": "Stop",
        "subagent_stop.py": "SubagentStop",
        "pre_compact.py": "PreCompact",
    }

    for filename in requested_hooks.keys():
        if filename in hook_to_settings:
            hook_type = hook_to_settings[filename]
            command = get_hook_command_path(filename, target_dir, path_mode)
            new_settings["hooks"][hook_type] = [
                {"matcher": "", "hooks": [{"type": "command", "command": command}]}
            ]

    # Merge or create settings
    if settings_path.exists() and not force:
        try:
            with open(settings_path) as f:
                existing_settings = json.load(f)

            merged_settings = merge_settings(existing_settings, new_settings["hooks"])

            with open(settings_path, "w") as f:
                json.dump(merged_settings, f, indent=2)
            click.echo(f"Updated: {settings_path}")
        except (OSError, json.JSONDecodeError) as e:
            click.echo(f"Warning: Could not merge existing {settings_filename}: {e}")
            click.echo(f"Creating new {settings_filename}")
            with open(settings_path, "w") as f:
                json.dump(new_settings, f, indent=2)
            click.echo(f"Created: {settings_path}")
    else:
        with open(settings_path, "w") as f:
            json.dump(new_settings, f, indent=2)
        click.echo(f"Created: {settings_path}")

    hook_names = list(requested_hooks.keys())
    click.echo(
        f"\nInitialization complete! Created {len(hook_names)} hook(s): {', '.join(hook_names)}"
    )
    click.echo("\nNext steps:")
    click.echo("1. Edit the hook files to customize your logic")
    click.echo(f"2. Configure Claude Code to use {settings_filename}")
    click.echo("3. Test your hooks with Claude Code")
    click.echo(
        "\nNote: The logs/ directory will be created automatically when hooks run."
    )


@main.command()
@click.argument("hook_name", type=click.Choice(list(HOOK_TEMPLATES.keys())))
@click.option(
    "--dir",
    "-d",
    default=".",
    help="Directory to create hook in (default: current directory)",
)
@click.option("--force", "-f", is_flag=True, help="Overwrite existing file")
def create(hook_name: str, dir: str, force: bool):
    """Create a specific hook template file."""
    target_dir = Path(dir).resolve()
    file_path = target_dir / hook_name

    if file_path.exists() and not force:
        click.echo(f"File {file_path} already exists (use --force to overwrite)")
        return

    if not target_dir.exists():
        target_dir.mkdir(parents=True)
        click.echo(f"Created directory: {target_dir}")

    file_path.write_text(HOOK_TEMPLATES[hook_name])
    click.echo(f"Created: {file_path}")


def find_hook_file(event_name: str, search_dir: Path | None = None) -> Path | None:
    """Find the hook file for a given event type."""
    if search_dir is None:
        search_dir = Path.cwd()

    # Map event names to expected filenames
    event_to_file = {
        "notification": "notification.py",
        "pre-tool-use": "pre_tool_use.py",
        "post-tool-use": "post_tool_use.py",
        "stop": "stop.py",
        "subagent-stop": "subagent_stop.py",
        "pre-compact": "pre_compact.py",
    }

    expected_file = event_to_file.get(event_name)
    if not expected_file:
        return None

    hook_path = search_dir / expected_file
    return hook_path if hook_path.exists() else None


def create_test_payload(event_name: str, **kwargs) -> dict[str, Any]:
    """Create a test payload for the given event type."""
    base_payload = {
        "hook_event_name": "",
        "session_id": kwargs.get("session_id", "test-session-123"),
    }

    if event_name == "notification":
        base_payload.update(
            {
                "hook_event_name": "Notification",
                "message": kwargs.get("message", "Test notification"),
                "transcript_path": kwargs.get("transcript_path"),
            }
        )

    elif event_name == "pre-tool-use":
        base_payload.update(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": kwargs.get("tool", "Bash"),
                "tool_input": {
                    "command": kwargs.get("command", "echo 'test'"),
                    **{
                        k: v
                        for k, v in kwargs.items()
                        if k not in ["tool", "command", "session_id"]
                    },
                },
            }
        )

    elif event_name == "post-tool-use":
        base_payload.update(
            {
                "hook_event_name": "PostToolUse",
                "tool_name": kwargs.get("tool", "Bash"),
                "tool_input": {"command": kwargs.get("command", "echo 'test'")},
                "tool_response": {
                    "output": kwargs.get("output", "test output"),
                    "error": kwargs.get("error", ""),
                    **{
                        k: v
                        for k, v in kwargs.items()
                        if k not in ["tool", "command", "output", "error", "session_id"]
                    },
                },
            }
        )

    elif event_name == "stop":
        base_payload.update(
            {
                "hook_event_name": "Stop",
                "transcript_path": kwargs.get(
                    "transcript_path", "/tmp/test-transcript.txt"
                ),
            }
        )

    elif event_name == "subagent-stop":
        base_payload.update(
            {
                "hook_event_name": "SubagentStop",
                "transcript_path": kwargs.get(
                    "transcript_path", "/tmp/test-subagent-transcript.txt"
                ),
            }
        )

    elif event_name == "pre-compact":
        base_payload.update(
            {
                "hook_event_name": "PreCompact",
                "transcript_path": kwargs.get(
                    "transcript_path", "/tmp/test-transcript.txt"
                ),
            }
        )

    # Remove None values
    return {k: v for k, v in base_payload.items() if v is not None}


def run_hook_test(
    hook_file: Path, payload: dict[str, Any], verbose: bool = False
) -> tuple[int, str, str]:
    """Execute a hook file with the given payload."""
    try:
        payload_json = json.dumps(payload)

        result = subprocess.run(
            ["uv", "run", str(hook_file)],
            input=payload_json,
            text=True,
            capture_output=True,
            timeout=30,
        )
        return result.returncode, result.stdout, result.stderr

    except FileNotFoundError:
        return 1, "", "uv command not found - ensure uv is installed and in PATH"
    except subprocess.TimeoutExpired:
        return 1, "", "Hook execution timed out after 30 seconds"
    except Exception as e:
        return 1, "", f"Execution error: {e}"


@main.command()
@click.argument(
    "event_type",
    type=click.Choice(
        [
            "notification",
            "pre-tool-use",
            "post-tool-use",
            "stop",
            "subagent-stop",
            "pre-compact",
        ]
    ),
)
@click.option("--message", help="Message for notification events")
@click.option("--tool", help="Tool name for tool events (default: Bash)")
@click.option("--command", help="Command for tool events (default: echo 'test')")
@click.option("--output", help="Output for post-tool-use events")
@click.option("--error", help="Error output for post-tool-use events")
@click.option("--session-id", help="Session ID (default: test-session-123)")
@click.option("--transcript-path", help="Transcript path for stop events")
@click.option(
    "--payload", type=click.Path(exists=True), help="Custom JSON payload file"
)
@click.option(
    "--hook-file", type=click.Path(exists=True), help="Specific hook file to test"
)
@click.option(
    "--verbose", "-v", is_flag=True, help="Show detailed output including payload"
)
def test(
    event_type: str,
    message: str,
    tool: str,
    command: str,
    output: str,
    error: str,
    session_id: str,
    transcript_path: str,
    payload: str,
    hook_file: str,
    verbose: bool,
):
    """Test a hook with the specified event type and parameters."""

    # Find hook file
    if hook_file:
        hook_path = Path(hook_file)
    else:
        hook_path = find_hook_file(event_type)
        if not hook_path:
            click.echo(f"Error: No hook file found for {event_type} event")
            click.echo(f"Expected: {event_type.replace('-', '_')}.py")
            click.echo("Use --hook-file to specify a different file")
            sys.exit(1)

    # Create or load payload
    if payload:
        with open(payload) as f:
            test_payload = json.load(f)
    else:
        # Build payload from arguments
        kwargs = {}
        if message is not None:
            kwargs["message"] = message
        if tool is not None:
            kwargs["tool"] = tool
        if command is not None:
            kwargs["command"] = command
        if output is not None:
            kwargs["output"] = output
        if error is not None:
            kwargs["error"] = error
        if session_id is not None:
            kwargs["session_id"] = session_id
        if transcript_path is not None:
            kwargs["transcript_path"] = transcript_path

        test_payload = create_test_payload(event_type, **kwargs)

    # Show what we're testing
    click.echo(
        f"Testing {hook_path.name} with {test_payload['hook_event_name']} event..."
    )

    if verbose:
        click.echo("\nPayload sent:")
        click.echo(json.dumps(test_payload, indent=2))

    # Execute hook
    exit_code, stdout, stderr = run_hook_test(hook_path, test_payload, verbose)

    # Interpret results
    click.echo("\nResult: ", nl=False)
    if exit_code == 0:
        click.echo(
            click.style("✅ APPROVED/NEUTRAL", fg="green") + f" (exit {exit_code})"
        )
    elif exit_code == 2:
        click.echo(click.style("🚫 BLOCKED", fg="red") + f" (exit {exit_code})")
    else:
        click.echo(click.style("❌ ERROR", fg="red") + f" (exit {exit_code})")

    if stdout.strip():
        click.echo(f"\nStdout:\n{stdout}")

    if stderr.strip():
        click.echo(f"\nStderr:\n{stderr}")

    if exit_code == 0:
        click.echo(f"\n{click.style('Hook executed successfully!', fg='green')}")
    elif exit_code == 2:
        click.echo(f"\n{click.style('Hook blocked the operation.', fg='yellow')}")
    else:
        click.echo(f"\n{click.style('Hook execution failed.', fg='red')}")


if __name__ == "__main__":
    main()
