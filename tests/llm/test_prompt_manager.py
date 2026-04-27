"""Unit tests for PromptManager."""

import pytest
from pathlib import Path
import tempfile
import yaml

from open_source_risk_model.llm.prompt_manager import PromptManager
from open_source_risk_model.llm.exceptions import (
    PromptNotFoundError,
    TemplateRenderError
)


@pytest.fixture
def temp_prompts_dir(tmp_path):
    """Create a temporary directory with test prompt YAML files."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    
    # Create a simple test prompt
    simple_prompt = {
        "name": "test_prompt",
        "version": "1.0",
        "description": "A test prompt",
        "required_params": ["name", "age"],
        "system_template": "You are a helpful assistant for {name}.",
        "user_template": "The user is {age} years old.",
        "metadata": {
            "author": "test-team",
            "created_at": "2024-02-13"
        }
    }
    
    with open(prompts_dir / "test_prompt.yaml", "w") as f:
        yaml.dump(simple_prompt, f)
    
    # Create a prompt with escaped braces
    escaped_prompt = {
        "name": "escaped_braces",
        "version": "1.0",
        "description": "Prompt with escaped braces",
        "required_params": ["query"],
        "system_template": "Process this query: {query}",
        "user_template": "Return JSON: {{\"result\": \"value\", \"query\": \"{query}\"}}",
        "metadata": {}
    }
    
    with open(prompts_dir / "escaped_braces.yaml", "w") as f:
        yaml.dump(escaped_prompt, f)
    
    # Create a prompt with no required params
    no_params_prompt = {
        "name": "no_params",
        "version": "1.0",
        "description": "Prompt with no parameters",
        "system_template": "You are a helpful assistant.",
        "user_template": "Hello, how can I help you?",
        "metadata": {}
    }
    
    with open(prompts_dir / "no_params.yaml", "w") as f:
        yaml.dump(no_params_prompt, f)
    
    # Create a prompt with optional params (not in required_params)
    optional_params_prompt = {
        "name": "optional_params",
        "version": "1.0",
        "description": "Prompt with optional parameters",
        "required_params": ["required_field"],
        "system_template": "Required: {required_field}",
        "user_template": "Optional: {optional_field}",
        "metadata": {}
    }
    
    with open(prompts_dir / "optional_params.yaml", "w") as f:
        yaml.dump(optional_params_prompt, f)
    
    return prompts_dir


def test_load_prompts(temp_prompts_dir):
    """Test that prompts load correctly from directory."""
    manager = PromptManager(temp_prompts_dir)
    
    # Verify prompts were loaded
    assert len(manager.prompts) >= 3
    assert "test_prompt" in manager.prompts
    assert "escaped_braces" in manager.prompts
    assert "no_params" in manager.prompts
    
    # Verify prompt structure
    test_prompt = manager.prompts["test_prompt"]
    assert test_prompt["name"] == "test_prompt"
    assert test_prompt["version"] == "1.0"
    assert test_prompt["description"] == "A test prompt"
    assert test_prompt["required_params"] == ["name", "age"]


def test_load_prompts_nonexistent_directory():
    """Test that FileNotFoundError is raised for nonexistent directory."""
    with pytest.raises(FileNotFoundError):
        PromptManager(Path("/nonexistent/directory"))


def test_render_with_valid_params(temp_prompts_dir):
    """Test rendering a prompt with all required parameters."""
    manager = PromptManager(temp_prompts_dir)
    
    result = manager.render("test_prompt", {"name": "Alice", "age": 30})
    
    assert result["system"] == "You are a helpful assistant for Alice."
    assert result["user"] == "The user is 30 years old."


def test_render_missing_prompt(temp_prompts_dir):
    """Test that PromptNotFoundError is raised for missing prompt."""
    manager = PromptManager(temp_prompts_dir)
    
    with pytest.raises(PromptNotFoundError) as exc_info:
        manager.render("nonexistent_prompt", {})
    
    assert "nonexistent_prompt" in str(exc_info.value)
    assert "not found" in str(exc_info.value).lower()


def test_render_missing_params(temp_prompts_dir):
    """Test that TemplateRenderError is raised for missing required parameters."""
    manager = PromptManager(temp_prompts_dir)
    
    # Missing 'age' parameter
    with pytest.raises(TemplateRenderError) as exc_info:
        manager.render("test_prompt", {"name": "Alice"})
    
    assert "age" in str(exc_info.value)
    assert "missing" in str(exc_info.value).lower()


def test_render_missing_all_params(temp_prompts_dir):
    """Test that TemplateRenderError is raised when all required params are missing."""
    manager = PromptManager(temp_prompts_dir)
    
    with pytest.raises(TemplateRenderError) as exc_info:
        manager.render("test_prompt", {})
    
    error_msg = str(exc_info.value).lower()
    assert "missing" in error_msg
    # Should mention at least one of the missing params
    assert "name" in str(exc_info.value) or "age" in str(exc_info.value)


def test_no_unresolved_placeholders(temp_prompts_dir):
    """Test that all placeholders are substituted in rendered output."""
    manager = PromptManager(temp_prompts_dir)
    
    result = manager.render("test_prompt", {"name": "Bob", "age": 25})
    
    # Check that no single-brace placeholders remain
    # (escaped double braces {{ }} are allowed)
    assert "{name}" not in result["system"]
    assert "{age}" not in result["user"]
    
    # Verify actual substitution occurred
    assert "Bob" in result["system"]
    assert "25" in result["user"]


def test_escaped_braces(temp_prompts_dir):
    """Test that escaped braces {{}} are preserved in output."""
    manager = PromptManager(temp_prompts_dir)
    
    result = manager.render("escaped_braces", {"query": "test query"})
    
    # Escaped braces should be converted to single braces in output
    assert '{"result": "value"' in result["user"]
    assert "test query" in result["user"]
    
    # Verify the JSON structure is preserved
    assert "{\"result\":" in result["user"] or '{"result":' in result["user"]


def test_list_prompts(temp_prompts_dir):
    """Test that list_prompts() returns all available prompts."""
    manager = PromptManager(temp_prompts_dir)
    
    prompts = manager.list_prompts()
    
    assert isinstance(prompts, list)
    assert len(prompts) >= 3
    assert "test_prompt" in prompts
    assert "escaped_braces" in prompts
    assert "no_params" in prompts


def test_get_prompt_info(temp_prompts_dir):
    """Test that get_prompt_info() returns correct metadata."""
    manager = PromptManager(temp_prompts_dir)
    
    info = manager.get_prompt_info("test_prompt")
    
    assert info["name"] == "test_prompt"
    assert info["version"] == "1.0"
    assert info["description"] == "A test prompt"
    assert info["required_params"] == ["name", "age"]
    assert "metadata" in info
    assert info["metadata"]["author"] == "test-team"


def test_get_prompt_info_missing_prompt(temp_prompts_dir):
    """Test that get_prompt_info() raises PromptNotFoundError for missing prompt."""
    manager = PromptManager(temp_prompts_dir)
    
    with pytest.raises(PromptNotFoundError):
        manager.get_prompt_info("nonexistent_prompt")


def test_validate_prompt(temp_prompts_dir):
    """Test that validate_prompt() checks prompt structure."""
    manager = PromptManager(temp_prompts_dir)
    
    # Valid prompt should return True
    assert manager.validate_prompt("test_prompt") is True
    
    # Add an invalid prompt (missing required fields)
    manager.prompts["invalid_prompt"] = {
        "name": "invalid_prompt"
        # Missing version and description
    }
    
    assert manager.validate_prompt("invalid_prompt") is False


def test_validate_prompt_missing_prompt(temp_prompts_dir):
    """Test that validate_prompt() raises PromptNotFoundError for missing prompt."""
    manager = PromptManager(temp_prompts_dir)
    
    with pytest.raises(PromptNotFoundError):
        manager.validate_prompt("nonexistent_prompt")


def test_render_with_no_required_params(temp_prompts_dir):
    """Test rendering a prompt that has no required parameters."""
    manager = PromptManager(temp_prompts_dir)
    
    result = manager.render("no_params", {})
    
    assert result["system"] == "You are a helpful assistant."
    assert result["user"] == "Hello, how can I help you?"


def test_render_with_extra_params(temp_prompts_dir):
    """Test that extra parameters (not in template) don't cause errors."""
    manager = PromptManager(temp_prompts_dir)
    
    # Provide extra params that aren't used in the template
    result = manager.render("test_prompt", {
        "name": "Charlie",
        "age": 35,
        "extra_param": "unused",
        "another_extra": 123
    })
    
    assert result["system"] == "You are a helpful assistant for Charlie."
    assert result["user"] == "The user is 35 years old."


def test_render_with_optional_params_missing(temp_prompts_dir):
    """Test that missing optional parameters (not in required_params) raise error."""
    manager = PromptManager(temp_prompts_dir)
    
    # The template has {optional_field} but it's not in required_params
    # This should still raise an error because the placeholder can't be resolved
    with pytest.raises(TemplateRenderError) as exc_info:
        manager.render("optional_params", {"required_field": "value"})
    
    assert "optional_field" in str(exc_info.value)


def test_render_with_all_params_including_optional(temp_prompts_dir):
    """Test rendering when all parameters including optional ones are provided."""
    manager = PromptManager(temp_prompts_dir)
    
    result = manager.render("optional_params", {
        "required_field": "required_value",
        "optional_field": "optional_value"
    })
    
    assert result["system"] == "Required: required_value"
    assert result["user"] == "Optional: optional_value"


def test_render_with_special_characters(temp_prompts_dir):
    """Test rendering with special characters in parameter values."""
    manager = PromptManager(temp_prompts_dir)
    
    result = manager.render("test_prompt", {
        "name": "Alice & Bob",
        "age": "30 (approximately)"
    })
    
    assert "Alice & Bob" in result["system"]
    assert "30 (approximately)" in result["user"]


def test_render_with_numeric_params(temp_prompts_dir):
    """Test rendering with numeric parameter values."""
    manager = PromptManager(temp_prompts_dir)
    
    result = manager.render("test_prompt", {
        "name": "Alice",
        "age": 30  # Integer, not string
    })
    
    assert "Alice" in result["system"]
    assert "30" in result["user"]


def test_multiple_prompts_loaded(temp_prompts_dir):
    """Test that multiple prompts can be loaded and used independently."""
    manager = PromptManager(temp_prompts_dir)
    
    # Render first prompt
    result1 = manager.render("test_prompt", {"name": "Alice", "age": 30})
    
    # Render second prompt
    result2 = manager.render("escaped_braces", {"query": "test"})
    
    # Verify both work correctly
    assert "Alice" in result1["system"]
    assert "test" in result2["system"]


def test_prompt_manager_with_real_intent_classification():
    """Test PromptManager with the real intent_classification.yaml file."""
    # Use the actual prompts directory
    prompts_dir = Path("src/open_source_risk_model/llm/prompts")
    
    if not prompts_dir.exists():
        pytest.skip("Real prompts directory not found")
    
    manager = PromptManager(prompts_dir)
    
    # Verify intent_classification prompt loaded
    assert "intent_classification" in manager.prompts
    
    # Test rendering with valid params
    result = manager.render("intent_classification", {
        "query": "What are the dependencies of django/django?",
        "available_intents": "list_dependencies, search_packages"
    })
    
    assert "django/django" in result["user"]
    assert "list_dependencies" in result["system"]
    
    # Verify no unresolved placeholders
    assert "{query}" not in result["user"]
    assert "{available_intents}" not in result["system"]


def test_error_messages_are_helpful(temp_prompts_dir):
    """Test that error messages provide helpful information."""
    manager = PromptManager(temp_prompts_dir)
    
    # Test missing prompt error message
    try:
        manager.render("nonexistent", {})
    except PromptNotFoundError as e:
        error_msg = str(e)
        assert "nonexistent" in error_msg
        assert "Available prompts:" in error_msg
        # Should list available prompts
        assert "test_prompt" in error_msg
    
    # Test missing parameter error message
    try:
        manager.render("test_prompt", {"name": "Alice"})
    except TemplateRenderError as e:
        error_msg = str(e)
        assert "age" in error_msg
        assert "test_prompt" in error_msg
