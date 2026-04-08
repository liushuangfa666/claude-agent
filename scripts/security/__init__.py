"""
Security Module - 权限系统增强
"""
from .auto_classifier import BLOCK_PATTERNS, AutoClassifier, Classification
from .bash_sandbox import BashSandbox, ExecResult, ValidationResult
from .path_protection import PROTECTED_PATHS, ProtectedPathManager
from .path_validation import PathValidationResult, PathValidator
from .permission_modes import PermissionMode, PermissionModeManager

__all__ = [
    "ProtectedPathManager",
    "PROTECTED_PATHS",
    "BashSandbox",
    "ValidationResult",
    "ExecResult",
    "PathValidator",
    "PathValidationResult",
    "AutoClassifier",
    "Classification",
    "BLOCK_PATTERNS",
    "PermissionMode",
    "PermissionModeManager",
]
