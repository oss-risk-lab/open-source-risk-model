"""Data models for LLM provider abstraction layer."""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, Optional, List, Literal


class MessageRole(str, Enum):
    """Standard message roles across providers."""
    
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    """Standardized message format.
    
    Attributes:
        role: The role of the message sender (system, user, assistant, or tool)
        content: The content of the message
        name: Optional name of the message sender (for tool messages)
        tool_calls: Optional list of tool calls made by the assistant
    """
    
    role: MessageRole
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


@dataclass
class CompletionRequest:
    """Standardized completion request.
    
    Attributes:
        messages: List of messages in the conversation
        model: The model to use for completion
        temperature: Sampling temperature (0.0 = deterministic, higher = more random)
        max_tokens: Maximum number of tokens to generate
        response_format: Optional response format ("json" for JSON mode, None for text)
        tools: Optional list of tool definitions for function calling
        tool_choice: Optional tool choice strategy ("auto", "none", or specific tool)
        prompt_name: Optional prompt name for debugging and MockProvider routing
    """
    
    messages: List[Message]
    model: str
    temperature: float = 0.0
    max_tokens: int = 500
    response_format: Optional[Literal["json"]] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[str] = None
    prompt_name: Optional[str] = None


@dataclass
class CompletionResponse:
    """Standardized completion response.
    
    Attributes:
        content: The generated completion content
        model: The model that generated the completion
        finish_reason: Reason for completion finish (e.g., "stop", "length", "tool_calls")
        usage: Token usage statistics (total_tokens, prompt_tokens, completion_tokens)
        tool_calls: Optional list of tool calls made by the assistant
        raw_response: Optional raw response from the provider for debugging
    """
    
    content: str
    model: str
    finish_reason: str
    usage: Dict[str, int]
    tool_calls: Optional[List[Dict[str, Any]]] = None
    raw_response: Optional[Any] = None
