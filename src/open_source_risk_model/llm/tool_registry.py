"""
Tool Registry for LLM function calling.

FUTURE ENHANCEMENT - NOT IMPLEMENTED IN MVP
"""

from typing import Dict, Any, Callable, List


class ToolRegistry:
    """
    Registry for LLM tools/functions.
    
    STUB: This is a placeholder for future implementation.
    """
    
    def __init__(self):
        """Initialize tool registry."""
        raise NotImplementedError("ToolRegistry not yet implemented")
    
    def register_tool(
        self,
        name: str,
        description: str,
        parameters_schema: Dict[str, Any],
        handler: Callable
    ) -> None:
        """Register a tool (not implemented)."""
        raise NotImplementedError("ToolRegistry not yet implemented")
    
    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Get tool definitions (not implemented)."""
        raise NotImplementedError("ToolRegistry not yet implemented")
