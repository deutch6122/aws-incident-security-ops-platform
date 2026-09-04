from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from app.db.models import Base, Incident
from app.repositories import IncidentRepository


def test_models_match_all_migration_tables() -> None:
    assert set(Base.metadata.tables) == {
        "incidents",
        "incident_comments",
        "findings",
        "finding_triage",
        "alarm_events",
        "monthly_summaries",
        "audit_logs",
    }
    assert Incident.__table__.c.external_id.nullable is False
    assert Incident.__table__.c.external_id.unique is True


def test_repository_write_commits_and_refreshes() -> None:
    session = MagicMock()
    repository = IncidentRepository(session)

    created = repository.create(external_id="event-1", title="Example", severity="high")

    session.add.assert_called_once_with(created)
    session.commit.assert_called_once_with()
    session.refresh.assert_called_once_with(created)
    session.rollback.assert_not_called()


def test_repository_rolls_back_if_commit_fails() -> None:
    session = MagicMock()
    session.commit.side_effect = RuntimeError("database unavailable")
    repository = IncidentRepository(session)

    with pytest.raises(RuntimeError, match="database unavailable"):
        repository.create(external_id="event-1", title="Example", severity="high")
    session.rollback.assert_called_once_with()
