import asyncio
from loguru import logger
from aiohttp import ClientSession

from provider import ahu
from provider import database

from schemes.electric import BalanceRecord


async def main():
    await ahu.init_client_session(force_create=True)

    record_dict = await ahu.get_record()
    logger.info('Record caught from AHU:')
    logger.info(record_dict)
    try:
        record_ins = BalanceRecord(**record_dict)
        await database.add_record(record_ins)
        await database.session_maker().close()
    except Exception as e:
        logger.error('Failed to add record info into database')
        logger.exception(e)

    await ahu.aiohttp_session.close()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except RuntimeError as re:
        if re.__repr__() == '''RuntimeError('Timeout context manager should be used inside a task')''':
            logger.error('Async Client Session Error')
            logger.exception(re)
        logger.success('Task accomplished')