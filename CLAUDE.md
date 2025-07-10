# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python utility library for handling Claude Code hooks. It provides a framework for creating hooks that respond to various Claude Code events (PreToolUse, PostToolUse, Notification, Stop, SubagentStop).

**Note**: The `examples/` folder contains development examples and is not part of the core library - it's only here to help with project development and testing.

## Commands

### Development Commands

#### Testing
- `uv run ruff check --fix . && uv run ruff format . && uv run pytest` - Full development check (lint + format + test)
- `uv run pytest` - Run tests only
- `uv run pytest -v` - Run tests with verbose output

**Important**: Always run ruff before pytest to avoid multiple test cycles due to formatting changes. Use `--fix` to auto-fix linting issues.

#### Code Quality
- `uv run ruff check .` - Lint code with Ruff
- `uv run ruff format .` - Format code with Ruff  
- `uv run ruff check --fix .` - Lint and auto-fix issues

#### Direct Module Testing
- `uv run python -m claude_hooks.hook_utils` - Test the hook_utils module directly

**See** `tests/README.md` for detailed testing strategy and best practices.

### CLI Commands (for testing during development)
- `uv run python -m claude_hooks.cli init` - Initialize all hook templates
- `uv run python -m claude_hooks.cli init notification` - Initialize only notification hook
- `uv run python -m claude_hooks.cli init pre-tool-use stop` - Initialize specific hooks
- `uv run python -m claude_hooks.cli create notification.py` - Create single hook file

**Development Note:** Use `uv run python -m claude_hooks.cli` instead of `uvx --from .` for development testing to avoid caching issues. The `uvx --from .` approach caches the built package, so code changes won't be reflected until you run `uv cache clean`.

### Final Testing (packaged version)
- `uv cache clean && uvx --from . claude-hooks init` - Test the packaged version (clears cache first)
- `uvx --from . claude-hooks init notification` - Test specific functionality in packaged version

**Note:** Only use `uvx --from .` for final testing of the packaged version before release. For development, use the direct module approach above.

### Running Development Examples
- `uv run examples/notification.py` - Run notification hook example (development only)
- `uv run examples/pre_tool_use.py` - Run pre-tool-use logging hook (development only)
- `uv run examples/post_tool_use.py` - Run post-tool-use hook (development only)
- `uv run examples/stop.py` - Run stop event hook (development only)
- `uv run examples/subagent_stop.py` - Run subagent stop hook (development only)

## Architecture

### Core Components

**`claude_hooks/hook_utils.py`** - The main framework providing:
- `EventContext` - Raw event context from Claude Code with event, tool, input, and response data
- `HookResult` - Result object with `Decision` enum (BLOCK, APPROVE, NEUTRAL)
- `run_hooks()` - Framework runner supporting single or multiple hooks with parallel execution
- Event-specific helper classes: `Notification`, `PreToolUse`, `PostToolUse`, `Stop`
- Convenience functions: `block()`, `approve()`, `neutral()`

### Hook Event System

Hooks receive JSON payloads from Claude Code via stdin and can return output in two ways:

### Simple Exit Code Output
- Exit 0: Success/approve (stderr shown to user in transcript mode)
- Exit 2: Block operation (stderr fed back to Claude)

### Advanced JSON Output
Hooks can return structured JSON to stdout for more sophisticated control:
- **Decision Control**: "approve", "block", or undefined (let Claude decide)
- **Continue Control**: Stop Claude from continuing with `"continue": false`
- **Output Suppression**: Hide stdout from transcript with `"suppressOutput": true`
- **Stop Reason**: Custom message when stopping Claude

Both upstream naming (`suppressOutput`, `stopReason`) and Python-style shortcuts (`suppress_output`, `stop_reason`) are supported.

### Hook Types

1. **PreToolUse** - Called before tool execution, can block tools
2. **PostToolUse** - Called after tool execution with response data
3. **Notification** - Called for various notifications
4. **Stop** - Called when Claude finishes
5. **SubagentStop** - Called when subagent stops

### Logging

All hooks automatically get rotating file logging in `logs/` directory with format `{event_name}.log` (e.g., `notification.log`, `pretooluse.log`). Logs are limited to 5MB with 5 backup files.

**Automatic Logging in Hook Functions:**
```python
def my_hook(event):
    event.logger.info("Hook executed successfully")
    event.logger.debug("Detailed debug information")
    event.logger.warning("Something needs attention")
    event.logger.error("An error occurred")
    return event.undefined()
```

**Controlling Log Level:**
Set the `CLAUDE_HOOKS_LOG_LEVEL` environment variable before starting Claude Code:
```bash
# Enable debug logging
export CLAUDE_HOOKS_LOG_LEVEL=DEBUG
claude --chat

# Or for a single session
CLAUDE_HOOKS_LOG_LEVEL=DEBUG claude --chat
```

Available levels: `DEBUG`, `INFO` (default), `WARNING`, `ERROR`, `CRITICAL`

## Development Philosophy

### Consistency and Simplicity
- **Use `uv` exclusively** - All commands, examples, and tooling assume `uv` is available
- **Avoid backwards compatibility** - Do not add fallbacks or support for multiple options unless explicitly required by design
- **Single path forward** - Choose one approach and stick with it consistently across the project
- **Explicit approval required** - Any deviation from this principle needs explicit design approval

### Tool Dependencies
- `uv` - Package management, script running, dependency installation
- `ruff` - Linting and formatting (no Black, no other formatters)
- `pytest` - Testing (no other test frameworks)

## Development Patterns

### Creating New Hooks

#### Simple Exit Code Hooks (Basic)

```python
from hook_utils import run_hooks

def my_hook(event):
    # Logging is automatic - just use event.logger
    event.logger.info("Processing hook event")
    
    # Your hook logic here
    return event.neutral()  # or event.block("reason") or event.approve("reason")

if __name__ == "__main__":
    run_hooks(my_hook)
```

#### Advanced JSON Output Hooks

```python
from hook_utils import run_hooks

def advanced_hook(event):
    event.logger.info(f"Processing {event.tool_name} tool")
    
    # Block with JSON output
    if event.tool_name == "Bash" and "rm -rf" in event.tool_input.get("command", ""):
        event.logger.warning("Blocking dangerous command")
        return event.block_json("Dangerous command blocked")
    
    # Approve with suppressed output (upstream naming)
    if event.tool_name == "Read":
        return event.approve_json("File access approved", suppressOutput=True)
    
    # Approve with suppressed output (Python-style shortcut)
    if event.tool_name == "Write":
        return event.approve_json("Write approved", suppress_output=True)
    
    # Stop Claude from continuing
    if "critical" in event.tool_input.get("file_path", ""):
        event.logger.error("Critical file access detected")
        return event.stop_claude("Critical file access requires manual review")
    
    return event.neutral_json()

if __name__ == "__main__":
    run_hooks(advanced_hook)
```

### Using Event-Specific Helper Classes

```python
from hook_utils import run_hooks

def my_pre_tool_hook(event):
    event.logger.info(f"Checking {event.tool_name} command")
    
    if event.tool_name == "Bash":
        command = event.input.get("command", "")
        if "dangerous" in command:
            event.logger.warning(f"Blocking dangerous command: {command}")
            return event.block("Dangerous command detected")
    
    return event.neutral()

if __name__ == "__main__":
    run_hooks(my_pre_tool_hook)
```

### Multiple Hook Support

The framework supports running multiple hooks in parallel - any hook returning `BLOCK` will immediately block the operation.

## Configuration

Hooks are configured in Claude Code settings JSON with commands like:
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command", 
            "command": "uv run /path/to/hook.py"
          }
        ]
      }
    ]
  }
}
```