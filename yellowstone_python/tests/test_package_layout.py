"""Installed package import and library boundary checks."""
from __future__ import annotations

import ast
import os
import subprocess
import sys


def test_package_and_tools_import_outside_checkout(tmp_path):
    """Import the installed package and CLI modules from an unrelated working directory."""
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    result = subprocess.run([sys.executable, "-c",
        "import yellowstone_python; import yellowstone_python.observations.met; import tools.hot_lowflow"],
        cwd=tmp_path, env=environment, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_library_has_no_tool_imports(repo_root):
    """Keep command-line tool dependencies outside the model package."""
    for path in (repo_root / "yellowstone_python").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module == "tools" or (node.module or "").startswith("tools.")), path
            elif isinstance(node, ast.Import):
                assert all(alias.name != "tools" and not alias.name.startswith("tools.")
                           for alias in node.names), path
