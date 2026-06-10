"""
Tests for Renderer and asset reference functionality.
"""

import os
import tempfile
import shutil
from unittest.mock import MagicMock
from pathlib import Path

from runtime.renderer import Renderer
from runtime.unified_loader import UnifiedLoader


def create_test_assets():
    temp_dir = tempfile.mkdtemp()
    
    base_path = os.path.join(temp_dir, "base")
    os.makedirs(base_path)
    
    diagrams_path = os.path.join(base_path, "diagrams")
    os.makedirs(diagrams_path)
    with open(os.path.join(diagrams_path, "software_arch.md"), "w") as f:
        f.write("# Software Architecture\n\nThis is the software architecture diagram content.")
    
    domain_path = os.path.join(temp_dir, "llm_corpus")
    os.makedirs(domain_path)
    
    with open(os.path.join(domain_path, "pack.yaml"), "w") as f:
        f.write("id: llm_corpus\nkind: domain\nrequires_commons:\n  - base\n")
    
    return temp_dir, base_path, domain_path

def test_asset_reference_resolution():
    """Test that asset references are properly resolved."""
    temp_dir, base_path, domain_path = create_test_assets()
    
    try:
        loader = UnifiedLoader(domain_path, [base_path])
        renderer = Renderer(loader)
        
        asset_path = loader.get_asset_path("base:diagrams/software_arch.md")
        assert asset_path is not None
        assert os.path.exists(asset_path)
        
        asset_content = renderer._asset_ref("base:diagrams/software_arch.md")
        assert "Software Architecture" in asset_content
        assert "This is the software architecture diagram content." in asset_content
        
        try:
            renderer._asset_ref("invalid_format")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass
        
        try:
            renderer._asset_ref("base:diagrams/non_existent.md")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass
        
    finally:
        shutil.rmtree(temp_dir)


def test_renderer_with_asset_template():
    """Test that renderer can use asset references in templates."""
    temp_dir, base_path, domain_path = create_test_assets()
    
    try:
        loader = UnifiedLoader(domain_path, [base_path])
        renderer = Renderer(loader)
        
        template_str = """
## Software Architecture

{{ asset("base:diagrams/software_arch.md") }}
"""
        
        result = renderer._render_to_string(template_str, {})
        
        assert "Software Architecture" in result
        assert "This is the software architecture diagram content." in result
        
    finally:
        shutil.rmtree(temp_dir)
"""
