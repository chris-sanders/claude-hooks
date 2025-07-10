#!/usr/bin/env python3
"""
hook_utils.py - Shared utilities for Claude Code hooks

Provides EventContext, HookResult, JsonResult, and run_hooks() for standardized hook development.

## Basic Usage (Simple Exit Codes)

```python
from hook_utils import run_hooks

def my_hook(event):
    if event.tool_name == "Bash" and "dangerous" in event.tool_input.get("command", ""):
        return event.block("Dangerous command detected")
    return event.undefined()

if __name__ == "__main__":
    run_hooks(my_hook)
```

## Advanced Usage (JSON Output)

```python
from hook_utils import run_hooks

def advanced_hook(event):
    # Block with JSON output
    if event.tool_name == "Bash" and "rm -rf" in event.tool_input.get("command", ""):
        return event.block_json("Dangerous command blocked")

    # Approve with suppressed output
    if event.tool_name == "Read" and event.tool_input.get("file_path", "").endswith(".log"):
        return event.approve_json("Log file access approved", suppress_output=True)

    # Stop Claude from continuing
    if event.tool_name == "Write" and "critical_config" in event.tool_input.get("file_path", ""):
        return event.stop_claude("Critical configuration change requires manual review")

    return event.undefined_json()

if __name__ == "__main__":
    run_hooks(advanced_hook)
```

## Both Upstream and Python-style naming supported:

```python
# Upstream naming (matches Claude Code docs exactly)
return event.block_json("reason", stopReason="Manual review required")

# Python-style shortcuts (more pythonic)
return event.block_json("reason", stop_reason="Manual review required")
```
"""

import inspect
import json
import logging
import logging.handlers
import os
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

# ============================================================================
# CORE FRAMEWORK CLASSES
# ============================================================================


class Decision(Enum):
    """Hook decision options - matches upstream exactly"""

    BLOCK = "block"
    APPROVE = "approve"
    # No NEUTRAL - use None for undefined (let Claude Code decide)


@dataclass
class EventContext:
    """Raw event context from Claude Code. Contains the raw JSON payload data."""

    event: str
    tool: str | None
    input: dict[str, Any]
    response: dict[str, Any] | None = None
    full_payload: dict[str, Any] = None

    @classmethod
    def from_stdin(cls) -> "EventContext":
        """Create context from stdin JSON payload"""
        try:
            # Read stdin data
            stdin_data = sys.stdin.read()

            # Debug logging using standard log levels
            logging.debug(f"Hook called with stdin data: {stdin_data}")
            logging.debug(f"Stdin length: {len(stdin_data)} characters")

            payload = json.loads(stdin_data)
            logging.debug(f"Parsed payload: {payload}")

            # Validate required fields
            event = payload.get("hook_event_name")
            if not event:
                logging.error("Missing required field: hook_event_name")
                sys.exit(1)

            result = cls(
                event=event,
                tool=payload.get("tool_name"),  # None if not present
                input=payload.get("tool_input", {}),  # tool_input for tool events
                response=payload.get("tool_response"),
                full_payload=payload,
            )

            logging.debug(
                f"Created context - event: {result.event}, tool: {result.tool}, input: {result.input}"
            )
            return result

        except json.JSONDecodeError as e:
            logging.error(f"JSON parsing error: {e}")
            sys.exit(1)


class HookResult:
    """Internal result object. Use block(), approve(), or neutral() instead."""

    def __init__(self, decision: Decision | None, reason: str = ""):
        self.decision = decision
        self.reason = reason

    def exit_with_result(self):
        """Handle the exit logic based to Claude Code exit code specification"""
        if self.decision == Decision.BLOCK:
            # Exit 2: Blocking error. stderr is fed back to Claude
            if self.reason:
                print(self.reason, file=sys.stderr)
            sys.exit(2)
        elif self.decision == Decision.APPROVE:
            # Exit 0: Success. stdout shown to user in transcript mode
            if self.reason:
                print(self.reason)  # stdout
            sys.exit(0)
        else:
            # Undefined (None) - Exit 0: Let Claude Code decide (no output)
            sys.exit(0)


@dataclass
class JsonResult:
    """Advanced JSON output result with upstream naming and Python shortcuts"""

    decision: Decision | None = None
    reason: str = ""
    continue_: bool = True  # 'continue' is Python keyword, use continue_
    stopReason: str = ""  # Upstream naming  # noqa: N815
    suppressOutput: bool = False  # Upstream naming  # noqa: N815

    def __init__(
        self,
        decision: Decision | None = None,
        reason: str = "",
        continue_: bool = True,
        stopReason: str = "",  # noqa: N803
        suppressOutput: bool = False,  # noqa: N803
        # Python-style shortcuts for convenience
        stop_reason: str = "",
        suppress_output: bool = False,
    ):
        self.decision = decision
        self.reason = reason
        self.continue_ = continue_
        # Use shortcuts if provided, otherwise use upstream naming
        self.stopReason = stop_reason if stop_reason else stopReason
        self.suppressOutput = suppress_output if suppress_output else suppressOutput

    def exit_with_result(self):
        """Output JSON to stdout and exit with code 0"""
        output = {}

        # Add decision and reason if specified
        if self.decision is not None:
            output["decision"] = self.decision.value
            if self.reason:
                output["reason"] = self.reason

        # Add continue control
        if not self.continue_:
            output["continue"] = False
            if self.stopReason:
                output["stopReason"] = self.stopReason

        # Add output suppression
        if self.suppressOutput:
            output["suppressOutput"] = True

        print(json.dumps(output))
        sys.exit(0)


# ============================================================================
# LOGGING UTILITIES
# ============================================================================


def setup_logging(hook_name: str, event_name: str | None = None) -> None:
    """Setup logging for a specific hook"""

    # Create logs directory relative to the hook file location
    # Walk up the call stack to find the hook script file
    hook_script_path = None

    # Look through the call stack to find the main script file
    for frame_info in inspect.stack():
        frame_path = Path(frame_info.filename)
        # Skip our own module files and Python built-ins
        if (
            frame_path.name != "hook_utils.py"
            and not frame_path.name.startswith("<")
            and frame_path.suffix == ".py"
        ):
            hook_script_path = frame_path
            break

    # Error if we can't determine hook location - this shouldn't happen
    if not hook_script_path:
        print(
            "Error: Unable to determine hook script location for logging setup",
            file=sys.stderr,
        )
        sys.exit(1)

    log_dir = hook_script_path.parent / "logs"

    log_dir.mkdir(parents=True, exist_ok=True)

    # Clear any existing handlers to avoid duplicates
    logging.getLogger().handlers.clear()

    # Create log filename based on event name
    if event_name:
        log_filename = f"{event_name.lower()}.log"
    else:
        log_filename = f"{hook_name}.log"

    # Create rotating file handler (10MB max, keep 5 files)
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / log_filename,
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=5,
        encoding="utf-8",
    )

    # Create stream handler
    stream_handler = logging.StreamHandler(sys.stderr)

    # Create formatter that uses the logger name instead of fixed hook_name
    formatter = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)

    # Determine logging level from environment variable
    log_level = os.getenv("CLAUDE_HOOKS_LOG_LEVEL", "INFO").upper()
    try:
        level = getattr(logging, log_level)
    except AttributeError:
        level = logging.INFO  # Fallback to INFO for invalid values

    logging.basicConfig(
        level=level,
        handlers=[file_handler, stream_handler],
        force=True,  # Clear any existing handlers
    )

    # Note: Removed manual flush override to avoid shell spawn issues


# ============================================================================
# COMMAND UTILITIES
# ============================================================================


def run_command(command: list, timeout: int = 30) -> tuple[bool, str, str]:
    """
    Run a shell command safely

    Returns:
        (success, stdout, stderr)
    """
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", f"Command timed out after {timeout}s"
    except Exception as e:
        return False, "", str(e)


# ============================================================================
# FRAMEWORK RUNNER
# ============================================================================


def run_hooks(*hooks) -> None:
    """
    Run single or multiple hook functions with parallel execution support

    Args:
        *hooks: Hook functions: (event: BaseEvent) -> HookResult
    """
    # Convert to list for unified handling
    hooks = list(hooks)

    # Validate input
    if not hooks:
        logging.error("No hooks provided")
        sys.exit(1)

    # Introspect hook name from first hook
    first_hook = hooks[0]
    if hasattr(first_hook, "__name__"):
        hook_name = first_hook.__name__
    elif hasattr(first_hook, "__class__"):
        hook_name = first_hook.__class__.__name__
    else:
        hook_name = "unknown_hook"

    import concurrent.futures

    try:
        ctx = EventContext.from_stdin()
        event = create_event(ctx)
        setup_logging(hook_name, ctx.event)
        framework_logger = logging.getLogger("hook_utils")
        framework_logger.info(
            f"Running {len(hooks)} hooks for {ctx.event} on {ctx.tool}"
        )
        framework_logger.info(f"Raw payload: {json.dumps(ctx.full_payload, indent=2)}")

        # Run hooks in parallel
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {}

            for i, hook in enumerate(hooks):
                # Determine hook name
                if hasattr(hook, "__name__"):
                    individual_name = hook.__name__
                elif hasattr(hook, "__class__"):
                    individual_name = hook.__class__.__name__
                else:
                    individual_name = f"hook_{i}"

                # Submit hook for execution
                futures[executor.submit(_execute_hook, hook, event)] = individual_name

            # Collect results - any block wins
            for future in concurrent.futures.as_completed(futures):
                hook_name_individual = futures[future]
                try:
                    result = future.result()
                    # Handle None return (treat as undefined)
                    if result is None:
                        result = HookResult(None)

                    if not isinstance(result, HookResult | JsonResult):
                        logging.error(
                            f"Hook {hook_name_individual} returned invalid result type"
                        )
                        print(
                            f"Invalid result from {hook_name_individual}",
                            file=sys.stderr,
                        )
                        sys.exit(2)

                    # Handle JsonResult - always exits immediately
                    if isinstance(result, JsonResult):
                        if result.decision == Decision.BLOCK:
                            framework_logger.info(
                                f"Hook {hook_name_individual} blocked operation (JSON)"
                            )
                        elif result.decision == Decision.APPROVE:
                            framework_logger.info(
                                f"Hook {hook_name_individual} approved operation (JSON)"
                            )
                        else:
                            framework_logger.info(
                                f"Hook {hook_name_individual} returned JSON result"
                            )
                        result.exit_with_result()

                    # Handle HookResult - traditional behavior
                    elif isinstance(result, HookResult):
                        if result.decision == Decision.BLOCK:
                            framework_logger.info(
                                f"Hook {hook_name_individual} blocked operation"
                            )
                            result.exit_with_result()
                        elif result.decision == Decision.APPROVE:
                            framework_logger.info(
                                f"Hook {hook_name_individual} approved operation"
                            )
                            result.exit_with_result()
                        # If decision is None (undefined), continue to next hook

                except Exception as e:
                    logging.error(f"Hook {hook_name_individual} failed: {e}")
                    print(f"{hook_name_individual} failed: {e}", file=sys.stderr)
                    sys.exit(2)

        # All hooks passed
        framework_logger.info(f"All {len(hooks)} hooks completed successfully")
        sys.exit(0)

    except KeyboardInterrupt:
        framework_logger.info("Hooks interrupted by user")
        sys.exit(1)
    except Exception as e:
        framework_logger.error(f"Hooks failed: {e}")
        sys.exit(1)


def _execute_hook(hook, event: "BaseEvent") -> HookResult | JsonResult:
    """Execute a single hook function"""
    try:
        if not callable(hook):
            raise ValueError(f"Hook must be a callable function, got {type(hook)}")

        # Set up logger for this hook function
        hook_name = hook.__name__ if hasattr(hook, "__name__") else "unknown_hook"
        event._logger = logging.getLogger(hook_name)

        return hook(event)
    except Exception as e:
        raise Exception(f"Hook execution failed: {e}") from e


# ============================================================================
# CLASS-BASED EVENT FRAMEWORK
# ============================================================================


class BaseEvent:
    """Base class for event-specific helpers with validation and field access."""

    def __init__(self, ctx: EventContext):
        self._ctx = ctx
        self._logger = None  # Will be set by _execute_hook
        self.validate_required_fields()

    @property
    def logger(self):
        """Logger for this hook function"""
        if self._logger is None:
            # Fallback logger if not set by framework
            self._logger = logging.getLogger("unknown_hook")
        return self._logger

    def validate_required_fields(self):
        """Override in subclasses to validate event-specific requirements"""
        if not self._ctx.event:
            raise ValueError("Missing hook_event_name")

    def _validate_event(self, expected_event: str):
        """Helper to validate event type"""
        if self._ctx.event != expected_event:
            raise ValueError(f"Expected {expected_event} event, got {self._ctx.event}")

    def _validate_tool_present(self):
        """Helper to validate tool is present"""
        if not self._ctx.tool:
            raise ValueError(f"{self._ctx.event} event missing tool_name")

    def get_field(self, *keys, default=None):
        """
        Safely get nested field from full payload

        Args:
            *keys: Field path (e.g., "session_id" or nested like "config", "timeout")
            default: Default value if not found

        Returns:
            Field value or default
        """
        current = self._ctx.full_payload
        for key in keys:
            if not isinstance(current, dict) or key not in current:
                return default
            current = current[key]
        return current

    def block(self, reason: str) -> "HookResult":
        """Block operation with reason"""
        return HookResult(Decision.BLOCK, reason)

    def approve(self, reason: str = "") -> "HookResult":
        """Approve operation with optional reason"""
        return HookResult(Decision.APPROVE, reason)

    def undefined(self) -> "HookResult":
        """Let Claude Code decide (default behavior)"""
        return HookResult(None)

    # JSON output methods - upstream compatible with Python shortcuts
    def block_json(
        self,
        reason: str,
        continue_: bool = True,
        stopReason: str = "",  # noqa: N803
        stop_reason: str = "",
    ) -> "JsonResult":
        """Block with JSON output"""
        return JsonResult(
            decision=Decision.BLOCK,
            reason=reason,
            continue_=continue_,
            stopReason=stopReason,
            stop_reason=stop_reason,
        )

    def approve_json(
        self,
        reason: str = "",
        suppressOutput: bool = False,  # noqa: N803
        suppress_output: bool = False,
    ) -> "JsonResult":
        """Approve with JSON output"""
        return JsonResult(
            decision=Decision.APPROVE,
            reason=reason,
            suppressOutput=suppressOutput,
            suppress_output=suppress_output,
        )

    def undefined_json(
        self,
        suppressOutput: bool = False,  # noqa: N803
        suppress_output: bool = False,
    ) -> "JsonResult":
        """Let Claude Code decide with JSON output"""
        return JsonResult(
            decision=None,
            suppressOutput=suppressOutput,
            suppress_output=suppress_output,
        )

    def stop_claude(
        self,
        stopReason: str = "",  # noqa: N803
        stop_reason: str = "",
    ) -> "JsonResult":
        """Stop Claude from continuing"""
        return JsonResult(
            continue_=False,
            stopReason=stopReason,
            stop_reason=stop_reason,
        )

    @property
    def hook_event_name(self) -> str:
        """The upstream hook event name (e.g., 'PreToolUse', 'PostToolUse')"""
        return self._ctx.event

    @property
    def name(self) -> str:
        """Shortcut for hook_event_name"""
        return self._ctx.event

    @property
    def transcript_path(self) -> str | None:
        """Path to the conversation transcript"""
        return self.get_field("transcript_path")

    @property
    def session_id(self) -> str | None:
        """Session ID for this event"""
        return self.get_field("session_id")


class Notification(BaseEvent):
    """Helper for Notification events - only supports undefined behavior"""

    def validate_required_fields(self):
        super().validate_required_fields()
        self._validate_event("Notification")

    @property
    def message(self) -> str | None:
        return self.get_field("message")

    @property
    def has_message(self) -> bool:
        return bool(self.message)

    # Override to only allow undefined - Notification hooks don't support decisions
    def block(self, reason: str) -> "HookResult":
        """Not supported for Notification hooks"""
        raise NotImplementedError(
            "Notification hooks don't support block() - use undefined() or just return None"
        )

    def approve(self, reason: str = "") -> "HookResult":
        """Not supported for Notification hooks"""
        raise NotImplementedError(
            "Notification hooks don't support approve() - use undefined() or just return None"
        )

    def block_json(self, reason: str, **kwargs) -> "JsonResult":
        """Not supported for Notification hooks"""
        raise NotImplementedError(
            "Notification hooks don't support block_json() - use undefined_json() or just return None"
        )

    def approve_json(self, reason: str = "", **kwargs) -> "JsonResult":
        """Not supported for Notification hooks"""
        raise NotImplementedError(
            "Notification hooks don't support approve_json() - use undefined_json() or just return None"
        )


class ToolEvent(BaseEvent):
    """Base class for tool-related events (PreToolUse, PostToolUse)"""

    def validate_required_fields(self):
        super().validate_required_fields()
        self._validate_tool_present()

    @property
    def tool_name(self) -> str:
        return self._ctx.tool

    @property
    def tool_input(self) -> dict[str, Any]:
        """Tool input parameters"""
        return self.get_field("tool_input", default={})


class PreToolUse(ToolEvent):
    """Helper for PreToolUse events (before tool execution)"""

    def validate_required_fields(self):
        super().validate_required_fields()
        self._validate_event("PreToolUse")


class PostToolUse(ToolEvent):
    """Helper for PostToolUse events (after tool execution) - supports block, undefined"""

    def validate_required_fields(self):
        super().validate_required_fields()
        self._validate_event("PostToolUse")
        if self._ctx.response is None:
            raise ValueError("PostToolUse event missing tool_response")

    @property
    def tool_response(self) -> dict[str, Any]:
        """Tool response data"""
        return self._ctx.response

    # Override to only allow block and undefined - PostToolUse doesn't support approve
    def approve(self, reason: str = "") -> "HookResult":
        """Not supported for PostToolUse hooks"""
        raise NotImplementedError(
            "PostToolUse hooks don't support approve() - only block() and undefined()"
        )

    def approve_json(self, reason: str = "", **kwargs) -> "JsonResult":
        """Not supported for PostToolUse hooks"""
        raise NotImplementedError(
            "PostToolUse hooks don't support approve_json() - only block_json() and undefined()"
        )


class Stop(BaseEvent):
    """Helper for Stop events (when Claude finishes) - supports block, undefined"""

    def validate_required_fields(self):
        super().validate_required_fields()
        self._validate_event("Stop")

    @property
    def stop_hook_active(self) -> bool:
        """True when Claude Code is already continuing as a result of a stop hook"""
        return self.get_field("stop_hook_active", default=False)

    # Override to only allow block and undefined - Stop doesn't support approve
    def approve(self, reason: str = "") -> "HookResult":
        """Not supported for Stop hooks"""
        raise NotImplementedError(
            "Stop hooks don't support approve() - only block() and undefined()"
        )

    def approve_json(self, reason: str = "", **kwargs) -> "JsonResult":
        """Not supported for Stop hooks"""
        raise NotImplementedError(
            "Stop hooks don't support approve_json() - only block_json() and undefined()"
        )


class SubagentStop(BaseEvent):
    """Helper for SubagentStop events (when Claude subagent stops) - supports block, undefined"""

    def validate_required_fields(self):
        super().validate_required_fields()
        self._validate_event("SubagentStop")

    @property
    def stop_hook_active(self) -> bool:
        """True when Claude Code is already continuing as a result of a stop hook"""
        return self.get_field("stop_hook_active", default=False)

    # Override to only allow block and undefined - SubagentStop doesn't support approve
    def approve(self, reason: str = "") -> "HookResult":
        """Not supported for SubagentStop hooks"""
        raise NotImplementedError(
            "SubagentStop hooks don't support approve() - only block() and undefined()"
        )

    def approve_json(self, reason: str = "", **kwargs) -> "JsonResult":
        """Not supported for SubagentStop hooks"""
        raise NotImplementedError(
            "SubagentStop hooks don't support approve_json() - only block_json() and undefined()"
        )


class PreCompact(BaseEvent):
    """Helper for PreCompact events (before conversation compaction) - only supports undefined behavior"""

    def validate_required_fields(self):
        super().validate_required_fields()
        self._validate_event("PreCompact")

    @property
    def trigger(self) -> str | None:
        """Trigger type ('manual' or 'auto')"""
        return self.get_field("trigger")

    @property
    def custom_instructions(self) -> str | None:
        """Custom instructions for compaction (from user input in manual mode)"""
        return self.get_field("custom_instructions")

    # Override to only allow undefined - PreCompact hooks don't support decisions
    def block(self, reason: str) -> "HookResult":
        """Not supported for PreCompact hooks"""
        raise NotImplementedError(
            "PreCompact hooks don't support block() - only undefined()"
        )

    def approve(self, reason: str = "") -> "HookResult":
        """Not supported for PreCompact hooks"""
        raise NotImplementedError(
            "PreCompact hooks don't support approve() - only undefined()"
        )

    def block_json(self, reason: str, **kwargs) -> "JsonResult":
        """Not supported for PreCompact hooks"""
        raise NotImplementedError(
            "PreCompact hooks don't support block_json() - only undefined()"
        )

    def approve_json(self, reason: str = "", **kwargs) -> "JsonResult":
        """Not supported for PreCompact hooks"""
        raise NotImplementedError(
            "PreCompact hooks don't support approve_json() - only undefined()"
        )


# Event factory function
def create_event(ctx: EventContext) -> BaseEvent:
    """
    Create appropriate event instance based on event type

    Args:
        ctx: Event context

    Returns:
        Event-specific helper instance
    """
    event_classes = {
        "Notification": Notification,
        "PreToolUse": PreToolUse,
        "PostToolUse": PostToolUse,
        "Stop": Stop,
        "SubagentStop": SubagentStop,
        "PreCompact": PreCompact,
    }

    event_class = event_classes.get(ctx.event)
    if not event_class:
        raise ValueError(f"Unknown event type: {ctx.event}")

    return event_class(ctx)


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================


def block(reason: str) -> "HookResult":
    """Block operation with reason"""
    return HookResult(Decision.BLOCK, reason)


def approve(reason: str = "") -> "HookResult":
    """Approve operation with optional reason"""
    return HookResult(Decision.APPROVE, reason)


def undefined() -> "HookResult":
    """Let Claude Code decide (default behavior)"""
    return HookResult(None)


# JSON convenience functions
def block_json(
    reason: str,
    continue_: bool = True,
    stopReason: str = "",  # noqa: N803
    stop_reason: str = "",
) -> "JsonResult":
    """Block operation with JSON output"""
    return JsonResult(
        decision=Decision.BLOCK,
        reason=reason,
        continue_=continue_,
        stopReason=stopReason,
        stop_reason=stop_reason,
    )


def approve_json(
    reason: str = "",
    suppressOutput: bool = False,  # noqa: N803
    suppress_output: bool = False,
) -> "JsonResult":
    """Approve operation with JSON output"""
    return JsonResult(
        decision=Decision.APPROVE,
        reason=reason,
        suppressOutput=suppressOutput,
        suppress_output=suppress_output,
    )


def undefined_json(
    suppressOutput: bool = False,  # noqa: N803
    suppress_output: bool = False,
) -> "JsonResult":
    """Let Claude Code decide with JSON output"""
    return JsonResult(
        decision=None,
        suppressOutput=suppressOutput,
        suppress_output=suppress_output,
    )


def stop_claude(
    stopReason: str = "",  # noqa: N803
    stop_reason: str = "",
) -> "JsonResult":
    """Stop Claude from continuing"""
    return JsonResult(
        continue_=False,
        stopReason=stopReason,
        stop_reason=stop_reason,
    )


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    print("hook_utils.py is a utility library - import it in your hook files!")
