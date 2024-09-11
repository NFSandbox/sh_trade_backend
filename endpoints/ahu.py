import time
from enum import Enum
from typing import Annotated
from pydantic import BaseModel

import jwt

from fastapi import APIRouter, Query, Depends, Request, Response, Body

import provider.ahu
from config import dorm as dorm_config
from endpoints import auth as auth_endpoint
from schemes import ahu as ahu_schema
from schemes import electric as elec_schema

ahu_router = APIRouter()


@ahu_router.get('/header_info', response_model=ahu_schema.AHUHeaderInfo)
async def get_ahu_header_info(role=Depends(auth_endpoint.require_role(['admin']))):
    return ahu_schema.AHUHeaderInfo.from_dict(dorm_config.get_ahu_header(force_load_from_file=True))


@ahu_router.post('/set_header_info', response_model=ahu_schema.AHUHeaderInfo)
async def set_ahu_header_info(
        url_str: str = Body(),
        role=Depends(auth_endpoint.require_role(['admin'])),
):
    dorm_config.update_ahu_header(url_str=url_str, clear_cache=True)
    return ahu_schema.AHUHeaderInfo.from_dict(dorm_config.get_ahu_header(force_load_from_file=True))


class CatchRecordResponse(BaseModel):
    """
    Members:

    - ``record`` The record retrieved from AHU website.
    - ``latency_ms`` Request latency between backend server and AHU website. In milliseconds unit.
    """
    record: elec_schema.BalanceRecord
    latency_ms: int


@ahu_router.get('/catch_record', tags=['Test', 'Records'], response_model=CatchRecordResponse)
async def catch_record_from_ahu(dry_run: bool = True):
    """
    Directly catch records from AHU website.

    This endpoint could also be used as a test to AHU website.

    Parameter:

    - `dry_run` Default to `True`.
        - If `True`, only try to catch records and returns info to frontend,
        will NOT update database.
        - If `false`, means catch records, return info, then add record to database.

    Returns:

    - ``latency_ms`` The time consumed for requesting data from AHU website and pydantic validation.
    The database operation when `dry_run=False` is not included in this field.

    """
    start_req = time.time()
    record_info: elec_schema.BalanceRecord = elec_schema.BalanceRecord.from_info_dict(await provider.ahu.get_record())
    duration = time.time() - start_req
    latency_ms: int = int(duration * (10 ** 3))

    if not dry_run:
        await provider.database.add_record(record_info=record_info)

    return CatchRecordResponse(
        record=record_info,
        latency_ms=latency_ms,
    )
