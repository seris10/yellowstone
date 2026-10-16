"""Whole-tree source style and notebook output checks."""
import json

from tools.check_comment_style import check_file, style_paths


def test_whole_tree_house_style(repo_root):
    """Require the hard style rules across the maintained source tree."""
    findings = [finding for path in style_paths(repo_root)
                for finding in check_file(path, repo_root.parent)
                if finding.severity == "error"]
    assert not findings, "\n".join(
        f"{item.file}:{item.line}: [{item.rule}] {item.text}" for item in findings)


def test_notebooks_have_no_saved_outputs(repo_root):
    """Keep notebook demonstrations free of stale execution outputs."""
    for path in (repo_root / "notebooks").glob("*.ipynb"):
        notebook = json.loads(path.read_text())
        for cell in notebook["cells"]:
            if cell["cell_type"] == "code":
                assert cell.get("outputs", []) == [], path.name
                assert cell.get("execution_count") is None, path.name
