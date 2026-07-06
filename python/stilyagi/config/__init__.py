"""Config package surface for Stilyagi."""

from .load import LoadedConfig, discover_same_directory_config, load_config_file
from .resolve import resolve_config_for_path
from .schema import (
    InvalidCacheDirError,
    InvalidConfigError,
    LintConfig,
    MarkdownExtractConfig,
    NlpConfig,
    StilyagiConfig,
)

__all__ = [
    "InvalidCacheDirError",
    "InvalidConfigError",
    "LintConfig",
    "LoadedConfig",
    "MarkdownExtractConfig",
    "NlpConfig",
    "StilyagiConfig",
    "discover_same_directory_config",
    "load_config_file",
    "resolve_config_for_path",
]
