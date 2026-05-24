"""
UnifiedLoader module for loading domain and commons packs.

Handles dual-channel loading of domain and commons packs with asset resolution.
"""

import os
from typing import List, Dict, Any, Optional
from pathlib import Path


class UnifiedLoader:
    """Dual-channel loader for domain and commons packs.
    
    Loads domain packs (with their own schema, rules, skills) and commons packs
    (providing reusable assets and skills) with asset referencing capability.
    """
    
    def __init__(self, domain_pack: str, commons: List[str] = None):
        """Initialize unified loader.
        
        Args:
            domain_pack: Path to domain pack directory
            commons: List of paths to commons packs (optional)
        """
        self.domain_pack_path: str = domain_pack
        self.commons_paths: List[str] = commons or []
        
        self.domain_config: Dict[str, Any] = self._load_pack_config(domain_pack)
        self.commons_configs: Dict[str, Dict[str, Any]] = {}
        for commons_path in self.commons_paths:
            self.commons_configs[os.path.basename(commons_path)] = self._load_pack_config(commons_path)
    
    def _load_pack_config(self, pack_path: str) -> Dict[str, Any]:
        config_path = os.path.join(pack_path, "pack.yaml")
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"pack.yaml not found in {pack_path}")
            
        return {"id": os.path.basename(pack_path), "kind": "domain"}
    
    def get_asset_path(self, asset_key: str) -> Optional[str]:
        """Resolve asset reference like "base:diagrams/software_arch.md" to absolute path.
        
        Args:
            asset_key: Asset reference in format "pack_name:rel_path"
            
        Returns:
            str: Absolute path to asset file, or None if not found
        """
        if ":" not in asset_key:
            return None
            
        pack_name, rel_path = asset_key.split(":", 1)
        
        domain_asset_path = os.path.join(self.domain_pack_path, rel_path)
        if os.path.exists(domain_asset_path):
            return domain_asset_path
        
        for commons_path in self.commons_paths:
            if os.path.basename(commons_path) == pack_name:
                commons_asset_path = os.path.join(commons_path, rel_path)
                if os.path.exists(commons_asset_path):
                    return commons_asset_path
        
        return None
"""
