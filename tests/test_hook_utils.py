"""End-to-end tests for claude_hooks.hook_utils module.

These tests focus on real hook execution scenarios,
avoiding excessive mocking and trivial unit tests.
"""

import json
import subprocess
import sys

import pytest

from claude_hooks.hook_utils import (
    HookContext,
    Notification,
    PostToolUse,
    PreToolUse,
    Stop,
    SubagentStop,
    approve,
    block,
    create_event,
    neutral,
)


class TestHookFrameworkIntegration:
    """Test the hook framework with real hook execution."""

    def test_complete_hook_workflow(self, tmp_path):
        """Test a complete workflow: create hook, execute with payload, verify result."""
        # Create a test hook file
        hook_content = """
import json
import sys
from claude_hooks.hook_utils import HookContext, run_hooks, neutral, block

def test_hook(ctx: HookContext):
    if ctx.tool == "Bash" and "dangerous" in ctx.input.get("command", ""):
        return block("Blocked dangerous command")
    return neutral()

if __name__ == "__main__":
    run_hooks(test_hook)
"""

        hook_file = tmp_path / "test_hook.py"
        hook_file.write_text(hook_content)

        # Test with safe command
        safe_payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "input": {"command": "echo hello"},
            "tool_response": None,
        }

        result = subprocess.run(
            [sys.executable, str(hook_file)],
            input=json.dumps(safe_payload),
            text=True,
            capture_output=True,
            timeout=10,
        )

        assert result.returncode == 0  # Should pass through

        # Test with dangerous command
        dangerous_payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "input": {"command": "rm dangerous file"},
            "tool_response": None,
        }

        result = subprocess.run(
            [sys.executable, str(hook_file)],
            input=json.dumps(dangerous_payload),
            text=True,
            capture_output=True,
            timeout=10,
        )

        assert result.returncode == 2  # Should be blocked
        assert "Blocked dangerous command" in result.stderr

    def test_multiple_hooks_execution(self, tmp_path):
        """Test framework with multiple hooks where one blocks."""
        hook_content = """
import json
import sys
from claude_hooks.hook_utils import HookContext, run_hooks, neutral, block

def hook1(ctx: HookContext):
    return neutral()

def hook2(ctx: HookContext):
    if ctx.tool == "Bash" and "block" in ctx.input.get("command", ""):
        return block("Hook 2 blocked")
    return neutral()

if __name__ == "__main__":
    run_hooks([hook1, hook2])
"""

        hook_file = tmp_path / "multi_hook.py"
        hook_file.write_text(hook_content)

        # Should be blocked by hook2
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "input": {"command": "block this command"},
            "tool_response": None,
        }

        result = subprocess.run(
            [sys.executable, str(hook_file)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=10,
        )

        assert result.returncode == 2
        assert "Hook 2 blocked" in result.stderr

    def test_hook_with_invalid_payload_fails_gracefully(self, tmp_path):
        """Test hooks handle invalid payloads gracefully."""
        hook_content = """
from claude_hooks.hook_utils import HookContext, run_hooks, neutral

def test_hook(ctx: HookContext):
    return neutral()

if __name__ == "__main__":
    run_hooks(test_hook)
"""

        hook_file = tmp_path / "invalid_hook.py"
        hook_file.write_text(hook_content)

        # Missing required hook_event_name
        invalid_payload = {"tool_name": "Bash", "input": {"command": "echo test"}}

        result = subprocess.run(
            [sys.executable, str(hook_file)],
            input=json.dumps(invalid_payload),
            text=True,
            capture_output=True,
            timeout=10,
        )

        assert result.returncode == 1  # Should error

    def test_hook_exception_handling(self, tmp_path):
        """Test that hook exceptions are handled properly."""
        hook_content = """
from claude_hooks.hook_utils import HookContext, run_hooks

def failing_hook(ctx: HookContext):
    raise ValueError("Hook intentionally failed")

if __name__ == "__main__":
    run_hooks(failing_hook)
"""

        hook_file = tmp_path / "failing_hook.py"
        hook_file.write_text(hook_content)

        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "input": {"command": "echo test"},
            "tool_response": None,
        }

        result = subprocess.run(
            [sys.executable, str(hook_file)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=10,
        )

        assert result.returncode == 2  # Should error
        assert "Hook intentionally failed" in result.stderr


class TestHookClasses:
    """Test the event-specific hook classes with real scenarios."""

    def test_notification_hook_real_usage(self):
        """Test NotificationHook with realistic notification data."""
        payload = {
            "hook_event_name": "Notification",
            "session_id": "session-123",
            "message": "Claude has started a new conversation",
            "transcript_path": "/tmp/transcript.txt",
        }

        ctx = HookContext(
            event="Notification",
            tool=None,
            input=payload,
            response=None,
            full_payload=payload,
        )

        event = Notification(ctx)
        assert event.message == "Claude has started a new conversation"
        assert event.session_id == "session-123"
        assert event.transcript_path == "/tmp/transcript.txt"
        assert event.has_message is True

    def test_pre_tool_use_hook_real_usage(self):
        """Test PreToolUseHook with realistic command validation."""
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "input": {
                "file_path": "/secure/config.py",
                "old_string": "debug=False",
                "new_string": "debug=True",
            },
            "session_id": "session-456",
        }

        ctx = HookContext(
            event="PreToolUse",
            tool="Edit",
            input=payload["input"],
            response=None,
            full_payload=payload,
        )

        event = PreToolUse(ctx)
        assert event.tool_name == "Edit"
        assert event.get_input("file_path") == "/secure/config.py"
        assert event.get_input("old_string") == "debug=False"
        assert event.get_input("nonexistent", "default") == "default"

    def test_post_tool_use_hook_real_usage(self):
        """Test PostToolUseHook with realistic tool response data."""
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "input": {"command": "ls -la /tmp"},
            "tool_response": {
                "output": "total 16\ndrwxr-xr-x file1.txt\ndrwxr-xr-x file2.txt\n",
                "error": "",
                "exit_code": 0,
            },
            "session_id": "session-789",
        }

        ctx = HookContext(
            event="PostToolUse",
            tool="Bash",
            input=payload["input"],
            response=payload["tool_response"],
            full_payload=payload,
        )

        event = PostToolUse(ctx)
        assert event.tool_name == "Bash"
        assert "file1.txt" in event.get_response("output")
        assert event.get_response("exit_code") == 0
        assert event.get_response("nonexistent", "default") == "default"

    def test_stop_hook_real_usage(self):
        """Test StopHook with realistic conversation end data."""
        payload = {
            "hook_event_name": "Stop",
            "session_id": "session-end-123",
            "transcript_path": "/logs/conversation_transcript.md",
            "duration": 1800,
        }

        ctx = HookContext(
            event="Stop", tool=None, input=payload, response=None, full_payload=payload
        )

        event = Stop(ctx)
        assert event.session_id == "session-end-123"
        assert event.transcript_path == "/logs/conversation_transcript.md"

    def test_subagent_stop_hook_real_usage(self):
        """Test SubagentStopHook with realistic subagent data."""
        payload = {
            "hook_event_name": "SubagentStop",
            "session_id": "subagent-456",
            "transcript_path": "/logs/subagent_log.md",
            "parent_session": "main-session-123",
        }

        ctx = HookContext(
            event="SubagentStop",
            tool=None,
            input=payload,
            response=None,
            full_payload=payload,
        )

        event = SubagentStop(ctx)
        assert event.session_id == "subagent-456"
        assert event.transcript_path == "/logs/subagent_log.md"

    def test_create_hook_factory_works(self):
        """Test create_hook factory with all event types."""
        test_cases = [
            ("Notification", Notification),
            ("PreToolUse", PreToolUse),
            ("PostToolUse", PostToolUse),
            ("Stop", Stop),
            ("SubagentStop", SubagentStop),
        ]

        for event_name, expected_class in test_cases:
            ctx = HookContext(
                event=event_name,
                tool="TestTool" if "Tool" in event_name else None,
                input={"test": "data"},
                response={"response": "data"} if event_name == "PostToolUse" else None,
                full_payload={"hook_event_name": event_name},
            )

            event = create_event(ctx)
            assert isinstance(event, expected_class)

    def test_create_hook_with_unknown_event_fails(self):
        """Test create_hook fails gracefully with unknown events."""
        ctx = HookContext(
            event="UnknownEvent", tool=None, input={}, response=None, full_payload={}
        )

        with pytest.raises(ValueError, match="Unknown event type: UnknownEvent"):
            create_event(ctx)


class TestConvenienceFunctions:
    """Test convenience functions in realistic scenarios."""

    def test_convenience_functions_return_correct_results(self):
        """Test that convenience functions work as expected."""
        # Test block
        block_result = block("Access denied")
        assert block_result.decision.value == "block"
        assert block_result.reason == "Access denied"

        # Test approve
        approve_result = approve("Command validated")
        assert approve_result.decision.value == "approve"
        assert approve_result.reason == "Command validated"

        # Test neutral
        neutral_result = neutral()
        assert neutral_result.decision.value is None
        assert neutral_result.reason == ""


class TestRealWorldScenarios:
    """Test realistic hook scenarios that users would actually implement."""

    def test_security_hook_blocks_sensitive_file_access(self, tmp_path):
        """Test a realistic security hook that protects sensitive files."""
        hook_content = """
from claude_hooks.hook_utils import HookContext, PreToolUse, run_hooks, neutral, block

def security_hook(ctx: HookContext):
    event = PreToolUse(ctx)

    if event.tool_name in ["Edit", "Write", "Read"]:
        file_path = event.get_input("file_path", "")
        if any(sensitive in file_path.lower() for sensitive in [".env", "secret", "password", "key"]):
            return block(f"Access to sensitive file blocked: {file_path}")

    return neutral()

if __name__ == "__main__":
    run_hooks(security_hook)
"""

        hook_file = tmp_path / "security_hook.py"
        hook_file.write_text(hook_content)

        # Should block access to .env file
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "input": {
                "file_path": "/project/.env",
                "old_string": "API_KEY=old",
                "new_string": "API_KEY=new",
            },
        }

        result = subprocess.run(
            [sys.executable, str(hook_file)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=10,
        )

        assert result.returncode == 2
        assert "Access to sensitive file blocked" in result.stderr
        assert ".env" in result.stderr

    def test_audit_hook_logs_tool_usage(self, tmp_path):
        """Test a realistic audit hook that logs tool usage."""
        log_file = tmp_path / "audit.log"

        hook_content = f'''
from claude_hooks.hook_utils import HookContext, PostToolUse, run_hooks, neutral
import json
from datetime import datetime

def audit_hook(ctx: HookContext):
    event = PostToolUse(ctx)

    # Log tool usage
    log_entry = {{
        "timestamp": datetime.now().isoformat(),
        "tool": event.tool_name,
        "session": event.session_id,
        "input": dict(event.tool_input),
        "success": event.get_response("error", "") == ""
    }}

    with open("{log_file}", "a") as f:
        f.write(json.dumps(log_entry) + "\\n")

    return neutral()

if __name__ == "__main__":
    run_hooks(audit_hook)
'''

        hook_file = tmp_path / "audit_hook.py"
        hook_file.write_text(hook_content)

        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "input": {"command": "echo test"},
            "tool_response": {"output": "test", "error": ""},
            "session_id": "audit-test-123",
        }

        result = subprocess.run(
            [sys.executable, str(hook_file)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert log_file.exists()

        # Verify log entry
        log_content = log_file.read_text()
        log_entry = json.loads(log_content.strip())
        assert log_entry["tool"] == "Bash"
        assert log_entry["session"] == "audit-test-123"
        assert log_entry["success"] is True
