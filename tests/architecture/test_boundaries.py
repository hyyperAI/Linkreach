import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "linkreach"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_presentation_layer_does_not_import_side_effect_adapters():
    forbidden = (
        "playwright",
        "smtplib",
        "pydantic_ai",
        "linkedin_cli.actions",
        "linkreach.linkedin.browser",
        "linkreach.emails.sender",
        "linkreach.contacts.service",
    )
    violations = []
    presentation_paths = [
        PACKAGE / "dashboard" / "views.py",
        PACKAGE / "dashboard" / "forms.py",
        *(PACKAGE / "dashboard" / "templatetags").glob("*.py"),
    ]
    for path in presentation_paths:
        for module in _imports(path):
            if module.startswith(forbidden):
                violations.append(f"{path.relative_to(ROOT)} imports {module}")
    assert violations == []


def test_domain_and_engine_do_not_depend_on_dashboard():
    violations = []
    for folder in ("core", "crm", "linkedin", "emails", "chat", "contacts"):
        for path in (PACKAGE / folder).rglob("*.py"):
            if "migrations" in path.parts:
                continue
            for module in _imports(path):
                if module.startswith("linkreach.dashboard"):
                    violations.append(f"{path.relative_to(ROOT)} imports {module}")
    assert violations == []


def test_automation_task_creation_stays_at_owned_boundaries():
    allowed = {
        Path("linkreach/core/scheduler.py"),
        Path("linkreach/dashboard/views.py"),  # explicit human manual reply
    }
    violations = []
    for path in PACKAGE.rglob("*.py"):
        if "migrations" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "Task.objects.create(" not in text:
            continue
        relative = path.relative_to(ROOT)
        if relative not in allowed:
            violations.append(str(relative))
    assert violations == []


def test_async_safety_is_not_disabled_globally():
    settings_text = (PACKAGE / "settings.py").read_text(encoding="utf-8")
    assert "DJANGO_ALLOW_ASYNC_UNSAFE" not in settings_text
