import ast
from pathlib import Path

API_ROOT = Path(__file__).parents[1] / "src" / "clipper"
WEB_ROOT = Path(__file__).parents[2] / "web"

FORBIDDEN_PURE_IMPORTS = (
    "fastapi",
    "sqlalchemy",
    "subprocess",
    "clipper.api",
    "clipper.persistence",
)


def imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def assert_pure(path: Path) -> None:
    violations = [
        module for module in imported_modules(path) if module.startswith(FORBIDDEN_PURE_IMPORTS)
    ]
    assert not violations, f"{path.relative_to(API_ROOT)} imports adapter code: {violations}"


def test_domain_packages_do_not_depend_on_framework_or_persistence() -> None:
    for package in ("captions", "editorial", "transcription"):
        for path in (API_ROOT / package).glob("*.py"):
            assert_pure(path)


def test_pure_rendering_and_media_policy_do_not_execute_processes() -> None:
    pure_paths = [
        API_ROOT / "rendering" / "ffmpeg.py",
        API_ROOT / "rendering" / "framing.py",
        API_ROOT / "rendering" / "tracking.py",
        API_ROOT / "media" / "errors.py",
        API_ROOT / "media" / "ingestion.py",
        API_ROOT / "media" / "tools.py",
    ]
    for path in pure_paths:
        assert_pure(path)


def test_subprocesses_never_enable_a_shell() -> None:
    for path in API_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg == "shell":
                    assert not (
                        isinstance(keyword.value, ast.Constant) and keyword.value.value is True
                    ), f"{path.relative_to(API_ROOT)} enables shell execution"


def test_web_page_remains_a_small_composition_root() -> None:
    page = WEB_ROOT / "app" / "page.tsx"
    source = page.read_text()
    assert len(source.splitlines()) < 100
    assert "lib/api" not in source
    assert "useProjectWorkbench" in source
