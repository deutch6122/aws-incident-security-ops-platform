import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_requirements_are_exactly_pinned() -> None:
    for name in ("requirements.txt", "requirements-test.txt"):
        lines = [line.strip() for line in (ROOT / name).read_text().splitlines() if line.strip() and not line.startswith("-r")]
        assert lines
        assert all("==" in line and not any(marker in line for marker in (">=", "<=", "~=", "*")) for line in lines)


def test_dockerfile_security_baseline() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "FROM python:3.12.10-slim-bookworm" in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "COPY --chown=app:app app ./app" in dockerfile
    assert not any(word in dockerfile for word in ("ARG SECRET", "ARG PASSWORD", "COPY . "))


def test_imports_do_not_create_aws_clients_or_database_engines() -> None:
    for source_path in (ROOT / "app").rglob("*.py"):
        tree = ast.parse(source_path.read_text())
        top_level_calls = [node for node in tree.body if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)]
        rendered = "\n".join(ast.unparse(node) for node in top_level_calls)
        assert "boto3.client" not in rendered
        assert "create_engine" not in rendered


def test_task_7_contract_placeholder_is_preserved() -> None:
    # Task 8 adds business routers but must not remove the Task 7 contract routes.
    contracts = (ROOT / "app" / "contracts.py").read_text()
    assert 'prefix="/_contracts"' in contracts


def test_task_8_business_routers_are_registered() -> None:
    # Business routes live in the dedicated routers package (Task 8), each
    # guarded by the shared bearer dependency.
    routers_dir = ROOT / "app" / "routers"
    assert routers_dir.is_dir()
    sources = {path.name: path.read_text() for path in routers_dir.glob("*.py")}
    assert 'prefix="/dashboard"' in sources["dashboard.py"]
    assert '"/summary"' in sources["dashboard.py"]
    assert 'prefix="/incidents"' in sources["incidents.py"]
    assert '"/{incident_id}/status"' in sources["incidents.py"]
    assert 'prefix="/findings"' in sources["findings.py"]
    assert 'prefix="/summaries"' in sources["summaries.py"]
    for source in sources.values():
        if 'APIRouter(' in source:
            assert "require_bearer_auth" in source
