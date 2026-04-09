"""
Environment detection and path utilities.
Mirrors src/utils/env.ts

Provides:
  - get_global_claude_file()  — path to ~/.claude.json
  - env                       — platform/terminal detection object
  - detect_terminal()         — terminal name from environment
  - detect_deployment_environment() — cloud/CI platform detection
"""
from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Literal

Platform = Literal["win32", "darwin", "linux"]

JETBRAINS_IDES = [
    "pycharm", "intellij", "webstorm", "phpstorm", "rubymine",
    "clion", "goland", "rider", "datagrip", "appcode", "dataspell",
    "aqua", "gateway", "fleet", "jetbrains", "androidstudio",
]


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_global_claude_file() -> str:
    """
    Return the path to the global Claude config file (~/.claude.json).
    Checks for legacy .config.json first for backward compat.
    """
    from optimus.utils.env_utils import get_claude_config_home_dir

    config_home = get_claude_config_home_dir()

    # Legacy fallback
    legacy = Path(config_home) / ".config.json"
    if legacy.exists():
        return str(legacy)

    # Determine oauth suffix (mirrors fileSuffixForOauthConfig())
    suffix = _get_oauth_config_suffix()
    filename = f".claude{suffix}.json"

    config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if config_dir:
        return str(Path(config_dir) / filename)
    return str(Path.home() / filename)


def _get_oauth_config_suffix() -> str:
    """Return the config file suffix based on OAuth environment."""
    try:
        from optimus.constants.oauth import file_suffix_for_oauth_config
        return file_suffix_for_oauth_config()
    except ImportError:
        return ""


# ---------------------------------------------------------------------------
# SSH detection
# ---------------------------------------------------------------------------

def is_ssh_session() -> bool:
    return bool(
        os.environ.get("SSH_CONNECTION")
        or os.environ.get("SSH_CLIENT")
        or os.environ.get("SSH_TTY")
    )


# ---------------------------------------------------------------------------
# WSL detection
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def is_wsl_environment() -> bool:
    try:
        return Path("/proc/sys/fs/binfmt_misc/WSLInterop").exists()
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Terminal detection
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def detect_terminal() -> str | None:
    env = os.environ

    if env.get("CURSOR_TRACE_ID"):
        return "cursor"
    askpass = env.get("VSCODE_GIT_ASKPASS_MAIN", "")
    if "cursor" in askpass:
        return "cursor"
    if "windsurf" in askpass:
        return "windsurf"
    if "antigravity" in askpass:
        return "antigravity"

    bundle_id = (env.get("__CFBundleIdentifier") or "").lower()
    if "vscodium" in bundle_id:
        return "codium"
    if "windsurf" in bundle_id:
        return "windsurf"
    if "com.google.android.studio" in bundle_id:
        return "androidstudio"
    if bundle_id:
        for ide in JETBRAINS_IDES:
            if ide in bundle_id:
                return ide

    if env.get("VisualStudioVersion"):
        return "visualstudio"

    if env.get("TERMINAL_EMULATOR") == "JetBrains-JediTerm":
        return "pycharm"

    if env.get("TERM") == "xterm-ghostty":
        return "ghostty"
    if (env.get("TERM") or "").startswith("kitty") or "kitty" in (env.get("TERM") or ""):
        return "kitty"
    if env.get("TERM_PROGRAM"):
        return env["TERM_PROGRAM"]
    if env.get("TMUX"):
        return "tmux"
    if env.get("STY"):
        return "screen"
    if env.get("KONSOLE_VERSION"):
        return "konsole"
    if env.get("GNOME_TERMINAL_SERVICE"):
        return "gnome-terminal"
    if env.get("XTERM_VERSION"):
        return "xterm"
    if env.get("VTE_VERSION"):
        return "vte-based"
    if env.get("TERMINATOR_UUID"):
        return "terminator"
    if env.get("KITTY_WINDOW_ID"):
        return "kitty"
    if env.get("ALACRITTY_LOG"):
        return "alacritty"
    if env.get("TILIX_ID"):
        return "tilix"

    # Windows
    if env.get("WT_SESSION"):
        return "windows-terminal"
    if env.get("SESSIONNAME") and env.get("TERM") == "cygwin":
        return "cygwin"
    if env.get("MSYSTEM"):
        return (env["MSYSTEM"] or "").lower()
    if env.get("ConEmuANSI") or env.get("ConEmuPID") or env.get("ConEmuTask"):
        return "conemu"

    # WSL
    if env.get("WSL_DISTRO_NAME"):
        return f"wsl-{env['WSL_DISTRO_NAME']}"

    if is_ssh_session():
        return "ssh-session"

    term = env.get("TERM", "")
    if term:
        if "alacritty" in term:
            return "alacritty"
        if "rxvt" in term:
            return "rxvt"
        if "termite" in term:
            return "termite"
        return term

    if not sys.stdout.isatty():
        return "non-interactive"

    return None


# ---------------------------------------------------------------------------
# Deployment environment detection
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def detect_deployment_environment() -> str:
    env = os.environ

    def truthy(v: str | None) -> bool:
        return v is not None and v.lower() in ("1", "true", "yes")

    if truthy(env.get("CODESPACES")):
        return "codespaces"
    if env.get("GITPOD_WORKSPACE_ID"):
        return "gitpod"
    if env.get("REPL_ID") or env.get("REPL_SLUG"):
        return "replit"
    if env.get("PROJECT_DOMAIN"):
        return "glitch"
    if truthy(env.get("VERCEL")):
        return "vercel"
    if env.get("RAILWAY_ENVIRONMENT_NAME") or env.get("RAILWAY_SERVICE_NAME"):
        return "railway"
    if truthy(env.get("RENDER")):
        return "render"
    if truthy(env.get("NETLIFY")):
        return "netlify"
    if env.get("DYNO"):
        return "heroku"
    if env.get("FLY_APP_NAME") or env.get("FLY_MACHINE_ID"):
        return "fly.io"
    if truthy(env.get("CF_PAGES")):
        return "cloudflare-pages"
    if env.get("DENO_DEPLOYMENT_ID"):
        return "deno-deploy"
    if env.get("AWS_LAMBDA_FUNCTION_NAME"):
        return "aws-lambda"
    if env.get("AWS_EXECUTION_ENV") == "AWS_ECS_FARGATE":
        return "aws-fargate"
    if env.get("AWS_EXECUTION_ENV") == "AWS_ECS_EC2":
        return "aws-ecs"
    try:
        uuid = Path("/sys/hypervisor/uuid").read_text().strip().lower()
        if uuid.startswith("ec2"):
            return "aws-ec2"
    except OSError:
        pass
    if env.get("K_SERVICE"):
        return "gcp-cloud-run"
    if env.get("GOOGLE_CLOUD_PROJECT"):
        return "gcp"
    if env.get("WEBSITE_SITE_NAME") or env.get("WEBSITE_SKU"):
        return "azure-app-service"
    if env.get("AZURE_FUNCTIONS_ENVIRONMENT"):
        return "azure-functions"
    if (env.get("APP_URL") or "").endswith("ondigitalocean.app"):
        return "digitalocean-app-platform"
    if env.get("SPACE_CREATOR_USER_ID"):
        return "huggingface-spaces"
    if truthy(env.get("GITHUB_ACTIONS")):
        return "github-actions"
    if truthy(env.get("GITLAB_CI")):
        return "gitlab-ci"
    if env.get("CIRCLECI"):
        return "circleci"
    if env.get("BUILDKITE"):
        return "buildkite"
    if truthy(env.get("CI")):
        return "ci"
    if env.get("KUBERNETES_SERVICE_HOST"):
        return "kubernetes"
    try:
        if Path("/.dockerenv").exists():
            return "docker"
    except OSError:
        pass

    platform = _detect_platform()
    if platform == "darwin":
        return "unknown-darwin"
    if platform == "linux":
        return "unknown-linux"
    if platform == "win32":
        return "unknown-win32"
    return "unknown"


# ---------------------------------------------------------------------------
# Platform helpers
# ---------------------------------------------------------------------------

def _detect_platform() -> Platform:
    if sys.platform == "win32":
        return "win32"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def get_host_platform_for_analytics() -> Platform:
    override = os.environ.get("CLAUDE_CODE_HOST_PLATFORM")
    if override in ("win32", "darwin", "linux"):
        return override  # type: ignore[return-value]
    return _detect_platform()


# ---------------------------------------------------------------------------
# env object (mirrors TS `export const env = { ... }`)
# ---------------------------------------------------------------------------

class _Env:
    """Immutable env descriptor — mirrors the TypeScript `env` export."""

    def __init__(self) -> None:
        self.platform: Platform = _detect_platform()
        self.arch: str = _get_arch()
        self.is_ci: bool = bool(os.environ.get("CI"))
        self._terminal: str | None = detect_terminal()

    @property
    def terminal(self) -> str | None:
        return self._terminal

    def is_ssh(self) -> bool:
        return is_ssh_session()

    def is_wsl_environment(self) -> bool:
        return is_wsl_environment()

    def is_conductor(self) -> bool:
        return os.environ.get("__CFBundleIdentifier") == "com.conductor.app"

    def detect_deployment_environment(self) -> str:
        return detect_deployment_environment()

    async def has_internet_access(self) -> bool:
        import asyncio
        import socket
        loop = asyncio.get_event_loop()
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, _check_connection),
                timeout=1.0,
            )
            return True
        except Exception:
            return False


def _get_arch() -> str:
    import platform
    machine = platform.machine().lower()
    if machine in ("amd64", "x86_64"):
        return "x64"
    if machine in ("arm64", "aarch64"):
        return "arm64"
    return machine


def _check_connection() -> None:
    import socket
    socket.setdefaulttimeout(1)
    socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("1.1.1.1", 80))


env = _Env()
