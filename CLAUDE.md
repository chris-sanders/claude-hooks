# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python utility library for handling Claude Code hooks. It provides a framework for creating hooks that respond to various Claude Code events (PreToolUse, PostToolUse, Notification, Stop, SubagentStop).

**Note**: The `examples/` folder contains development examples and is not part of the core library - it's only here to help with project development and testing.

## Commands

### Development Commands
- `uv run pytest` - Run tests
- `uv run black .` - Format code with Black
- `uv run python -m src.hook_utils` - Test the hook_utils module directly

### Running Development Examples
- `uv run examples/notification.py` - Run notification hook example (development only)
- `uv run examples/pre_tool_use.py` - Run pre-tool-use logging hook (development only)
- `uv run examples/post_tool_use.py` - Run post-tool-use hook (development only)
- `uv run examples/stop.py` - Run stop event hook (development only)
- `uv run examples/subagent_stop.py` - Run subagent stop hook (development only)

## Architecture

### Core Components

**`src/hook_utils.py`** - The main framework providing:
- `HookContext` - Raw hook context from Claude Code with event, tool, input, and response data
- `HookResult` - Result object with `Decision` enum (BLOCK, APPROVE, NEUTRAL)
- `run_hooks()` - Framework runner supporting single or multiple hooks with parallel execution
- Event-specific hook classes: `NotificationHook`, `PreToolUseHook`, `PostToolUseHook`, `StopHook`
- Convenience functions: `block()`, `approve()`, `neutral()`

### Hook Event System

Hooks receive JSON payloads from Claude Code via stdin and must exit with specific codes:
- Exit 0: Success/approve (stderr shown to user in transcript mode)
- Exit 2: Block operation (stderr fed back to Claude)

### Hook Types

1. **PreToolUse** - Called before tool execution, can block tools
2. **PostToolUse** - Called after tool execution with response data
3. **Notification** - Called for various notifications
4. **Stop** - Called when Claude finishes
5. **SubagentStop** - Called when subagent stops

### Logging

All hooks automatically get rotating file logging in `logs/` directory with format `{event}_{hook_name}_hooks.log`. Logs are limited to 10MB with 5 backup files.

## Development Patterns

### Creating New Hooks

```python
from hook_utils import HookContext, run_hooks, neutral, block

def my_hook(ctx: HookContext):
    # Your hook logic here
    return neutral()  # or block("reason") or approve("reason")

if __name__ == "__main__":
    run_hooks(my_hook)
```

### Using Event-Specific Hook Classes

```python
from hook_utils import PreToolUseHook, create_hook

def my_pre_tool_hook(ctx: HookContext):
    hook = PreToolUseHook(ctx)
    # or use: hook = create_hook(ctx)
    
    if hook.tool_name == "Bash":
        command = hook.get_input("command")
        # Validate command logic
    
    return neutral()
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