"""Config package surface for Stilyagi."""

from .load import LoadedConfig, discover_same_directory_config, load_config_file
from .path_resolution import PathResolutionError
from .resolve import ConfigResolver, ResolvedTargetConfig, resolve_config_for_path
from .schema import (
    ConfigError,
    InvalidCacheDirError,
    InvalidConfigError,
    LintConfig,
    MarkdownExtractConfig,
    NlpConfig,
    StilyagiConfig,
)

__all__ = [
    "ConfigError",
    "ConfigResolver",
    "InvalidCacheDirError",
    "InvalidConfigError",
    "LintConfig",
    "LoadedConfig",
    "MarkdownExtractConfig",
    "NlpConfig",
    "PathResolutionError",
    "ResolvedTargetConfig",
    "StilyagiConfig",
    "discover_same_directory_config",
    "load_config_file",
    "resolve_config_for_path",
]
