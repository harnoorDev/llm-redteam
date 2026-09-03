"""Native tool registry — PentAGI/sliver tool-driver pattern.

Auto-detects what's installed, runs it with a timeout, captures output.
Missing tools are never fatal: every check has a zero-dep fallback.
"""
from __future__ import annotations

import shutil
import subprocess

KNOWN_TOOLS = [
    # network / service recon
    "nmap", "masscan",
    # web/API probing
    "httpx", "nuclei", "ffuf", "gobuster", "nikto", "whatweb", "wafw00f",
    # TLS & injection
    "testssl.sh", "sqlmap",
    # osint / subdomains
    "subfinder", "amass",
    # brute force
    "hydra",
    # universal
    "curl",
]

_TOOL_URL_FLAGS = {
    "httpx": ["-u"],     # projectdiscovery httpx
    "nikto": ["-h"],
    "whatweb": [],
}


class ToolRegistry:
    def __init__(self, extra_paths: list[str] | None = None):
        self._cache: dict[str, bool] = {}
        self.extra_paths = extra_paths or []

    def available(self, name: str | None = None) -> bool | list[str]:
        if name is None:
            return [t for t in KNOWN_TOOLS if shutil.which(t)]
        if name in self._cache:
            return self._cache[name]
        found = shutil.which(name) is not None
        self._cache[name] = found
        return found

    def run(self, name: str, args: list[str], timeout_s: int = 60) -> dict:
        if not self.available(name):
            return {"available": False, "tool": name, "returncode": -1,
                    "stdout": "", "stderr": "tool not installed"}
        try:
            proc = subprocess.run(
                [name, *args], capture_output=True, text=True,
                timeout=timeout_s, check=False)
            return {"available": True, "name": name,
                    "returncode": proc.returncode,
                    "stdout": proc.stdout, "stderr": proc.stderr}
        except subprocess.TimeoutExpired:
            return {"available": True, "name": name, "returncode": -9,
                    "stdout": "", "stderr": f"timeout after {timeout_s}s"}
        except OSError as e:
            return {"available": True, "name": name, "returncode": -1,
                    "stdout": "", "stderr": str(e)}
