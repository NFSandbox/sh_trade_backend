from pydantic import BaseModel
import time
from datetime import datetime, timedelta
from enum import Enum


class BackendInfoOut(BaseModel):
    version: str
    on_cloud: bool


class PeriodUnit(str, Enum):
    """
    Enum used to represent the time unit when calculating usage or other case need to set time period
    """
    day: str = 'day'
    week: str = 'week'
    month: str = 'month'

    @classmethod
    def get_current_period_start(cls, period: 'PeriodUnit') -> int:
        """
        Return `int` timestamp of start time of current period unit.

        Period Unit Start Time Definition:

        - ``day``: Today's 0:00AM
        - ``week``: Monday of this week, 0:00AM
        - ``month``: First day of this month, 0:00AM
        """
        datetime_ins = datetime.today()
        datetime_ins = datetime_ins.replace(hour=0, minute=0, second=0, microsecond=0)

        if period == PeriodUnit.week:
            datetime_ins = datetime_ins - timedelta(days=datetime_ins.weekday())
        if period == PeriodUnit.month:
            datetime_ins = datetime_ins.replace(day=1)

        return int(datetime_ins.timestamp())

    @classmethod
    def get_period_end(cls, period: 'PeriodUnit', period_start_timestamp: int) -> int:
        # make sure it's int.
        period_start_timestamp = int(period_start_timestamp)

        # convert period start timestamp to datetime
        dt_period_start = datetime.fromtimestamp(period_start_timestamp)

        if period == PeriodUnit.day:
            # 00:00:00 to 23:59:59
            return period_start_timestamp + 24 * 60 * 60 - 1
        if period == PeriodUnit.week:
            return int((dt_period_start + timedelta(days=7)).timestamp()) - 1
        if period == PeriodUnit.month:
            next_month = dt_period_start + timedelta(days=35)
            last_day = next_month - timedelta(days=next_month.day - 1)
            return int(last_day.timestamp()) - 1

    @classmethod
    def get_previous_period_start(cls, period: 'PeriodUnit', period_start_timestamp: int) -> int:
        period_start_timestamp = int(period_start_timestamp)
        dt_period_start = datetime.fromtimestamp(period_start_timestamp)

        if period == PeriodUnit.day:
            return period_start_timestamp - 24 * 60 * 60
        if period == PeriodUnit.week:
            return int((dt_period_start - timedelta(weeks=1)).timestamp())
        if period == PeriodUnit.month:
            return int((dt_period_start - timedelta(days=5)).replace(day=1).timestamp())

    @classmethod
    def get_period_duration(cls, period: 'PeriodUnit') -> int:
        """
        Return ``int`` seconds of the receiving duration.
        """
        duration = int(24 * 60 * 60)

        if period == PeriodUnit.day:
            return duration
        if period == PeriodUnit.week:
            return duration * 7
        if period == PeriodUnit.month:
            return duration * 30
