"""End-to-end tests for claude_hooks.hook_utils module.

These tests focus on real hook execution scenarios,
avoiding excessive mocking and trivial unit tests.
"""

import json
import subprocess
import sys

import pytest

from claude_hooks.hook_utils import (
    EventContext,
    JsonResult,
    Notification,
    PostToolUse,
    PreToolUse,
    Stop,
    SubagentStop,
    approve,
    block,
    create_event,
    undefined,
)


class TestHookFrameworkIntegration:
    """Test the hook framework with real hook execution."""

    def test_complete_hook_workflow(self, tmp_path):
        """Test a complete workflow: create hook, execute with payload, verify result."""
        # Create a test hook file
        hook_content = """
import json
import sys
from claude_hooks.hook_utils import run_hooks

def test_hook(event):
    if event.tool_name == "Bash" and "dangerous" in event.tool_input.get("command", ""):
        return event.block("Blocked dangerous command")
    return event.undefined()

if __name__ == "__main__":
    run_hooks(test_hook)
"""

        hook_file = tmp_path / "test_hook.py"
        hook_file.write_text(hook_content)

        # Test with safe command
        safe_payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "echo hello"},
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
            "tool_input": {"command": "rm dangerous file"},
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
from claude_hooks.hook_utils import run_hooks

def hook1(event):
    return event.undefined()

def hook2(event):
    if event.tool_name == "Bash" and "block" in event.tool_input.get("command", ""):
        return event.block("Hook 2 blocked")
    return event.undefined()

if __name__ == "__main__":
    run_hooks(hook1, hook2)
"""

        hook_file = tmp_path / "multi_hook.py"
        hook_file.write_text(hook_content)

        # Should be blocked by hook2
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "block this command"},
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
from claude_hooks.hook_utils import run_hooks

def test_hook(event):
    return event.undefined()

if __name__ == "__main__":
    run_hooks(test_hook)
"""

        hook_file = tmp_path / "invalid_hook.py"
        hook_file.write_text(hook_content)

        # Missing required hook_event_name
        invalid_payload = {"tool_name": "Bash", "tool_input": {"command": "echo test"}}

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
from claude_hooks.hook_utils import run_hooks

def failing_hook(event):
    raise ValueError("Hook intentionally failed")

if __name__ == "__main__":
    run_hooks(failing_hook)
"""

        hook_file = tmp_path / "failing_hook.py"
        hook_file.write_text(hook_content)

        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "echo test"},
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

        ctx = EventContext(
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
            "tool_input": {
                "file_path": "/secure/config.py",
                "old_string": "debug=False",
                "new_string": "debug=True",
            },
            "session_id": "session-456",
        }

        ctx = EventContext(
            event="PreToolUse",
            tool="Edit",
            input=payload["tool_input"],
            response=None,
            full_payload=payload,
        )

        event = PreToolUse(ctx)
        assert event.tool_name == "Edit"
        assert event.tool_input.get("file_path") == "/secure/config.py"
        assert event.tool_input.get("old_string") == "debug=False"
        assert event.tool_input.get("nonexistent", "default") == "default"

    def test_post_tool_use_hook_real_usage(self):
        """Test PostToolUseHook with realistic tool response data."""
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la /tmp"},
            "tool_response": {
                "output": "total 16\ndrwxr-xr-x file1.txt\ndrwxr-xr-x file2.txt\n",
                "error": "",
                "exit_code": 0,
            },
            "session_id": "session-789",
        }

        ctx = EventContext(
            event="PostToolUse",
            tool="Bash",
            input=payload["tool_input"],
            response=payload["tool_response"],
            full_payload=payload,
        )

        event = PostToolUse(ctx)
        assert event.tool_name == "Bash"
        assert "file1.txt" in event.tool_response.get("output")
        assert event.tool_response.get("exit_code") == 0
        assert event.tool_response.get("nonexistent", "default") == "default"

    def test_stop_hook_real_usage(self):
        """Test StopHook with realistic conversation end data."""
        payload = {
            "hook_event_name": "Stop",
            "session_id": "session-end-123",
            "transcript_path": "/logs/conversation_transcript.md",
            "duration": 1800,
        }

        ctx = EventContext(
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

        ctx = EventContext(
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
            ctx = EventContext(
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
        ctx = EventContext(
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

        # Test undefined
        undefined_result = undefined()
        assert undefined_result.decision is None
        assert undefined_result.reason == ""


class TestJsonOutput:
    """Test JSON output functionality with upstream compatibility."""

    def test_json_result_creation_with_upstream_naming(self):
        """Test JsonResult creation with upstream field names."""
        result = JsonResult(
            decision=None,
            reason="test reason",
            continue_=False,
            stopReason="Manual review required",
            suppressOutput=True,
        )

        assert result.decision is None
        assert result.reason == "test reason"
        assert result.continue_ is False
        assert result.stopReason == "Manual review required"
        assert result.suppressOutput is True

    def test_json_result_creation_with_python_shortcuts(self):
        """Test JsonResult creation with Python-style shortcuts."""
        result = JsonResult(
            decision=None,
            reason="test reason",
            continue_=False,
            stop_reason="Manual review required",
            suppress_output=True,
        )

        assert result.decision is None
        assert result.reason == "test reason"
        assert result.continue_ is False
        assert result.stopReason == "Manual review required"  # Should use shortcut
        assert result.suppressOutput is True  # Should use shortcut

    def test_json_result_shortcuts_override_upstream(self):
        """Test that Python shortcuts override upstream naming when both provided."""
        result = JsonResult(
            stopReason="upstream",
            stop_reason="shortcut",
            suppressOutput=False,
            suppress_output=True,
        )

        assert result.stopReason == "shortcut"  # Shortcut wins
        assert result.suppressOutput is True  # Shortcut wins

    def test_json_output_methods_on_base_event(self):
        """Test JSON output methods on BaseEvent."""
        ctx = EventContext(
            event="PreToolUse",
            tool="TestTool",
            input={"test": "data"},
            response=None,
            full_payload={"hook_event_name": "PreToolUse"},
        )

        event = create_event(ctx)

        # Test block_json
        result = event.block_json("Access denied")
        assert isinstance(result, JsonResult)
        assert result.decision.value == "block"
        assert result.reason == "Access denied"

        # Test approve_json with upstream naming
        result = event.approve_json("Access granted", suppressOutput=True)
        assert isinstance(result, JsonResult)
        assert result.decision.value == "approve"
        assert result.suppressOutput is True

        # Test approve_json with Python shortcuts
        result = event.approve_json("Access granted", suppress_output=True)
        assert isinstance(result, JsonResult)
        assert result.suppressOutput is True

        # Test undefined_json
        result = event.undefined_json()
        assert isinstance(result, JsonResult)
        assert result.decision is None

        # Test stop_claude with upstream naming
        result = event.stop_claude(stopReason="Review required")
        assert isinstance(result, JsonResult)
        assert result.continue_ is False
        assert result.stopReason == "Review required"

        # Test stop_claude with Python shortcuts
        result = event.stop_claude(stop_reason="Review required")
        assert isinstance(result, JsonResult)
        assert result.continue_ is False
        assert result.stopReason == "Review required"

    def test_json_hook_execution_with_block(self, tmp_path):
        """Test JSON hook execution that blocks operation."""
        hook_content = """
import json
from claude_hooks.hook_utils import run_hooks

def json_hook(event):
    if event.tool_name == "Bash" and "dangerous" in event.tool_input.get("command", ""):
        return event.block_json("Dangerous command blocked")
    return event.undefined_json()

if __name__ == "__main__":
    run_hooks(json_hook)
"""

        hook_file = tmp_path / "json_hook.py"
        hook_file.write_text(hook_content)

        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "dangerous command"},
        }

        result = subprocess.run(
            [sys.executable, str(hook_file)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=10,
        )

        assert result.returncode == 0  # JSON output always exits 0

        # Parse JSON output
        json_output = json.loads(result.stdout.strip())
        assert json_output["decision"] == "block"
        assert json_output["reason"] == "Dangerous command blocked"

    def test_json_hook_execution_with_approve_and_suppress(self, tmp_path):
        """Test JSON hook execution that approves with suppressed output."""
        hook_content = """
import json
from claude_hooks.hook_utils import run_hooks

def json_hook(event):
    if event.tool_name == "Read":
        return event.approve_json("File access approved", suppress_output=True)
    return event.undefined_json()

if __name__ == "__main__":
    run_hooks(json_hook)
"""

        hook_file = tmp_path / "json_hook.py"
        hook_file.write_text(hook_content)

        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "tool_input": {"file_path": "/test/file.txt"},
        }

        result = subprocess.run(
            [sys.executable, str(hook_file)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=10,
        )

        assert result.returncode == 0

        # Parse JSON output
        json_output = json.loads(result.stdout.strip())
        assert json_output["decision"] == "approve"
        assert json_output["reason"] == "File access approved"
        assert json_output["suppressOutput"] is True

    def test_json_hook_execution_with_stop_claude(self, tmp_path):
        """Test JSON hook execution that stops Claude."""
        hook_content = """
import json
from claude_hooks.hook_utils import run_hooks

def json_hook(event):
    if "critical" in event.tool_input.get("file_path", ""):
        return event.stop_claude("Critical file access requires manual review")
    return event.undefined_json()

if __name__ == "__main__":
    run_hooks(json_hook)
"""

        hook_file = tmp_path / "json_hook.py"
        hook_file.write_text(hook_content)

        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": "/critical/config.json"},
        }

        result = subprocess.run(
            [sys.executable, str(hook_file)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=10,
        )

        assert result.returncode == 0

        # Parse JSON output
        json_output = json.loads(result.stdout.strip())
        assert json_output["continue"] is False
        assert (
            json_output["stopReason"] == "Critical file access requires manual review"
        )


class TestRealWorldScenarios:
    """Test realistic hook scenarios that users would actually implement."""

    def test_security_hook_blocks_sensitive_file_access(self, tmp_path):
        """Test a realistic security hook that protects sensitive files."""
        hook_content = """
from claude_hooks.hook_utils import run_hooks

def security_hook(event):
    if event.tool_name in ["Edit", "Write", "Read"]:
        file_path = event.tool_input.get("file_path", "")
        if any(sensitive in file_path.lower() for sensitive in [".env", "secret", "password", "key"]):
            return event.block(f"Access to sensitive file blocked: {file_path}")

    return event.undefined()

if __name__ == "__main__":
    run_hooks(security_hook)
"""

        hook_file = tmp_path / "security_hook.py"
        hook_file.write_text(hook_content)

        # Should block access to .env file
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {
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
from claude_hooks.hook_utils import run_hooks
import json
from datetime import datetime

def audit_hook(event):
    # Log tool usage
    log_entry = {{
        "timestamp": datetime.now().isoformat(),
        "tool": event.tool_name,
        "session": event.session_id,
        "input": dict(event.tool_input),
        "success": event.tool_response.get("error", "") == ""
    }}

    with open("{log_file}", "a") as f:
        f.write(json.dumps(log_entry) + "\\n")

    return event.undefined()

if __name__ == "__main__":
    run_hooks(audit_hook)
'''

        hook_file = tmp_path / "audit_hook.py"
        hook_file.write_text(hook_content)

        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "echo test"},
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

    def test_advanced_json_security_hook(self, tmp_path):
        """Test advanced security hook using JSON output."""
        hook_content = """
from claude_hooks.hook_utils import run_hooks

def advanced_security_hook(event):
    if event.tool_name in ["Edit", "Write", "Read"]:
        file_path = event.tool_input.get("file_path", "")

        # Critical files stop Claude entirely
        if "critical" in file_path.lower():
            return event.stop_claude("Critical file access requires manual approval")

        # Sensitive files are blocked with JSON
        if any(sensitive in file_path.lower() for sensitive in [".env", "secret", "password", "key"]):
            return event.block_json(f"Sensitive file access blocked: {file_path}")

        # Log files are approved but suppressed from transcript
        if file_path.endswith(".log"):
            return event.approve_json("Log file access approved", suppress_output=True)

    return event.undefined_json()

if __name__ == "__main__":
    run_hooks(advanced_security_hook)
"""

        hook_file = tmp_path / "advanced_security_hook.py"
        hook_file.write_text(hook_content)

        # Test critical file access - should stop Claude
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "/critical/system.conf"},
        }

        result = subprocess.run(
            [sys.executable, str(hook_file)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=10,
        )

        assert result.returncode == 0
        json_output = json.loads(result.stdout.strip())
        assert json_output["continue"] is False
        assert (
            "Critical file access requires manual approval" in json_output["stopReason"]
        )

    def test_logging_format_with_multiple_functions(self, tmp_path):
        """Test that logging format correctly shows framework vs function logging."""
        hook_content = """
from claude_hooks import run_hooks

def first_function(event):
    event.logger.info("First function executed")
    return event.undefined()

def second_function(event):
    event.logger.info("Second function executed")
    return event.undefined()

if __name__ == "__main__":
    run_hooks(first_function, second_function)
"""

        hook_file = tmp_path / "multi_function_hook.py"
        hook_file.write_text(hook_content)

        # Create logs directory
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()

        payload = {
            "hook_event_name": "Notification",
            "tool_name": None,
            "tool_input": {},
        }

        # Run the hook
        result = subprocess.run(
            [sys.executable, str(hook_file)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=10,
            cwd=str(tmp_path),
        )

        assert result.returncode == 0

        # Check that notification.log was created
        log_file = logs_dir / "notification.log"
        assert log_file.exists()

        # Read log contents
        log_content = log_file.read_text()
        log_lines = log_content.strip().split("\n")

        # Verify framework logging appears first with [hook_utils] identifier
        framework_lines = [line for line in log_lines if "[hook_utils]" in line]
        assert (
            len(framework_lines) >= 2
        )  # Should have "Running 2 hooks" and "Raw payload"
        assert any(
            "Running 2 hooks for Notification" in line for line in framework_lines
        )

        # Verify function logging appears with proper function names
        first_func_lines = [
            line
            for line in log_lines
            if "[first_function]" in line and "First function executed" in line
        ]
        second_func_lines = [
            line
            for line in log_lines
            if "[second_function]" in line and "Second function executed" in line
        ]

        assert len(first_func_lines) == 1, (
            f"Expected 1 first_function log line, got {len(first_func_lines)}"
        )
        assert len(second_func_lines) == 1, (
            f"Expected 1 second_function log line, got {len(second_func_lines)}"
        )

        # Verify order: initial framework logs should come before function logs
        initial_framework_lines = [
            i
            for i, line in enumerate(log_lines)
            if "[hook_utils]" in line and ("Running" in line or "Raw payload" in line)
        ]
        function_line_indices = [
            i
            for i, line in enumerate(log_lines)
            if "[first_function]" in line or "[second_function]" in line
        ]

        assert len(initial_framework_lines) >= 2, (
            "Should have initial framework logs (Running hooks + Raw payload)"
        )
        assert len(function_line_indices) == 2, (
            "Should have exactly 2 function log lines"
        )
        assert max(initial_framework_lines) < min(function_line_indices), (
            "Initial framework logs should appear before function logs"
        )

    def test_logging_path_relative_to_hook_file(self, tmp_path):
        """Test that logs are created relative to the hook file, not the current working directory."""
        # Create a hook in a subdirectory
        hook_dir = tmp_path / "hook_subdir"
        hook_dir.mkdir()

        hook_content = """
from claude_hooks import run_hooks

def test_hook(event):
    event.logger.info("Hook executed from subdirectory")
    return event.undefined()

if __name__ == "__main__":
    run_hooks(test_hook)
"""

        hook_file = hook_dir / "subdir_hook.py"
        hook_file.write_text(hook_content)

        payload = {
            "hook_event_name": "Notification",
            "tool_name": None,
            "tool_input": {},
        }

        # Run the hook from the parent directory (different from hook location)
        result = subprocess.run(
            [sys.executable, str(hook_file)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=10,
            cwd=str(tmp_path),  # Running from parent directory
        )

        assert result.returncode == 0

        # Verify logs were created in the hook's directory, not the cwd
        hook_log_file = hook_dir / "logs" / "notification.log"
        assert hook_log_file.exists(), (
            "Log file should be created relative to hook file location"
        )

        # Verify no logs were created in the cwd
        cwd_log_file = tmp_path / "logs" / "notification.log"
        assert not cwd_log_file.exists(), (
            "Log file should not be created in current working directory"
        )

        # Verify log content
        log_content = hook_log_file.read_text()
        assert "Hook executed from subdirectory" in log_content
        assert "[test_hook]" in log_content

    def test_logging_level_environment_variable(self, tmp_path, monkeypatch):
        """Test that CLAUDE_HOOKS_LOG_LEVEL environment variable controls logging level."""
        # Set DEBUG level
        monkeypatch.setenv("CLAUDE_HOOKS_LOG_LEVEL", "DEBUG")

        hook_content = """
from claude_hooks import run_hooks

def debug_function(event):
    event.logger.debug("Debug message should appear")
    event.logger.info("Info message should appear")
    return event.undefined()

if __name__ == "__main__":
    run_hooks(debug_function)
"""

        hook_file = tmp_path / "debug_hook.py"
        hook_file.write_text(hook_content)

        # Create logs directory
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()

        payload = {
            "hook_event_name": "Notification",
            "tool_name": None,
            "tool_input": {},
        }

        # Run the hook
        result = subprocess.run(
            [sys.executable, str(hook_file)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=10,
            cwd=str(tmp_path),
        )

        assert result.returncode == 0

        # Check that notification.log was created
        log_file = logs_dir / "notification.log"
        assert log_file.exists()

        # Read log contents
        log_content = log_file.read_text()

        # Verify both DEBUG and INFO messages appear
        assert "[debug_function] DEBUG: Debug message should appear" in log_content
        assert "[debug_function] INFO: Info message should appear" in log_content
