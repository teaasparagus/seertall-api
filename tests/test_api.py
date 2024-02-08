import datetime
import io
import json
from pathlib import Path

import pytest
from faker import Faker
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session

from seertall_api import database, main
from seertall_api.database import create_db_and_tables

fake = Faker()
SERIES_IDS = [fake.text(max_nb_chars=12).replace(" ", "-") for _ in range(5)]
TEST_CSV_NUM_DAYS = 5
SCREEN_TYPES = ["desktop", "tablet", "mobile"]


@pytest.fixture
def test_app():
    return main.app


@pytest.fixture
def client(test_app: FastAPI):
    return TestClient(test_app)


def test_root(client: TestClient):
    res = client.get("/", follow_redirects=False)
    assert res.status_code == 301, res.text
    assert res.headers.get("Location") == "/docs"


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("DB_URL", f"sqlite:////{tmp_path/'db.sqlite'}")
    create_db_and_tables()
    yield Session(database.engine)


@pytest.fixture
def csv_file_like():
    headers = "seriesId,date,screen,views"
    content = headers + "\n"
    start_date = datetime.date(2024, 1, 1)

    for i in range(TEST_CSV_NUM_DAYS):
        date = (start_date + datetime.timedelta(days=i)).strftime("%Y%m%d")
        for series_id in SERIES_IDS:
            for screen in SCREEN_TYPES:
                views = fake.random_int(min=0, max=10000)
                row = f"{series_id},{date},{screen},{views}\n"
                content += row
    return io.BytesIO(content.encode())


def test_ingest_csv(db: Session, csv_file_like: io.BytesIO, client: TestClient):
    res = client.post(
        "/ingest", files={"file": ("filename", csv_file_like, "text/csv")}
    )

    assert res.status_code == 202, res.text

    series_in_db = [r[0] for r in db.execute(text("SELECT name FROM series")).all()]
    assert set(series_in_db) == set(SERIES_IDS)

    row_count_day_view = db.execute(text("SELECT COUNT(*) FROM dayview")).fetchone()[0]
    assert row_count_day_view == len(SERIES_IDS) * len(SCREEN_TYPES) * TEST_CSV_NUM_DAYS


def test_get_popular_weekday_cached_response(client: TestClient):
    expected = [{"rank": 0, "weekday": "monday", "weekday_number": 1, "view_count": 123}]
    class MockCache:
        def get(self, *args, **kwargs):
            return json.dumps(expected)

    client.app.dependency_overrides[main.get_cache_client] = lambda: MockCache()

    res = client.get("/series/popularityByWeekday?series_id=1")
    assert res.json() == expected
