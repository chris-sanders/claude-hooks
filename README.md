# claude-hooks

Python utilities for handling Claude Code hooks with a framework for creating event-driven hooks.

## Features

- Framework for creating Claude Code hooks that respond to various events
- Support for PreToolUse, PostToolUse, Notification, Stop, and SubagentStop events
- Built-in logging with automatic rotation
- CLI tool for initializing hook templates and managing settings
- Easy-to-use event classes with utility methods

## Installation

```bash
pip install claude-hooks
```

## Quick Start

### Initialize a new project

```bash
claude-hooks init
```

This creates template hook files and a `settings.json` file ready for use with Claude Code.

### Create a specific hook

```bash
claude-hooks create pre_tool_use.py
```

## Usage

### Basic Hook Example

```python
from claude_hooks import HookContext, run_hooks, neutral, block

def my_hook(ctx: HookContext):
    # Your hook logic here
    if some_condition:
        return block("Reason for blocking")
    return neutral()

if __name__ == "__main__":
    run_hooks(my_hook)
```

### Using Event Classes

```python
from claude_hooks import PreToolUse, HookContext, run_hooks, neutral

def pre_tool_hook(ctx: HookContext):
    event = PreToolUse(ctx)
    
    if event.tool_name == "Bash":
        command = event.get_input("command")
        # Validate command logic
    
    return neutral()

if __name__ == "__main__":
    run_hooks(pre_tool_hook)
```

## Hook Types

- **PreToolUse**: Called before tool execution, can block tools
- **PostToolUse**: Called after tool execution with response data  
- **Notification**: Called for various notifications
- **Stop**: Called when Claude finishes
- **SubagentStop**: Called when subagent stops

## License

Apache-2.0