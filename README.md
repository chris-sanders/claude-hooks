# claude-hooks

## Why This Exists

A portable Python framework for writing Claude Code hooks that reduces boilerplate and provides essential infrastructure:

- **Portable Python Hooks**: Write hooks in Python with proper dependency management via `uv`
- **Automatic Logging**: Built-in rotating log files for all hook executions
- **Dependency Support**: Use `uv` inline dependencies in your hooks when needed
- **Isolated Environment**: All hooks run in their own virtual environment
- **Framework Structure**: Provides the scaffolding to focus on hook logic, not infrastructure

## Installation vs Creation

This package provides two main operations:

**`uvx claude-hooks init`** - **Installs** hook templates and creates/updates `settings.json`
- Creates template files for all hook types (or specific ones with arguments)
- Creates a new `settings.json` file or **merges** hook configurations into existing one
- Existing `settings.json` content is preserved - only adds missing hook entries
- Templates provide the framework structure and automatic logging setup

**`uvx claude-hooks create <filename>`** - **Creates** a single hook file
- Generates one hook file without touching `settings.json`
- Provided for flexibility init is expected to be most frequently used

```bash
# Install all hook templates + settings.json
uvx claude-hooks init

# Install specific hook templates + settings.json  
uvx claude-hooks init notification pre-tool-use

# Create a single hook file (no settings.json changes)
uvx claude-hooks create notification.py

# See all available hook types and options
uvx claude-hooks init --help
uvx claude-hooks create --help
```

## Folder Structure

When you run `init`, this framework creates a specific folder structure:

```
.claude/
├── hooks/                    # All hook files go here
│   ├── notification.py
│   ├── pre_tool_use.py
│   ├── post_tool_use.py
│   ├── stop.py
│   ├── subagent_stop.py
│   ├── pre_compact.py
│   └── logs/                 # Auto-created when hooks run
│       ├── notification.log
│       ├── pretooluse.log
│       └── ...
└── settings.json             # Claude Code configuration
```

**For global hooks in `~/.claude/`:**
- Hook files: `~/.claude/hooks/*.py` 
- Log files: `~/.claude/hooks/logs/*.log`
- Settings: `~/.claude/settings.json`

**For project hooks:**
- Hook files: `./.claude/hooks/*.py`
- Log files: `./.claude/hooks/logs/*.log`
- Settings: `./.claude/settings.json`

## Global vs Project Hooks

You can install hooks at different levels to serve different purposes:

### Global Hooks (~/.claude/)
Install hooks in your global Claude directory for system-wide functionality:

```bash
cd ~/.claude
uvx claude-hooks init notification stop
```

**Use global hooks for:**
- **Universal logging**: Log all Claude Code activity across all projects
- **General notifications**: System-wide alerts and monitoring
- **Security policies**: Apply consistent security rules everywhere
- **Personal preferences**: Your own workflow and safety checks

### Project Hooks (./project-root/)
Install hooks in specific project directories for project-specific functionality:

```bash
cd /path/to/your/project
uvx claude-hooks init pre-tool-use post-tool-use
```

**Use project hooks for:**
- **Project-specific linting**: Run project's linter/formatter on file edits
- **Code quality**: Enforce project coding standards and conventions
- **CI/CD integration**: Validate changes before they're made
- **Team policies**: Shared rules that apply to all team members

### Why This Matters

**Global hooks** provide consistent behavior across all your Claude Code usage with centralized logging and personal preferences.

**Project hooks** can be shared with your team, ensuring consistent project-specific behavior for all team members.

Claude Code will use hooks from both locations when available, with project hooks taking precedence for overlapping functionality.

## Usage

### Simple Exit Code Hooks

```python
from claude_hooks import run_hooks

def security_hook(event):
    # PreToolUse hook - supports approve, block, undefined
    if event.tool_name == "Bash":
        command = event.tool_input.get("command", "")
        if "rm -rf" in command:
            return event.block("Dangerous command blocked")
        elif command.startswith("ls"):
            return event.approve("Safe listing command")
    
    return event.undefined()  # Let Claude Code decide

if __name__ == "__main__":
    run_hooks(security_hook)
```

### Advanced JSON Output Hooks

```python
from claude_hooks import run_hooks

def advanced_hook(event):
    if event.tool_name == "Edit":
        file_path = event.tool_input.get("file_path", "")
        
        # Block with JSON output
        if ".env" in file_path:
            return event.block_json("Sensitive file access blocked")
        
        # Approve with suppressed transcript output
        if file_path.endswith(".log"):
            return event.approve_json("Log access approved", suppress_output=True)
        
        # Stop Claude entirely for critical files
        if "critical" in file_path:
            return event.stop_claude("Manual review required for critical files")
    
    return event.undefined_json()

if __name__ == "__main__":
    run_hooks(advanced_hook)
```

### Parallel Hook Execution

Run multiple hooks in parallel - any hook returning `BLOCK` immediately blocks the operation:

```python
from claude_hooks import run_hooks

def security_hook(event):
    if "dangerous" in event.tool_input.get("command", ""):
        return event.block("Security violation")
    return event.undefined()

def audit_hook(event):
    # Log all tool usage
    print(f"Tool used: {event.tool_name}")
    return event.undefined()

def compliance_hook(event):
    if event.tool_name in ["Edit", "Write"]:
        file_path = event.tool_input.get("file_path", "")
        if ".env" in file_path:
            return event.block("Compliance: No env file modifications")
    return event.undefined()

if __name__ == "__main__":
    # All hooks run in parallel - first block wins
    run_hooks(security_hook, audit_hook, compliance_hook)
```

### Serial vs Parallel Execution

**Serial Execution**: Functions call each other in sequence
```python
def first_hook(event):
    # First security check
    if "rm -rf" in event.tool_input.get("command", ""):
        return event.block("Dangerous command")
    
    # Pass to next hook
    return second_hook(event)

def second_hook(event):
    # Second check after first passes
    if "sudo" in event.tool_input.get("command", ""):
        return event.block("Elevated privileges")
    
    return event.undefined()

if __name__ == "__main__":
    run_hooks(first_hook)  # Only register the first - it calls the second
```

**Parallel Execution**: Register multiple functions to run simultaneously
```python
def security_hook(event):
    if "rm -rf" in event.tool_input.get("command", ""):
        return event.block("Security violation")
    return event.undefined()

def compliance_hook(event):
    if "sudo" in event.tool_input.get("command", ""):
        return event.block("Compliance violation")
    return event.undefined()

if __name__ == "__main__":
    # Both hooks run in parallel - first to block wins
    run_hooks(security_hook, compliance_hook)
```

### Hook-Specific Constraints

Each hook type supports different decision types:

```python
# PreToolUse - supports all decisions
def pre_tool_hook(event):
    return event.approve("reason")  # ✅ Allowed
    return event.block("reason")    # ✅ Allowed  
    return event.undefined()        # ✅ Allowed

# PostToolUse - only block and undefined
def post_tool_hook(event):
    return event.approve("reason")  # ❌ Raises NotImplementedError
    return event.block("reason")    # ✅ Allowed
    return event.undefined()        # ✅ Allowed

# Notification - only undefined behavior  
def notification_hook(event):
    print(f"Received: {event.message}")
    return None  # ✅ Allowed (treated as undefined)
    # or return event.undefined()
```

## Hook Types

| Hook Type | Supports | Description |
|-----------|----------|-------------|
| **PreToolUse** | approve, block, undefined | Called before tool execution, can block or approve tools |
| **PostToolUse** | block, undefined | Called after tool execution with response data |
| **Notification** | undefined only | Called for various Claude Code notifications |
| **Stop** | block, undefined | Called when Claude finishes, can prevent stopping |
| **SubagentStop** | block, undefined | Called when Claude subagent stops |
| **PreCompact** | undefined only | Called before conversation compaction |

## Output Modes

### Simple Exit Codes
- **Exit 0**: Success/approve (stdout shown to user in transcript)
- **Exit 2**: Block operation (stderr fed back to Claude)

### Advanced JSON Output
- **Decision Control**: `"approve"`, `"block"`, or undefined
- **Continue Control**: Stop Claude with `"continue": false`
- **Output Suppression**: Hide from transcript with `"suppressOutput": true`
- **Stop Reason**: Custom message when stopping Claude

Both upstream naming (`suppressOutput`, `stopReason`) and Python-style shortcuts (`suppress_output`, `stop_reason`) are supported.

## Upstream Compatibility

This framework is fully compatible with Claude Code's official hook specification:

- **Hook Input Format**: [https://docs.anthropic.com/en/docs/claude-code/hooks#hook-input](https://docs.anthropic.com/en/docs/claude-code/hooks#hook-input)
- **Hook Output Format**: [https://docs.anthropic.com/en/docs/claude-code/hooks#hook-output](https://docs.anthropic.com/en/docs/claude-code/hooks#hook-output)

## Testing Hooks

After creating or editing hook files, test them to catch runtime errors before they affect Claude Code sessions:

```bash
# From your hooks directory (where pyproject.toml is located)
cd ~/.claude/hooks  # or cd ./hooks for project hooks

# Test hook types with sample data
uv run claude-hooks test notification --message "Test notification" -v
uv run claude-hooks test pre-tool-use --tool "Bash" --command "ls -la" -v  
uv run claude-hooks test post-tool-use --tool "Read" --output "file contents" -v
uv run claude-hooks test stop --session-id "test-123" -v

# See all test options
uv run claude-hooks test --help
```

**Important**: Always run tests from the hooks directory after editing any hook files. Failed hooks show detailed error messages and stack traces to help debug issues.

## Convenience Features

This framework adds developer-friendly features on top of the upstream specification:

### Event Helper Classes
- **Type-safe access**: `event.tool_name`, `event.tool_input`, `event.tool_response`  
- **Convenience properties**: `event.session_id`, `event.transcript_path`
- **Validation**: Automatic validation of required fields per hook type

### Decision Helper Methods
- **Simple**: `event.block("reason")`, `event.approve("reason")`, `event.undefined()`
- **JSON**: `event.block_json()`, `event.approve_json()`, `event.undefined_json()`, `event.stop_claude()`
- **Global**: `block()`, `approve()`, `undefined()`, `block_json()`, etc.

### Automatic Logging
All hook functions get automatic logging with no imports required:

```python
def my_hook(event):
    event.logger.info("Hook executed successfully")
    event.logger.debug("Detailed debug information")  
    event.logger.warning("Something needs attention")
    event.logger.error("An error occurred")
    return event.undefined()
```

**Log Location**: `logs/{event_name}.log` (e.g., `notification.log`, `pretooluse.log`)  
**Log Format**: `timestamp [function_name] LEVEL: message`

**Control Log Level**: Set environment variable before starting Claude Code:
```bash
export CLAUDE_HOOKS_LOG_LEVEL=DEBUG  # DEBUG, INFO (default), WARNING, ERROR, CRITICAL
claude
```

## License

Apache-2.0
