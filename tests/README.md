# Testing Strategy

This document outlines the testing philosophy and principles for the claude-hooks project.

## Testing Philosophy

Our testing strategy prioritizes **end-to-end validation** over unit testing to ensure the complete user workflow works correctly. This approach catches integration issues and real-world problems that superficial unit tests miss.

### Core Principles

#### 1. **End-to-End Over Unit Testing**
- Test complete workflows users actually experience
- Avoid testing internal implementation details
- Focus on observable behavior and outcomes

#### 2. **Minimal Mocking**
- Only mock system boundaries (subprocess, file I/O, network)
- Never mock our own code - test it directly
- Prefer real execution when possible

#### 3. **Real Scenarios Over Trivial Tests**
- Test patterns users will actually implement
- Use realistic data and payloads
- Cover error scenarios users might encounter

#### 4. **Functional Validation**
- Generated code must actually work (syntax check + execution)
- Settings files must contain correct paths and structure
- Hook execution must produce expected exit codes and output

## What We Test

### ✅ **Valuable Tests**

#### **Complete CLI Workflows**
```python
def test_init_creates_working_hooks_structure(self, tmp_path):
    # Initialize hooks
    result = runner.invoke(main, ["init", "--dir", str(tmp_path)])
    
    # Verify files exist in correct structure
    assert (tmp_path / "hooks" / "notification.py").exists()
    
    # Verify generated code is valid Python
    subprocess.run([sys.executable, "-m", "py_compile", hook_file])
    
    # Verify settings.json has correct paths
    assert "hooks/" in settings["hooks"]["Notification"][0]["hooks"][0]["command"]
```

#### **Real Hook Execution**
```python
def test_pre_tool_use_hook_can_block_commands(self, tmp_path):
    # Generate hook with CLI
    runner.invoke(main, ["init", "--dir", str(tmp_path), "--pre-tool-use"])
    
    # Execute with dangerous payload
    result = subprocess.run([sys.executable, hook_file], 
                          input=json.dumps(dangerous_payload))
    
    # Verify it actually blocks
    assert result.returncode == 2
    assert "Dangerous command blocked" in result.stderr
```

#### **Integration Scenarios**
- Directory creation with nested paths
- Settings merging with existing configuration
- Cross-platform compatibility (paths with spaces)
- Error handling with malformed input

#### **Real-World Use Cases**
- Security hooks that block sensitive file access
- Audit hooks that log tool usage to files
- Multiple hook execution with blocking behavior

### ❌ **Tests We Avoid**

#### **Superficial Unit Tests**
```python
# DON'T TEST: Internal function behavior
def test_get_hook_command_path():
    result = get_hook_command_path("test.py", "/path")
    assert result == "expected"
    
# DON'T TEST: Trivial constructors
def test_hook_result_creation():
    result = HookResult(Decision.BLOCK, "reason")
    assert result.decision == Decision.BLOCK
```

#### **Excessive Mocking**
```python
# DON'T DO: Mock our own framework
with patch("claude_hooks.hook_utils.run_hooks"):
with patch("sys.stdin.read"):
with patch("sys.exit"):
    # Test mocks instead of real behavior
```

#### **Implementation Detail Testing**
- Testing internal helper functions
- Testing class properties and getters
- Testing enum values and constants

## Test Structure

### **Test Organization**
```
tests/
├── README.md                    # This file
├── test_cli.py                  # CLI end-to-end tests
└── test_hook_utils.py           # Hook framework integration tests
```

### **Test Classes by Purpose**
- `TestInitWorkflow` - Complete init command workflows
- `TestHookExecution` - Real hook execution scenarios  
- `TestCreateCommand` - Create command functionality
- `TestHookFrameworkIntegration` - Hook framework with real execution
- `TestRealWorldScenarios` - Realistic user implementations

## Running Tests

### **Standard Test Run**
```bash
# Run linting first to catch style issues
uv run ruff check . && uv run ruff format .

# Run tests 
uv run pytest
```

### **Verbose Output for Debugging**
```bash
uv run pytest -v
```

### **Run Specific Test Class**
```bash
uv run pytest tests/test_cli.py::TestInitWorkflow -v
```

### **Clear Cache When Testing CLI Changes**
```bash
uv cache clean
uv run pytest
```

## Test Quality Guidelines

### **Good Test Characteristics**
1. **Tests user-observable behavior** - What would a user notice if it broke?
2. **Self-contained** - Creates its own test data and environment
3. **Fast execution** - Completes quickly but thoroughly
4. **Clear failure messages** - Easy to understand what went wrong
5. **Realistic scenarios** - Tests what users actually do

### **Red Flags in Tests**
1. **Testing getters/setters** - Usually indicates testing implementation details
2. **Complex setup/mocking** - Often means testing wrong abstraction level
3. **Brittle assertions** - Tests that break on minor refactoring
4. **No actual execution** - Tests that don't run the real code path

## Example: Good vs Bad Test

### ❌ **Bad Test (Unit/Mocked)**
```python
def test_hook_result_exit_logic():
    with patch("sys.exit") as mock_exit:
        result = HookResult(Decision.BLOCK, "test")
        result.exit_with_result()
        mock_exit.assert_called_with(2)
```

### ✅ **Good Test (End-to-End)**
```python
def test_security_hook_blocks_sensitive_files(self, tmp_path):
    # Create realistic security hook
    hook_content = '''
    def security_hook(ctx):
        if ".env" in ctx.input.get("file_path", ""):
            return block("Sensitive file blocked")
        return neutral()
    '''
    
    # Execute with real payload
    result = subprocess.run([sys.executable, hook_file],
                          input=json.dumps(payload))
    
    # Verify real behavior
    assert result.returncode == 2
    assert "Sensitive file blocked" in result.stderr
```

## Debugging Test Failures

### **Common Issues**
1. **Cache problems** - Run `uv cache clean` if CLI behavior seems stale
2. **Path issues** - Ensure tests use absolute paths with `tmp_path`
3. **Timeout issues** - Add `timeout=10` to subprocess calls
4. **Syntax errors** - Check generated code with `py_compile` first

### **Test Environment**
- Tests run in isolated temporary directories
- Each test gets a fresh `tmp_path` fixture
- Tests should not depend on external state or files

## Maintenance

### **When Adding New Features**
1. **Add end-to-end test first** - Test the complete user workflow
2. **Include error scenarios** - Test what happens when things go wrong
3. **Test realistic usage** - Use real data and scenarios users would encounter
4. **Verify actual execution** - Make sure generated code actually works

### **When Modifying Tests**
1. **Preserve test intent** - Keep testing the same user scenario
2. **Update for new behavior** - Adjust expectations for changed functionality
3. **Maintain test isolation** - Ensure tests don't interfere with each other
4. **Keep tests simple** - Avoid complex test logic that needs its own testing

This testing strategy ensures our simple library has robust validation without over-testing implementation details.