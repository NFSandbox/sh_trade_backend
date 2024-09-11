import time
from enum import Enum
from typing import Annotated, Optional

from fastapi import APIRouter, Query, Body, Depends

import config.general
from provider.database import add_record, get_record_count
from provider import database as provider_db
from schemes.electric import Statistics, BalanceRecord
from schemes.electric import BalanceRecord
from schemes import electric as elec_schema
from schemes import general as gene_schema
from schemes.sql import PaginationConfig
from endpoints.auth import require_role

from exception import error as exc

# Router for info
# Notice that this router actually do NOT add any prefix
infoRouter = APIRouter()


@infoRouter.get('/api_info', response_model=gene_schema.BackendInfoOut)
def get_backend_endpoint_version():
    return gene_schema.BackendInfoOut(
        version=config.general.BACKEND_API_VER,
        on_cloud=config.general.ON_CLOUD,
    )


@infoRouter.get('/statistics', response_model=Statistics, tags=['Statistics'])
async def get_electrical_usage_statistic():
    return await provider_db.get_statistics()


@infoRouter.post('/add_record', tags=['Records'])
async def add_new_record(new_record: BalanceRecord, use_current_timestamp: bool = False):
    """
    Add a record into database.

    When timstamp in `new_record` is negative, use current timestamp forcefully.

    :param new_record: Record need to be added into database.
    :param use_current_timestamp: If `true`, use current timestamp.
    :return:
    """
    # Override timestamp if needed
    if use_current_timestamp or new_record.timestamp < 0:
        new_record.timestamp = time.time()
    await add_record(new_record)


@infoRouter.get('/record_count', response_model=elec_schema.CountInfoOut, tags=['Records', 'Statistics'])
async def record_count():
    return await get_record_count()


@infoRouter.post(
    '/records',
    response_model=list[BalanceRecord],
    tags=['Records'])
async def get_records_by_pagination(pagination: PaginationConfig):
    return await provider_db.get_records(pagination)


@infoRouter.get('/latest_record', tags=['Records'], response_model=BalanceRecord)
async def get_lastest_record():
    res = await provider_db.get_records(
        pagination=PaginationConfig(size=1, index=0)
    )
    if len(res) == 0:
        raise exc.NoResultError('No record found in database.')

    return res[0]


@infoRouter.post('/recent_records', tags=['Records'], response_model=list[BalanceRecord])
async def get_recent_days_records(
        days: Annotated[int, Body(ge=1)] = 7,
        usage_convert_config: elec_schema.UsageConvertConfig | None = None):
    """
    Here days actually has been converted to timstamp. That means the earliest limit is set by
    calculating time offset but not using natural day as limit.

    Parameters:

    - days: The days back you want to get records start from.
    - usage_convert_config: If NOT None, convert balance list to usage list using this config.

    Notice: For more info about usage convert config, check out Model `UsageConvertConfig`
    """
    return await provider_db.get_recent_records(days, usage_convert_config=usage_convert_config)


@infoRouter.get(
    '/daily_usage',
    response_model=list[elec_schema.PeriodUsageInfoOut],
    tags=['Statistics'], )
async def get_daily_usage(
        days: Annotated[int, Query(ge=1)] = 7,
        recent_on_top: Annotated[bool, Query()] = True,
):
    """
    Parameters:

    - ``days``: The number of days you want to calculate usage statistics. Back starting from today.
    - ``recent_on_top``: If ``true``, then the day closest to today will at the first place of the return list.
    """
    return await provider_db.daily_usage_list(days=days, recent_on_top=recent_on_top)


@infoRouter.get(
    '/period_usage',
    response_model=list[elec_schema.PeriodUsageInfoOut],
    tags=['Statistics'],
)
async def get_period_usage(
        period: gene_schema.PeriodUnit,
        period_count: int,
        recent_on_top: bool = True,
):
    return await provider_db.period_usage_list(
        period=period,
        period_count=period_count,
        recent_on_top=recent_on_top,
    )


@infoRouter.post('/get_records_by_time_range', tags=['Records'])
async def get_records_by_time_range(
        start_time: int,
        end_time: int | None = None,
        usage_convert_config: Annotated[elec_schema.UsageConvertConfig, Body(embed=True)] = None,
):
    """
    Get all records info in a specific time range.

    Parameter:

    - ``start_time`` : Specified the start timestamp.
    - ``end_time``: Specified the end timestamp. If `None`, will be current timestamp.

    Returns:
    - List of records/usage info.
    - If no records in this time range, return empty list.
    """
    if end_time is None:
        end_time = time.time()
    return await provider_db.get_records_by_time_range(start_time, end_time, usage_convert_config)


@infoRouter.get('/delete_records_by_time_range', tags=['Records'])
async def delete_records_by_time_range(
        start_time: int,
        end_time: int,
        role: Annotated[str, Depends(require_role(['admin']))],
        dry_run: bool = False,
) -> int:
    """
    Remove records from database with specific time range [start, end] (Notice that end time included in range)

    Params:

    - ``start`` UNIX timestamp of the start time range.
    - ``end`` UNIX timestamp of the end time range.
    - ``dry_run`` If `True`, will only test the affected records count, and will NOT delete the records.

    Returns:

    - Total count of records deleted.
    """
    return await provider_db.delete_records_by_time_range(
        start_time,
        end_time,
        dry_run,
    )


@infoRouter.get('/statistics/time_range', tags=['Statistics'], response_model=elec_schema.TimeRangeStatistics)
async def get_statistics_of_specific_time_range(start_time: int, end_time: int | None = None):
    return await provider_db.get_statistics_by_time_range(start_time, end_time)
