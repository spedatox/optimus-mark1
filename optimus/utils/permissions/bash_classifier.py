"""
Bash command classifier stub (classifier permissions are ant-only / feature-gated).
Mirrors src/utils/permissions/bashClassifier.ts (external/stub build).
"""
from __future__ import annotations

from optimus.types.permissions import ClassifierBehavior, ClassifierResult

__all__ = [
    "PROMPT_PREFIX",
    "extract_prompt_description",
    "create_prompt_rule_content",
    "is_classifier_permissions_enabled",
    "get_bash_prompt_deny_descriptions",
    "get_bash_prompt_ask_descriptions",
    "get_bash_prompt_allow_descriptions",
    "classify_bash_command",
    "generate_generic_description",
]

PROMPT_PREFIX = "prompt:"


def extract_prompt_description(rule_content: str | None) -> str | None:
    """Extract a prompt description from a rule content string. Returns None in stub."""
    return None


def create_prompt_rule_content(description: str) -> str:
    """Creates a prompt rule content string from a description."""
    return f"{PROMPT_PREFIX} {description.strip()}"


def is_classifier_permissions_enabled() -> bool:
    """Returns True if classifier permissions are enabled. Always False in stub."""
    return False


def get_bash_prompt_deny_descriptions(context: object) -> list[str]:
    """Returns deny descriptions for bash prompt classifier. Empty in stub."""
    return []


def get_bash_prompt_ask_descriptions(context: object) -> list[str]:
    """Returns ask descriptions for bash prompt classifier. Empty in stub."""
    return []


def get_bash_prompt_allow_descriptions(context: object) -> list[str]:
    """Returns allow descriptions for bash prompt classifier. Empty in stub."""
    return []


async def classify_bash_command(
    command: str,
    cwd: str,
    descriptions: list[str],
    behavior: ClassifierBehavior,
    signal: object,
    is_non_interactive_session: bool,
) -> ClassifierResult:
    """Classify a bash command. Always returns non-match in stub."""
    return ClassifierResult(
        matches=False,
        confidence="high",
        reason="This feature is disabled",
    )


async def generate_generic_description(
    command: str,
    specific_description: str | None,
    signal: object,
) -> str | None:
    """Generate a generic description. Returns specific_description or None in stub."""
    return specific_description
