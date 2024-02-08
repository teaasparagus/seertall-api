import datetime
import enum

from sqlmodel import Field, SQLModel, UniqueConstraint


class Series(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True)


class ScreenEnum(enum.StrEnum):
    desktop = "desktop"
    tablet = "tablet"
    mobile = "mobile"


class DayView(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    day: datetime.date = Field()
    series_id: int = Field(foreign_key="series.id")
    screen: ScreenEnum = Field()
    views: int = Field()

    __table_args__ = (UniqueConstraint("day", "series_id", "screen"),)
