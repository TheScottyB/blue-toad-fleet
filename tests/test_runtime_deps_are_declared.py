"""
Every module the server imports, against the requirements the image installs.

Revision blue-toad-fleet-00018-974 built clean and then died on startup with
`ModuleNotFoundError: No module named 'PIL'`. src/appraiser/containers.py had
imported Pillow since the container-decomposition work, and Pillow was declared
in requirements-dev.txt — so it was present in every developer venv, present in
CI, and absent from the only file the Dockerfile pip-installs. Nothing that runs
before a deploy could see the gap: the suite passes, the image builds, and the
failure appears five minutes later in a revision that never serves a request.

This test is that five minutes, spent in a tenth of a second. It reads the
requirements file out of the Dockerfile rather than hardcoding a name, because
the whole defect was a second requirements file that looked like it counted.
"""

import ast
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = ROOT / "Dockerfile"

# Import name -> distribution names that would satisfy it. Only needed where the
# two differ; anything not listed is assumed to match its own name.
DISTRIBUTIONS = {
    "PIL": {"pillow"},
    "google": {
        "google-genai", "google-auth", "google-cloud-aiplatform",
        "google-cloud-firestore", "google-cloud-storage",
    },
    "yaml": {"pyyaml"},
    "dateutil": {"python-dateutil"},
    "cv2": {"opencv-python", "opencv-python-headless"},
}


def _installed_requirements_file():
    """The requirements file the image actually installs, per the Dockerfile."""
    m = re.search(r"pip install[^\n]*?-r\s+(\S+)", DOCKERFILE.read_text())
    return ROOT / m.group(1) if m else None


def _declared(req_path):
    names = set()
    for line in req_path.read_text().splitlines():
        line = line.split("#")[0].strip()
        if line and not line.startswith("-"):
            names.add(re.split(r"[<>=!~\[; ]", line)[0].strip().lower())
    return names


def _first_party():
    """Top-level names that resolve inside this repo, not on PyPI."""
    return {
        p.name for p in ROOT.iterdir()
        if p.is_dir() and not p.name.startswith((".", "_"))
        and (any(p.glob("*.py")) or (p / "__init__.py").exists())
    }


def _top_level_imports(files):
    found = {}
    for f in files:
        for node in ast.walk(ast.parse(f.read_text(), filename=str(f))):
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                mods = [node.module]
            else:
                continue
            for m in mods:
                found.setdefault(m.split(".")[0], set()).add(
                    str(f.relative_to(ROOT)))
    return found


def _resolve(module):
    """Repo file backing a dotted module name, or None if it is not ours."""
    rel = Path(*module.split("."))
    for cand in (ROOT / rel.with_suffix(".py"), ROOT / rel / "__init__.py"):
        if cand.is_file():
            return cand
    return None


def _imported_modules(path):
    """Dotted module names imported at top level by one file."""
    out = []
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.append(node.module)
            # `from pkg.mod import name` may also name submodules
            out += [f"{node.module}.{a.name}" for a in node.names]
    return out


def _runtime_files():
    """Files actually reachable by import from the app, walked transitively.

    Deliberately a graph walk and not a directory glob. scripts/ holds one
    module the server imports and a pile of local probes that import matplotlib,
    numpy and websockets; globbing the directory would demand all three in the
    production image and train everyone to ignore this test.
    """
    queue = sorted((ROOT / "src").rglob("*.py"))
    seen = set(queue)
    while queue:
        current = queue.pop()
        for module in _imported_modules(current):
            target = _resolve(module)
            if target and target not in seen:
                seen.add(target)
                queue.append(target)
    return sorted(seen)


class TestTheImageCanImportWhatTheServerImports:
    def test_the_dockerfile_names_a_requirements_file(self):
        assert _installed_requirements_file() is not None, (
            "could not find `pip install -r <file>` in the Dockerfile; this "
            "guard cannot tell which requirements the image installs")

    def test_every_runtime_import_is_declared(self):
        req = _installed_requirements_file()
        declared = _declared(req)
        local = _first_party()
        missing = {}

        for mod, users in sorted(_top_level_imports(_runtime_files()).items()):
            if mod in sys.stdlib_module_names or mod in local:
                continue
            candidates = DISTRIBUTIONS.get(mod, {mod.lower()})
            if not (candidates & declared):
                missing[mod] = (sorted(candidates), sorted(users))

        assert not missing, "\n".join(
            [f"imports absent from {req.name} — the image will not start:"]
            + [f"  {m}  (needs one of {c})  imported by {', '.join(u)}"
               for m, (c, u) in missing.items()])
