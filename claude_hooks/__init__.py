"""
claude-hooks: Python utilities for handling Claude Code hooks.

This package provides a framework for creating hooks that respond to various
Claude Code events (PreToolUse, PostToolUse, Notification, Stop, SubagentStop).
"""

from .hook_utils import (
    Decision,
    EventContext,
    HookResult,
    Notification,
    PostToolUse,
    PreToolUse,
    Stop,
    SubagentStop,
    approve,
    block,
    create_event,
    run_hooks,
    undefined,
)

__version__ = "0.1.0"
__all__ = [
    "Decision",
    "EventContext",
    "HookResult",
    "Notification",
    "PostToolUse",
    "PreToolUse",
    "Stop",
    "SubagentStop",
    "approve",
    "block",
    "create_event",
    "run_hooks",
    "undefined",
]
