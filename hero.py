import os
import sys
from pathlib import Path


def resource_path(relative_path: str) -> Path:
    """
    Resolve a path relative to the project root, both during normal execution
    and when running as a PyInstaller-bundled .exe.

    PyInstaller extracts bundled files to a temp directory stored in
    sys._MEIPASS at runtime.  When running from source, we fall back to
    the directory that contains this file (hero.py lives at the project root).
    """
    base = getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)
    return Path(base) / relative_path


class Hero:
    """Represents a hero with all associated assets."""
    
    def __init__(self, name: str, assets_dir: str = "assets/heroes", volume: float = 1.0):
        """
        Initialize a Hero object.
        
        Args:
            name: The hero's folder name (e.g., "abrams")
            assets_dir: Base directory containing hero folders
            volume: Voice line playback volume for this hero (0.0 to 1.0)
        """
        self.name = name.lower()
        self.volume = max(0.0, min(1.0, volume))  # Clamp to valid range
        self.assets_dir = resource_path(assets_dir) / self.name
        
        # Define all asset paths
        self.background = self.assets_dir / "background.png"
        self.card = self.assets_dir / "card.png"
        self.crit = self.assets_dir / "crit.png"
        self.gloat = self.assets_dir / "gloat.png"
        self.icon = self.assets_dir / "icon.png"
        self.name_svg = self.assets_dir / "name.svg"
        self.render = self.assets_dir / "render.png"
        
        # Voice line directories
        self.voice_lines_dir = self.assets_dir / "voice_lines"
        self.voice_select = self.voice_lines_dir / "select"
        self.voice_bans = self.voice_lines_dir / "ban"
        
        # Validate that the hero folder exists
        if not self.assets_dir.exists():
            raise ValueError(f"Hero folder not found: {self.assets_dir}")
    
    def get_asset(self, asset_type: str) -> Path:
        """
        Get the path to a specific asset by type.
        
        Args:
            asset_type: One of "background", "card", "crit", "gloat", "icon", 
                       "minimap", "name", "render"
        
        Returns:
            Path object to the asset
        """
        assets = {
            "background": self.background,
            "card": self.card,
            "crit": self.crit,
            "gloat": self.gloat,
            "icon": self.icon,
            "name": self.name_svg,
            "render": self.render,
        }
        
        if asset_type not in assets:
            raise ValueError(f"Unknown asset type: {asset_type}")
        
        asset_path = assets[asset_type]
        if not asset_path.exists():
            raise FileNotFoundError(f"Asset not found: {asset_path}")
        
        return asset_path
    
    def get_voice_lines(self, voice_type: str) -> list:
        """
        Get a list of voice line files.
        
        Args:
            voice_type: Either "select" or "ban"
        
        Returns:
            List of Path objects to .mp3 files
        """
        if voice_type == "select":
            voice_dir = self.voice_select
        elif voice_type == "ban":
            voice_dir = self.voice_bans
        else:
            raise ValueError(f"Unknown voice type: {voice_type}")
        
        if not voice_dir.exists():
            return []
        
        return sorted([f for f in voice_dir.glob("*.mp3")])
    
    def __repr__(self) -> str:
        return f"Hero(name='{self.name}', path='{self.assets_dir}')"
