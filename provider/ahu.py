import time

from aiohttp import ClientSession
import re
from loguru import logger

from schemes.electric import BalanceRecord
from config import dorm
from exception import error as exc

aiohttp_session: ClientSession | None = None


async def init_client_session(force_create: bool = False) -> ClientSession:
    global aiohttp_session
    if aiohttp_session is None or force_create:
        aiohttp_session = ClientSession(base_url=dorm.AHU_WEBSITE)
    return aiohttp_session


def extract_balance(json):
    """
    Parse the balance info from the string returned by AHU website.

    Return:

    - A floating number representing the balance info retrived from string.
    - The floating number points is not limited.
    """
    logger.debug(f'Input Json,{json}')
    try:
        text_info = json['map']['showData']['信息']

        # try match balance number part inside the info text.
        logger.debug(f'text_info: {text_info}')
        match_number_str = re.search(r'[-+]?[0-9]+\.?[0-9]+', text_info)
        if match_number_str:
            logger.debug(f'Found matched balance number: {match_number_str}')
            match_number_str = match_number_str.group()
        else:
            raise exc.AHUInfoParseError(text_info)

        # convert to number and return the value
        return float(match_number_str)

    except exc.BaseError as e:
        raise e
    except Exception as e:
        logger.error(e)
        raise exc.BaseError(
            name='ahu_format_error',
            message='The data received by AHU datasource have wrong format',
        )


async def get_record() -> dict:
    """
    Get current record from AHU official website

    Return a dict with info::

        {
            timestamp: int,
            ac_balance: float,
            light_balance: float,
        }
    """
    light_balance: float = 0
    ac_balance: float = 0

    session = await init_client_session()

    try:
        async with session.post(
                url='/charge/feeitem/getThirdData',
                data=dorm.DORM_LIGHT_INFO_DICT,
                headers=dorm.get_ahu_header(),
        ) as res:
            json = await res.json()
            light_balance = extract_balance(json)

        async with session.post(
                url='/charge/feeitem/getThirdData',
                data=dorm.DORM_AC_INFO_DICT,
                headers=dorm.DORM_REQ_HEADER_DICT,
        ) as res:
            json = await res.json()
            ac_balance = extract_balance(json)

        return {
            'timestamp': time.time(),
            'light_balance': light_balance,
            'ac_balance': ac_balance,
        }
    except exc.BaseError as e:
        # Here actually want to catch error from func `extract_balance`
        raise e
