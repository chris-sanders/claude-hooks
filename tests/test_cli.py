"""End-to-end tests for claude_hooks.cli module.

These tests focus on real workflows users would experience,
avoiding unit testing of internal functions.
"""

import json
import subprocess
import sys

from click.testing import CliRunner

from claude_hooks.cli import main


class TestInitWorkflow:
    """Test complete init workflow end-to-end."""

    def test_init_creates_working_hooks_structure(self, tmp_path):
        """Test that init creates a fully functional hooks setup."""
        runner = CliRunner()

        # Initialize with all hooks
        result = runner.invoke(main, ["init", "--dir", str(tmp_path)])
        assert result.exit_code == 0

        # Verify directory structure
        hooks_dir = tmp_path / "hooks"
        settings_file = tmp_path / "settings.json"
        pyproject_file = hooks_dir / "pyproject.toml"

        assert hooks_dir.exists() and hooks_dir.is_dir()
        assert settings_file.exists()
        assert pyproject_file.exists()

        # Verify pyproject.toml contains claude-hooks dependency
        pyproject_content = pyproject_file.read_text()
        assert "[project]" in pyproject_content
        assert "claude-hooks" in pyproject_content

        # Verify all expected hook files exist and are executable Python
        expected_hooks = [
            "notification.py",
            "pre_tool_use.py",
            "post_tool_use.py",
            "stop.py",
            "subagent_stop.py",
        ]

        for hook_file in expected_hooks:
            hook_path = hooks_dir / hook_file
            assert hook_path.exists(), f"Missing hook file: {hook_file}"

            # Verify Python syntax is valid
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", str(hook_path)],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, (
                f"Syntax error in {hook_file}: {result.stderr}"
            )

            # Verify hook contains expected framework imports
            content = hook_path.read_text()
            assert "from claude_hooks import" in content
            assert "run_hooks" in content

        # Verify settings.json structure and commands
        with open(settings_file) as f:
            settings = json.load(f)

        assert "hooks" in settings
        expected_events = [
            "Notification",
            "PreToolUse",
            "PostToolUse",
            "Stop",
            "SubagentStop",
        ]

        for event in expected_events:
            assert event in settings["hooks"], f"Missing {event} in settings"
            command = settings["hooks"][event][0]["hooks"][0]["command"]
            assert "hooks/" in command, (
                f"Command doesn't reference hooks/ directory: {command}"
            )

    def test_init_selective_hooks_only_creates_requested(self, tmp_path):
        """Test selective hook creation."""
        runner = CliRunner()

        result = runner.invoke(
            main, ["init", "notification", "stop", "--dir", str(tmp_path)]
        )
        assert result.exit_code == 0

        hooks_dir = tmp_path / "hooks"

        # Only requested hooks should exist
        assert (hooks_dir / "notification.py").exists()
        assert (hooks_dir / "stop.py").exists()
        assert not (hooks_dir / "pre_tool_use.py").exists()
        assert not (hooks_dir / "post_tool_use.py").exists()
        assert not (hooks_dir / "subagent_stop.py").exists()

        # Settings should only contain requested hooks
        with open(tmp_path / "settings.json") as f:
            settings = json.load(f)

        assert "Notification" in settings["hooks"]
        assert "Stop" in settings["hooks"]
        assert "PreToolUse" not in settings["hooks"]

    def test_init_merges_with_existing_settings(self, tmp_path):
        """Test that init merges with existing settings without breaking them."""
        # Create existing settings
        existing_settings = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "custom",
                        "hooks": [{"type": "command", "command": "existing.py"}],
                    }
                ]
            },
            "other_config": "preserved",
        }

        settings_file = tmp_path / "settings.json"
        with open(settings_file, "w") as f:
            json.dump(existing_settings, f)

        runner = CliRunner()
        result = runner.invoke(main, ["init", "pre-tool-use", "--dir", str(tmp_path)])
        assert result.exit_code == 0

        # Verify merge preserved existing and added new
        with open(settings_file) as f:
            merged = json.load(f)

        assert "other_config" in merged  # Preserved
        assert len(merged["hooks"]["PreToolUse"]) == 2  # Existing + new
        assert (
            merged["hooks"]["PreToolUse"][0]["matcher"] == "custom"
        )  # Original preserved

    def test_init_creates_pyproject_toml_with_dependency(self, tmp_path):
        """Test that init creates pyproject.toml with claude-hooks dependency."""
        runner = CliRunner()
        result = runner.invoke(main, ["init", "notification", "--dir", str(tmp_path)])
        assert result.exit_code == 0

        # Verify pyproject.toml creation
        pyproject_file = tmp_path / "hooks" / "pyproject.toml"
        assert pyproject_file.exists()

        content = pyproject_file.read_text()
        assert "[project]" in content
        assert '"claude-hooks"' in content
        assert "dependencies" in content

    def test_init_skips_existing_pyproject_toml(self, tmp_path):
        """Test that init doesn't overwrite existing pyproject.toml."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()

        # Create existing pyproject.toml
        existing_pyproject = hooks_dir / "pyproject.toml"
        existing_content = "[project]\nname = 'existing'"
        existing_pyproject.write_text(existing_content)

        runner = CliRunner()
        result = runner.invoke(main, ["init", "notification", "--dir", str(tmp_path)])
        assert result.exit_code == 0

        # Verify existing content preserved
        assert existing_pyproject.read_text() == existing_content
        assert "Skipping pyproject.toml" in result.output

    def test_init_force_overwrites_existing(self, tmp_path):
        """Test --force flag overwrites existing files."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()

        # Create existing hook with different content
        existing_hook = hooks_dir / "notification.py"
        existing_hook.write_text("# Old content")

        runner = CliRunner()
        result = runner.invoke(
            main, ["init", "notification", "--dir", str(tmp_path), "--force"]
        )
        assert result.exit_code == 0

        # Verify content was overwritten
        new_content = existing_hook.read_text()
        assert "# Old content" not in new_content
        assert "from claude_hooks import" in new_content


class TestHookExecution:
    """Test actual hook execution end-to-end."""

    def test_notification_hook_executes_successfully(self, tmp_path):
        """Test that generated notification hook actually works."""
        # Initialize notification hook
        runner = CliRunner()
        result = runner.invoke(main, ["init", "notification", "--dir", str(tmp_path)])
        assert result.exit_code == 0

        hook_file = tmp_path / "hooks" / "notification.py"

        # Create test payload
        payload = {
            "hook_event_name": "Notification",
            "session_id": "test-123",
            "message": "Test notification",
        }

        # Execute hook directly
        result = subprocess.run(
            [sys.executable, str(hook_file)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=10,
        )

        # Should exit successfully (neutral/approve)
        assert result.returncode == 0

    def test_pre_tool_use_hook_can_block_commands(self, tmp_path):
        """Test that pre-tool-use hook can actually block dangerous commands."""
        # Create a custom hook that blocks dangerous commands
        hook_content = """
from claude_hooks import run_hooks

def security_hook(event):
    if event.tool_name == "Bash" and "rm -rf" in event.tool_input.get("command", ""):
        return event.block("Dangerous command blocked")
    return event.undefined()

if __name__ == "__main__":
    run_hooks(security_hook)
"""

        hook_file = tmp_path / "security_hook.py"
        hook_file.write_text(hook_content)

        # Test with dangerous command that should be blocked
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /important/data"},
            "session_id": "test-123",
        }

        result = subprocess.run(
            [sys.executable, str(hook_file)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=10,
        )

        # Should be blocked (exit code 2)
        assert result.returncode == 2
        assert "Dangerous command blocked" in result.stderr

    def test_post_tool_use_hook_processes_responses(self, tmp_path):
        """Test that post-tool-use hook processes tool responses."""
        runner = CliRunner()
        result = runner.invoke(main, ["init", "post-tool-use", "--dir", str(tmp_path)])
        assert result.exit_code == 0

        hook_file = tmp_path / "hooks" / "post_tool_use.py"

        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "echo hello"},
            "tool_response": {"output": "hello\n", "error": ""},
            "session_id": "test-123",
        }

        result = subprocess.run(
            [sys.executable, str(hook_file)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=10,
        )

        assert result.returncode == 0

    def test_hook_handles_malformed_json_gracefully(self, tmp_path):
        """Test hooks handle malformed input gracefully."""
        runner = CliRunner()
        result = runner.invoke(main, ["init", "notification", "--dir", str(tmp_path)])
        assert result.exit_code == 0

        hook_file = tmp_path / "hooks" / "notification.py"

        # Send malformed JSON
        result = subprocess.run(
            [sys.executable, str(hook_file)],
            input="invalid json {",
            text=True,
            capture_output=True,
            timeout=10,
        )

        # Should exit with error code but not crash
        assert result.returncode == 1


class TestCreateCommand:
    """Test create command end-to-end."""

    def test_create_produces_working_hook(self, tmp_path):
        """Test that create command produces a functional hook file."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["create", "notification.py", "--dir", str(tmp_path)]
        )
        assert result.exit_code == 0

        hook_file = tmp_path / "notification.py"
        assert hook_file.exists()

        # Verify it's valid Python
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(hook_file)], capture_output=True
        )
        assert result.returncode == 0

        # Verify it can execute
        payload = {"hook_event_name": "Notification", "message": "test"}

        result = subprocess.run(
            [sys.executable, str(hook_file)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=10,
        )
        assert result.returncode == 0


class TestErrorHandling:
    """Test error scenarios end-to-end."""

    def test_init_invalid_directory_creates_parent(self, tmp_path):
        """Test init creates parent directories when needed."""
        nested_dir = tmp_path / "deep" / "nested" / "path"

        runner = CliRunner()
        result = runner.invoke(main, ["init", "notification", "--dir", str(nested_dir)])
        assert result.exit_code == 0

        assert nested_dir.exists()
        assert (nested_dir / "hooks" / "notification.py").exists()

    def test_create_invalid_hook_name_fails(self, tmp_path):
        """Test create command with invalid hook name."""
        runner = CliRunner()
        result = runner.invoke(main, ["create", "invalid.py", "--dir", str(tmp_path)])

        # Should fail with validation error
        assert result.exit_code != 0


class TestCrossCompatibility:
    """Test cross-platform compatibility."""

    def test_init_works_with_spaces_in_paths(self, tmp_path):
        """Test init works with directory paths containing spaces."""
        spaced_dir = tmp_path / "path with spaces"

        runner = CliRunner()
        result = runner.invoke(main, ["init", "notification", "--dir", str(spaced_dir)])
        assert result.exit_code == 0

        hook_file = spaced_dir / "hooks" / "notification.py"
        assert hook_file.exists()

        # Verify the generated hook still works
        payload = {"hook_event_name": "Notification", "message": "test"}
        result = subprocess.run(
            [sys.executable, str(hook_file)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=10,
        )
        assert result.returncode == 0
