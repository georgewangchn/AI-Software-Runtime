"""
Renderer module for the Declarative Knowledge Compiler

Implements template-based rendering of fact data into documentation formats.
"""

import os
import jinja2
from typing import Dict, Any, Optional
from pathlib import Path


class Renderer:
    """Renderer that converts fact data into documentation using Jinja2 templates."""

    def __init__(self, unified_loader: Any):
        self.unified_loader: Any = unified_loader
        self.env = jinja2.Environment(
            loader=jinja2.BaseLoader(),
            autoescape=True
        )
        self.env.filters['asset'] = self._asset_ref
        
    def _asset_ref(self, asset_key: str) -> str:
        if ":" not in asset_key:
            raise ValueError(f"Invalid asset reference format: {asset_key}. Expected format: 'pack_name:rel_path'")
            
        pack_name, rel_path = asset_key.split(":", 1)
        
        asset_path = self.unified_loader.get_asset_path(asset_key)
        if not asset_path or not os.path.exists(asset_path):
            raise ValueError(f"Asset not found: {asset_key} (resolved to {asset_path})")
            
        with open(asset_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def _render_to_string(self, template_str: str, context: Dict[str, Any]) -> str:
        template = self.env.from_string(template_str)
        return template.render(**context)
    
    def render(self, template_path: str, context: Dict[str, Any]) -> str:
        with open(template_path, 'r', encoding='utf-8') as f:
            template_str = f.read()
        return self._render_to_string(template_str, context)
"""
