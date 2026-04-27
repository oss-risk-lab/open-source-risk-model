"""Demonstration of OpenAIProvider usage (requires OPENAI_API_KEY)."""

import os
import pytest
from open_source_risk_model.llm.providers import OpenAIProvider
from open_source_risk_model.llm.models import (
    CompletionRequest,
    Message,
    MessageRole
)


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set - skipping integration test"
)
def test_openai_provider_integration():
    """Integration test with real OpenAI API.
    
    This test demonstrates the full workflow:
    1. Initialize provider with API key
    2. Validate configuration
    3. Create a completion request
    4. Get a response
    5. Verify response structure
    
    Note: This test requires OPENAI_API_KEY environment variable
    and will make a real API call (costs ~$0.001).
    """
    # Initialize provider
    provider = OpenAIProvider(
        api_key=os.environ["OPENAI_API_KEY"]
    )
    
    # Validate configuration
    assert provider.validate_config() is True
    
    # Create a simple request
    request = CompletionRequest(
        messages=[
            Message(
                role=MessageRole.SYSTEM,
                content="You are a helpful assistant that responds concisely."
            ),
            Message(
                role=MessageRole.USER,
                content="Say 'Hello, World!' and nothing else."
            )
        ],
        model="gpt-3.5-turbo",  # Use cheaper model for testing
        temperature=0.0,  # Deterministic
        max_tokens=50
    )
    
    # Get completion
    response = provider.complete(request)
    
    # Verify response structure
    assert response.content is not None
    assert len(response.content) > 0
    assert response.model.startswith("gpt-3.5-turbo")
    assert response.finish_reason in ["stop", "length"]
    assert response.usage["total_tokens"] > 0
    assert response.usage["prompt_tokens"] > 0
    assert response.usage["completion_tokens"] > 0
    assert response.raw_response is not None
    
    # Verify content contains expected greeting
    assert "hello" in response.content.lower() or "hi" in response.content.lower()
    
    print(f"\n✅ Integration test passed!")
    print(f"   Model: {response.model}")
    print(f"   Response: {response.content}")
    print(f"   Tokens used: {response.usage['total_tokens']}")


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set - skipping integration test"
)
def test_openai_provider_json_mode():
    """Test JSON mode with real OpenAI API."""
    provider = OpenAIProvider(
        api_key=os.environ["OPENAI_API_KEY"]
    )
    
    request = CompletionRequest(
        messages=[
            Message(
                role=MessageRole.SYSTEM,
                content="You are a helpful assistant that responds in JSON format."
            ),
            Message(
                role=MessageRole.USER,
                content='Return a JSON object with a "greeting" field containing "Hello, World!"'
            )
        ],
        model="gpt-3.5-turbo",
        temperature=0.0,
        max_tokens=50,
        response_format="json"  # Enable JSON mode
    )
    
    response = provider.complete(request)
    
    # Verify response is valid JSON
    import json
    data = json.loads(response.content)
    assert isinstance(data, dict)
    assert "greeting" in data
    
    print(f"\n✅ JSON mode test passed!")
    print(f"   Response: {response.content}")


if __name__ == "__main__":
    """Run integration tests manually if OPENAI_API_KEY is set."""
    if os.environ.get("OPENAI_API_KEY"):
        print("Running OpenAI integration tests...")
        print("=" * 60)
        test_openai_provider_integration()
        test_openai_provider_json_mode()
        print("=" * 60)
        print("All integration tests passed! ✅")
    else:
        print("⚠️  OPENAI_API_KEY not set - skipping integration tests")
        print("   Set OPENAI_API_KEY to run these tests")
