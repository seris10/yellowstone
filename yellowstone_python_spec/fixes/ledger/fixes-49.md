# fixes-49 ledger
Doc: fixes/fixes-49-comment-and-docstring-house-style.md | read2026-10-13 | targets: yellowstone_python/AGENTS.md sha256:ee3603784f2b; yellowstone_python/tests/test_check_comment_style.py sha256:a4582ba6b6d2; yellowstone_python/tests/test_equations.py sha256:f704946ac681; yellowstone_python/tests/test_repository_style.py sha256:3d5cd029f4ca; yellowstone_python/tests/test_stressor_integration.py sha256:f018677b3133; yellowstone_python/tools/check_comment_style.py sha256:d0b90cf767e7; yellowstone_python/yellowstone_python/aquatic/aquatic_foodweb.py sha256:406e2cfe6094; yellowstone_python/yellowstone_python/aquatic/fish.py sha256:94aa2107d78b
Summary: 7 items: 7 implemented,0 shortcut,0 partial,0 missing,0 superseded,0 conflicts

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 1 | House style (add to `AGENTS.md` section 2) | implemented | yellowstone_python/AGENTS.md:16 | AGENTS rules and examples describe module/function docstrings, comments, banners, citations, units, ASCII and provenance classes. | medium |
| 2 | Remove process references | implemented | yellowstone_python/tools/check_comment_style.py:46; yellowstone_python/tests/test_stressor_integration.py:1; yellowstone_python/tests/test_equations.py:8 | Owned process labels removed, integration file renamed by subject, descriptive equation expectations updated. Other owners cleaned their source strings. | medium |
| 3 | Rewrite session narration in citations | implemented | yellowstone_python/tools/check_comment_style.py:48; yellowstone_python/yellowstone_python/aquatic/fish.py:83; yellowstone_python/yellowstone_python/aquatic/aquatic_foodweb.py:19; yellowstone_python/tests/test_check_comment_style.py:96 | Owned source citations contain evidence class rather than session narration; findings forwarded for model owners to clean. | medium |
| 4 | Fix history narration and stale statements | implemented | yellowstone_python/tools/check_comment_style.py:47; yellowstone_python/tests/test_check_comment_style.py:79 | Owned history/defensive narration and malformed shortened docstrings rewritten as current behavior. | medium |
| 5 | Extend the checker | implemented | yellowstone_python/tools/check_comment_style.py:88; yellowstone_python/tools/check_comment_style.py:195; yellowstone_python/tests/test_check_comment_style.py:114; yellowstone_python/tests/test_check_comment_style.py:145 | All requested checker rules implemented with AST-scoped comments/docstrings/test names/provenance/help/exceptions; vocabulary/citation rules remain warnings. Lowercase milestone suffixes caught; DOI capitals and ordinary domain tokens have false-positive regression coverage. | medium |
| 6 | Check Markdown and notebooks | implemented | yellowstone_python/tools/check_comment_style.py:134; yellowstone_python/tools/check_comment_style.py:152; yellowstone_python/tests/test_check_comment_style.py:125 | Markdown prose outside code fences/inline code and notebook markdown checked; planted positive/negative tests pass. | medium |
| 7 | Run the checker on the whole tree in the verify step | implemented | yellowstone_python/tools/check_comment_style.py:251; yellowstone_python/tests/test_repository_style.py:7; yellowstone_python/AGENTS.md:117 | Whole maintained tree gate is part of pytest; latest standalone gate377files0findings. | medium |

## Cross-project issues
- Python runtime frames are the model authority. Godot interpolates published/live states and displays their provenance.
- Current internal documents remain tracked by user decision. The future public export excludes generated prose.

## Scientific validity flags
- Scientific claims remain not_yet_accepted; authored/transferred values retain their classes and unknown uncertainty.
- Fish-rig redistribution rights and human visual acceptance remain unverified.
