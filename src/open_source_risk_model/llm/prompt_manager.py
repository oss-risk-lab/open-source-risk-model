"""Centralized prompt management with YAML templates."""

from typing import Dict, Any
from pathlib import Path
import yaml
import re

from .exceptions import PromptNotFoundError, TemplateRenderError


class PromptManager:
    """
    Centralized prompt management.
    
    Loads prompts from YAML files, renders templates with parameter substitution,
    and validates prompt structure.
    
    YAML Format Expected:
        name: prompt_name
        version: "1.0"
        description: "Description"
        required_params:
          - param1
          - param2
        system_template: |
          System message with {param1}
        user_template: |
          User message with {param2}
        metadata:
          author: "team"
          created_at: "2024-02-13"
    """
    
    def __init__(self, prompts_dir: Path):
        """
        Initialize prompt manager.
        
        Args:
            prompts_dir: Directory containing prompt YAML files
            
        Raises:
            FileNotFoundError: If prompts_dir doesn't exist
        """
        self.prompts_dir = Path(prompts_dir)
        if not self.prompts_dir.exists():
            raise FileNotFoundError(f"Prompts directory not found: {prompts_dir}")
        
        self.prompts: Dict[str, Dict[str, Any]] = {}
        self._load_prompts()
    
    def _load_prompts(self) -> None:
        """
        Load all prompts from YAML files in prompts_dir.
        
        Scans the prompts directory for *.yaml files and loads them into memory.
        Each prompt is indexed by its 'name' field.
        """
        for prompt_file in self.prompts_dir.glob("*.yaml"):
            try:
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    prompt_data = yaml.safe_load(f)
                    
                    if prompt_data and 'name' in prompt_data:
                        self.prompts[prompt_data['name']] = prompt_data
            except Exception as e:
                # Log warning but continue loading other prompts
                print(f"Warning: Failed to load prompt from {prompt_file}: {e}")
    
    def render(self, prompt_name: str, params: Dict[str, Any]) -> Dict[str, str]:
        """
        Render a prompt template with parameters.
        
        Args:
            prompt_name: Name of prompt to render
            params: Parameters for template substitution
            
        Returns:
            Dict with "system" and "user" message content
            
        Raises:
            PromptNotFoundError: If prompt doesn't exist
            TemplateRenderError: If rendering fails (missing params or invalid template)
        """
        # Check if prompt exists
        if prompt_name not in self.prompts:
            raise PromptNotFoundError(
                f"Prompt '{prompt_name}' not found. Available prompts: {list(self.prompts.keys())}"
            )
        
        prompt = self.prompts[prompt_name]
        
        # Validate required parameters are provided
        required_params = prompt.get('required_params', [])
        missing_params = [p for p in required_params if p not in params]
        if missing_params:
            raise TemplateRenderError(
                f"Missing required parameters for prompt '{prompt_name}': {missing_params}"
            )
        
        # Extract templates
        system_template = prompt.get('system_template', '')
        user_template = prompt.get('user_template', '')
        
        # Validate templates before rendering - check for placeholders not in params
        self._validate_template_params(system_template, params, 'system', prompt_name)
        self._validate_template_params(user_template, params, 'user', prompt_name)
        
        # Render system message
        try:
            system_message = system_template.format(**params)
        except KeyError as e:
            raise TemplateRenderError(
                f"Missing parameter in system template for prompt '{prompt_name}': {e}"
            )
        except Exception as e:
            raise TemplateRenderError(
                f"Failed to render system template for prompt '{prompt_name}': {e}"
            )
        
        # Render user message
        try:
            user_message = user_template.format(**params)
        except KeyError as e:
            raise TemplateRenderError(
                f"Missing parameter in user template for prompt '{prompt_name}': {e}"
            )
        except Exception as e:
            raise TemplateRenderError(
                f"Failed to render user template for prompt '{prompt_name}': {e}"
            )
        
        return {
            'system': system_message,
            'user': user_message
        }
    
    def _validate_template_params(
        self,
        template: str,
        params: Dict[str, Any],
        template_type: str,
        prompt_name: str
    ) -> None:
        """
        Validate that all placeholders in template are provided in params.
        
        This checks BEFORE rendering to ensure all {placeholder} patterns
        (that aren't escaped as {{}}) have corresponding values in params.
        
        Args:
            template: Template string to validate
            params: Parameters provided for rendering
            template_type: Type of template ('system' or 'user')
            prompt_name: Name of the prompt being validated
            
        Raises:
            TemplateRenderError: If template has placeholders not in params
        """
        # Find all placeholders in the template
        # We need to find {identifier} but NOT {{identifier}}
        # Strategy: First replace all {{...}} with a placeholder, then find {identifier}
        
        # Temporarily replace escaped braces
        temp_template = template.replace('{{', '\x00').replace('}}', '\x01')
        
        # Now find single-brace placeholders
        placeholder_pattern = r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}'
        placeholders = set(re.findall(placeholder_pattern, temp_template))
        
        # Check which placeholders are missing from params
        missing = [p for p in placeholders if p not in params]
        
        if missing:
            raise TemplateRenderError(
                f"Template has placeholders not provided in params for {template_type} "
                f"template of prompt '{prompt_name}': {missing}"
            )
    
    def validate_prompt(self, prompt_name: str) -> bool:
        """
        Validate prompt structure and required fields.
        
        Args:
            prompt_name: Name of prompt to validate
            
        Returns:
            True if prompt is valid
            
        Raises:
            PromptNotFoundError: If prompt doesn't exist
            ValidationError: If prompt structure is invalid
        """
        if prompt_name not in self.prompts:
            raise PromptNotFoundError(f"Prompt '{prompt_name}' not found")
        
        prompt = self.prompts[prompt_name]
        
        # Check required fields
        required_fields = ['name', 'version', 'description']
        for field in required_fields:
            if field not in prompt:
                return False
        
        # Check that at least one template exists
        if 'system_template' not in prompt and 'user_template' not in prompt:
            return False
        
        return True
    
    def list_prompts(self) -> list[str]:
        """
        Get list of all available prompt names.
        
        Returns:
            List of prompt names
        """
        return list(self.prompts.keys())
    
    def get_prompt_info(self, prompt_name: str) -> Dict[str, Any]:
        """
        Get metadata about a prompt.
        
        Args:
            prompt_name: Name of prompt
            
        Returns:
            Dict with prompt metadata (name, version, description, required_params)
            
        Raises:
            PromptNotFoundError: If prompt doesn't exist
        """
        if prompt_name not in self.prompts:
            raise PromptNotFoundError(f"Prompt '{prompt_name}' not found")
        
        prompt = self.prompts[prompt_name]
        return {
            'name': prompt.get('name'),
            'version': prompt.get('version'),
            'description': prompt.get('description'),
            'required_params': prompt.get('required_params', []),
            'metadata': prompt.get('metadata', {})
        }
