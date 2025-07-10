#!/usr/bin/env python3
"""
hook_utils.py - Shared utilities for Claude Code hooks

Provides HookContext, HookResult, and run_hooks() for standardized hook development.
"""
import sys
import json
import logging
import logging.handlers
import subprocess
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path
from enum import Enum

# ============================================================================
# CORE FRAMEWORK CLASSES
# ============================================================================


class Decision(Enum):
    """Hook decision options"""

    BLOCK = "block"
    APPROVE = "approve"
    NEUTRAL = None  # Let Claude Code decide


@dataclass
class HookContext:
    """Raw hook context from Claude Code. Use specific hook classes for structured access."""

    event: str
    tool: Optional[str]
    input: Dict[str, Any]
    response: Optional[Dict[str, Any]] = None
    full_payload: Dict[str, Any] = None

    @classmethod
    def from_stdin(cls) -> "HookContext":
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
                input=payload.get("input", {}),
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

    def __init__(self, decision: Decision, reason: str = ""):
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
            # NEUTRAL - Exit 0: Let Claude Code decide (no output)
            sys.exit(0)


# ============================================================================
# LOGGING UTILITIES
# ============================================================================


def setup_logging(hook_name: str, event_name: str = None) -> None:
    """Setup logging for a specific hook"""
    import inspect

    # Get the caller's file path to determine log directory
    caller_frame = inspect.currentframe().f_back
    caller_file = caller_frame.f_globals.get("__file__")

    if caller_file:
        # Create logs directory relative to the hook file
        hook_dir = Path(caller_file).parent
        log_dir = hook_dir / "logs"
    else:
        # Fallback to current directory
        log_dir = Path("logs")

    log_dir.mkdir(parents=True, exist_ok=True)

    # Clear any existing handlers to avoid duplicates
    logging.getLogger().handlers.clear()

    # Create log filename based on event and function name
    if event_name and event_name.lower() != hook_name.lower():
        log_filename = f"{event_name.lower()}_{hook_name}_hooks.log"
    else:
        log_filename = f"{hook_name}_hooks.log"
    
    # Create rotating file handler (10MB max, keep 5 files)
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / log_filename,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.flush = lambda: file_handler.stream.flush()

    # Create stream handler
    stream_handler = logging.StreamHandler(sys.stderr)

    logging.basicConfig(
        level=logging.INFO,
        format=f"%(asctime)s [{hook_name}] %(levelname)s: %(message)s",
        handlers=[file_handler, stream_handler],
        force=True,  # Clear any existing handlers
    )

    # Force immediate flushing after each log message
    for handler in logging.getLogger().handlers:
        handler.flush()


# ============================================================================
# COMMAND UTILITIES
# ============================================================================


def run_command(command: list, timeout: int = 30) -> Tuple[bool, str, str]:
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


def run_hooks(hooks) -> None:
    """
    Run single or multiple hook functions with parallel execution support

    Args:
        hooks: Either:
               - A single hook function: (ctx: HookContext) -> HookResult
               - A list of hook functions
    """
    # Handle single hook case
    if not isinstance(hooks, list):
        hooks = [hooks]  # Convert to list for unified handling

    # Validate input
    if not hooks:
        logging.error(f"No hooks provided")
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
        ctx = HookContext.from_stdin()
        setup_logging(hook_name, ctx.event)
        logging.info(f"Running {len(hooks)} hooks for {ctx.event} on {ctx.tool}")
        logging.info(f"Raw payload: {json.dumps(ctx.full_payload, indent=2)}")

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
                futures[executor.submit(_execute_hook, hook, ctx)] = individual_name

            # Collect results - any block wins
            for future in concurrent.futures.as_completed(futures):
                hook_name_individual = futures[future]
                try:
                    result = future.result()
                    if not isinstance(result, HookResult):
                        logging.error(
                            f"Hook {hook_name_individual} returned invalid result type"
                        )
                        print(
                            f"Invalid result from {hook_name_individual}",
                            file=sys.stderr,
                        )
                        sys.exit(2)

                    if result.decision == Decision.BLOCK:
                        logging.info(f"Hook {hook_name_individual} blocked operation")
                        result.exit_with_result()

                except Exception as e:
                    logging.error(f"Hook {hook_name_individual} failed: {e}")
                    print(f"{hook_name_individual} failed: {e}", file=sys.stderr)
                    sys.exit(2)

        # All hooks passed
        logging.info(f"All {len(hooks)} hooks completed successfully")
        sys.exit(0)

    except KeyboardInterrupt:
        logging.info(f"Hooks interrupted by user")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Hooks failed: {e}")
        sys.exit(1)


def _execute_hook(hook, ctx: HookContext) -> HookResult:
    """Execute a single hook function"""
    try:
        if not callable(hook):
            raise ValueError(f"Hook must be a callable function, got {type(hook)}")
        return hook(ctx)
    except Exception as e:
        raise Exception(f"Hook execution failed: {e}")


# ============================================================================
# CLASS-BASED HOOK FRAMEWORK
# ============================================================================


class BaseHook:
    """Base class for event-specific hook helpers with validation and field access."""

    def __init__(self, ctx: HookContext):
        self.ctx = ctx
        self.validate_required_fields()

    def validate_required_fields(self):
        """Override in subclasses to validate event-specific requirements"""
        if not self.ctx.event:
            raise ValueError("Missing hook_event_name")

    def _validate_event(self, expected_event: str):
        """Helper to validate event type"""
        if self.ctx.event != expected_event:
            raise ValueError(f"Expected {expected_event} event, got {self.ctx.event}")

    def _validate_tool_present(self):
        """Helper to validate tool is present"""
        if not self.ctx.tool:
            raise ValueError(f"{self.ctx.event} event missing tool_name")

    def get_field(self, *keys, default=None):
        """
        Safely get nested field from full payload

        Args:
            *keys: Field path (e.g., "session_id" or nested like "config", "timeout")
            default: Default value if not found

        Returns:
            Field value or default
        """
        current = self.ctx.full_payload
        for key in keys:
            if not isinstance(current, dict) or key not in current:
                return default
            current = current[key]
        return current


class NotificationHook(BaseHook):
    """Hook for Notification events"""

    def validate_required_fields(self):
        super().validate_required_fields()
        self._validate_event("Notification")

    @property
    def message(self) -> Optional[str]:
        return self.get_field("message")

    @property
    def session_id(self) -> Optional[str]:
        return self.get_field("session_id")

    @property
    def transcript_path(self) -> Optional[str]:
        return self.get_field("transcript_path")

    @property
    def has_message(self) -> bool:
        return bool(self.message)


class ToolHook(BaseHook):
    """Base class for tool-related hooks (PreToolUse, PostToolUse)"""

    def validate_required_fields(self):
        super().validate_required_fields()
        self._validate_tool_present()

    @property
    def tool_name(self) -> str:
        return self.ctx.tool

    @property
    def tool_input(self) -> Dict[str, Any]:
        return self.ctx.input

    @property
    def session_id(self) -> Optional[str]:
        return self.get_field("session_id")

    def get_input(self, key: str, default=None):
        """Get specific tool input parameter"""
        return self.tool_input.get(key, default)


class PreToolUseHook(ToolHook):
    """Hook for PreToolUse events (before tool execution)"""

    def validate_required_fields(self):
        super().validate_required_fields()
        self._validate_event("PreToolUse")


class PostToolUseHook(ToolHook):
    """Hook for PostToolUse events (after tool execution)"""

    def validate_required_fields(self):
        super().validate_required_fields()
        self._validate_event("PostToolUse")
        if self.ctx.response is None:
            raise ValueError("PostToolUse event missing tool_response")

    @property
    def tool_response(self) -> Dict[str, Any]:
        return self.ctx.response

    def get_response(self, key: str, default=None):
        """Get specific field from tool response"""
        return self.tool_response.get(key, default)


class StopHook(BaseHook):
    """Hook for Stop events (when Claude finishes)"""

    def validate_required_fields(self):
        super().validate_required_fields()
        self._validate_event("Stop")

    @property
    def session_id(self) -> Optional[str]:
        return self.get_field("session_id")

    @property
    def transcript_path(self) -> Optional[str]:
        return self.get_field("transcript_path")


# Hook factory function
def create_hook(ctx: HookContext) -> BaseHook:
    """
    Create appropriate hook instance based on event type

    Args:
        ctx: Hook context

    Returns:
        Event-specific hook instance
    """
    hook_classes = {
        "Notification": NotificationHook,
        "PreToolUse": PreToolUseHook,
        "PostToolUse": PostToolUseHook,
        "Stop": StopHook,
        "SubagentStop": StopHook,  # Same as Stop for now
    }

    hook_class = hook_classes.get(ctx.event)
    if not hook_class:
        raise ValueError(f"Unknown hook event: {ctx.event}")

    return hook_class(ctx)


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================


def block(reason: str) -> "HookResult":
    """Block operation with reason"""
    return HookResult(Decision.BLOCK, reason)


def approve(reason: str = "") -> "HookResult":
    """Approve operation with optional reason"""
    return HookResult(Decision.APPROVE, reason)


def neutral() -> "HookResult":
    """Let Claude Code decide (default behavior)"""
    return HookResult(Decision.NEUTRAL)


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    print("hook_utils.py is a utility library - import it in your hook files!")
