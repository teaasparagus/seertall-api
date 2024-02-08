import csv
import datetime
from http import HTTPStatus
from typing import Literal, Sequence

import pydantic
import sqlalchemy
import structlog
from fastapi import Depends, FastAPI, File, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlmodel import Session, select

from seertall_api import cache, database, models

logger = structlog.get_logger(__name__)
app = FastAPI(title="seertall-api")


def get_session():
    logger.debug(f"Using {database.engine}")
    with Session(database.engine) as session:
        yield session


def get_cache_client():
    client = cache.CacheClient()
    yield client


@app.on_event("startup")
def on_startup():
    database.create_db_and_tables()
    logger.debug("DB initialization success")


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/docs", status_code=HTTPStatus.MOVED_PERMANENTLY)


@app.post("/ingest", status_code=HTTPStatus.ACCEPTED, tags=["manage"])
def ingest(
    file: bytes = File(),
    session: Session = Depends(get_session),
):
    csv_reader = csv.DictReader(file.decode().splitlines())
    series: dict[str, int] = {}
    for row in csv_reader:
        series_human_id = row["seriesId"]
        date = datetime.datetime.strptime(row["date"], "%Y%m%d").date()
        screen = models.ScreenEnum(row["screen"])
        views = int(row["views"])
        if series_human_id not in series.keys():
            with session.no_autoflush:
                series_in_db = session.exec(
                    select(models.Series).where(models.Series.name == series_human_id)
                ).one_or_none()
            if series_in_db:
                assert series_in_db.id
                series[series_in_db.name] = series_in_db.id
            else:
                series_created = models.Series(name=series_human_id)
                session.add(series_created)
                session.flush()
                assert series_created.id
                series[series_human_id] = series_created.id
        series_pk = series[series_human_id]
        logger.debug(f"{series_human_id} ({series_pk}) {date} {screen}")
        session.add(
            models.DayView(
                day=date, series_id=series[series_human_id], screen=screen, views=views
            )
        )
    logger.debug(f"Adding series={session.dirty}")
    try:
        session.commit()
    except sqlalchemy.exc.IntegrityError:
        raise HTTPException(400, detail="Could not add data")
    return {"message": "ingest scheduled"}


SeriesListResponse = pydantic.RootModel[list[models.Series]]


@app.get("/series", response_model=SeriesListResponse, tags=["series"])
def list_series(
    limit: int = Query(default=5, le=10),
    offset: int = Query(default=0),
    session: Session = Depends(get_session),
) -> Sequence[models.Series]:
    series = session.exec(select(models.Series).offset(offset).limit(limit)).all()
    return series


_weekday_from_int = {
    1: "monday",
    2: "tuesday",
    3: "wednesday",
    4: "thursday",
    5: "friday",
    6: "saturday",
    7: "sunday",
}


class PopularityByWeekdayItem(pydantic.BaseModel):
    rank: int = pydantic.Field(ge=0, le=6)
    weekday: Literal[
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
    ]
    weekday_number: int = pydantic.Field(ge=1, le=7)
    view_count: int


PopularityByWeekdayResponse = pydantic.RootModel[list[PopularityByWeekdayItem]]


@app.get(
    "/series/popularityByWeekday",
    response_model=PopularityByWeekdayResponse,
    tags=["series"],
)
def get_popular_weekday(
    series_id: int = Query(...),
    start_date: datetime.date | None = Query(
        default=None, description="Inclusive (i.e. 00:00 that day)"
    ),
    end_date: datetime.date | None = Query(
        default=None, description="Inclusive (i.e. until midnight that day)"
    ),
    session: Session = Depends(get_session),
    cache_client: cache.CacheClient = Depends(get_cache_client),
):
    params = {"series_id": series_id, "start_date": start_date, "end_date": end_date}
    if (cached := cache_client.get(str(params))) is not None:
        logger.debug("Returning from cache")
        try:
            return PopularityByWeekdayResponse.model_validate_json(cached)
        except Exception:
            logger.debug("Cache invalid, fetching from DB")
    logger.debug("No cache hit")
    sql = text(
        """
        SELECT EXTRACT(isodow FROM day)::int AS weekday_num, SUM(views) AS total_views
        FROM dayview
        WHERE series_id = :series_id
            AND (:start_date IS NULL OR day >= :start_date)
            AND (:end_date IS NULL OR day <= :end_date)
        GROUP BY weekday_num
        ORDER BY total_views DESC
        """
    )
    logger.debug(f"Querying with {params}")
    query_res = session.execute(sql, params=params).fetchall()
    item_list: list[PopularityByWeekdayItem] = []
    for rank, item in enumerate(query_res):
        weekday_num, total_views = item.tuple()
        item_list.append(
            PopularityByWeekdayItem(
                rank=rank,
                weekday=_weekday_from_int[weekday_num],
                weekday_number=weekday_num,
                view_count=total_views,
            )
        )
    response = PopularityByWeekdayResponse(item_list)
    cache_client.set(str(params), response.model_dump_json())
    return response


class SeriesWithViews(pydantic.BaseModel):
    id: int
    name: str
    rank: int
    view_count: int


SeriesByViews = pydantic.RootModel[list[SeriesWithViews]]


@app.get("/series/byViews", response_model=SeriesByViews, tags=["series"])
def get_series_by_views(
    start_date: datetime.date | None = Query(
        default=None, description="Inclusive (i.e. 00:00 that day)"
    ),
    end_date: datetime.date | None = Query(
        default=None, description="Inclusive (i.e. until midnight that day)"
    ),
    limit: int = Query(default=5, le=10),
    offset: int = Query(default=0),
    session: Session = Depends(get_session),
):
    sql = text(
        """
        SELECT series_id, series.name, SUM(views) AS total_views
        FROM dayview
        JOIN series ON series.id = series_id
        WHERE (:start_date IS NULL OR day >= :start_date)
            AND (:end_date IS NULL OR day <= :end_date)
        GROUP BY series_id, series.name
        ORDER BY total_views DESC
        LIMIT :limit OFFSET :offset;
        """
    )
    params = {
        "start_date": start_date,
        "end_date": end_date,
        "limit": limit,
        "offset": offset,
    }
    logger.debug(f"Querying with {params}")
    query_res = session.execute(sql, params=params).fetchall()
    response: list[SeriesWithViews] = []
    for rank, item in enumerate(query_res):
        series_id, series_name, total_views = item.tuple()
        response.append(
            SeriesWithViews(
                id=series_id, name=series_name, rank=rank, view_count=total_views
            )
        )
    return response
