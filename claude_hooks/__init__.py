"""
claude-hooks: Python utilities for handling Claude Code hooks.

This package provides a framework for creating hooks that respond to various
Claude Code events (PreToolUse, PostToolUse, Notification, Stop, SubagentStop).
"""

from .hook_utils import (
    Decision,
    HookContext,
    HookResult,
    NotificationHook,
    PostToolUseHook,
    PreToolUseHook,
    StopHook,
    SubagentStopHook,
    approve,
    block,
    create_hook,
    neutral,
    run_hooks,
)

__version__ = "0.1.0"
__all__ = [
    "Decision",
    "HookContext",
    "HookResult",
    "NotificationHook",
    "PostToolUseHook",
    "PreToolUseHook",
    "StopHook",
    "SubagentStopHook",
    "approve",
    "block",
    "create_hook",
    "neutral",
    "run_hooks",
]
