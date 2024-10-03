import subprocess
import asyncio
import time
from loguru import logger
import fire

import httpx

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.sql import text
from sqlalchemy.engine import create_engine

from schemes.sql import SQLBaseModel
from schemes import sql as orm
from schemes import db as db_sche

from config import sql
from config import general as gene_config

from provider.database import session_manager, _engine


async def init_database(no_drop: bool = False):
    """
    Initialize business database
    """
    async with _engine.begin() as conn:
        if not no_drop:
            await conn.run_sync(SQLBaseModel.metadata.drop_all)
        await conn.run_sync(SQLBaseModel.metadata.create_all)


async def init_supertoken_db():
    """Initialize supertoken database

    This function will clear all previous info stored in supertoken server,
    make sure you have backup the supertoken database.
    """
    # try stop supertoken
    res = subprocess.run(["supertokens stop"], shell=True)
    if res.returncode != 0:
        raise RuntimeError(
            "Failed to stop supertokens services. This is most likely caused by "
            "insufficient permissions. "
            "Try running this script with sudo or administration privilege on Windows. "
            f"Return code: {res.returncode}"
        )

    st_db_engine = create_engine(
        f"mysql+pymysql://"
        f"{sql.ST_DB_USERNAME}:{sql.ST_DB_PASSWORD}"
        f"@{sql.ST_DB_HOST}/{sql.ST_DB_NAME}",
        echo=sql.ENGINE_ECHO,
    )

    # try remove and recreate databse
    with st_db_engine.connect() as conn:
        with conn.begin():
            res = conn.execute(text("DROP DATABASE IF EXISTS supertokens"))
            res = conn.execute(text("CREATE DATABASE supertokens"))

    logger.info("Finished cleaning Supertokens database")

    # try start supertokens
    res = subprocess.run(
        [
            "supertokens start"
            f" -h {gene_config.ST_HOST}"
            f" -p {str(gene_config.ST_PORT)}"
        ],
        shell=True,
    )

    # try add dashboard admin user
    res = httpx.post(
        f"{gene_config.GET_SUPERTOKEN_BACKEND_URL()}/recipe/dashboard/user",
        headers={
            "rid": "dashboard",
            "Content-Type": "application/json",
        },
        json={
            "email": gene_config.ST_DASHBOARD_USERNAME,
            "password": gene_config.ST_DASHBOARD_PASSWORD,
        },
    )

    if res.status_code != 200:
        raise RuntimeError("Failed to add supertoken dashboard admin account.")


DEFAULT_USERS = [
    {
        "formFields": [
            {"id": "email", "value": "test1@stu.ahu.edu.cn"},
            {"id": "password", "value": "Asd123123"},
        ]
    },
    {
        "formFields": [
            {"id": "email", "value": "test2@stu.ahu.edu.cn"},
            {"id": "password", "value": "Asd123123"},
        ]
    },
]

DEFAULT_ROLES = [
    orm.Role(role_name="admin", role_title="系统管理员"),
    orm.Role(role_name="moderator", role_title="管理员"),
]


async def add_default_data():
    async with session_manager() as ss:
        async with ss.begin():

            # adding users
            for u in DEFAULT_USERS:
                logger.debug(
                    "Sending request to: "
                    f"{gene_config.GET_BACKEND_URL()}/auth/signup"
                )

                res = httpx.post(
                    f"{gene_config.GET_BACKEND_URL()}/auth/signup",
                    json=u,
                )

                if res.status_code != 200:
                    raise RuntimeError(
                        "[SupertokensSignUpFailed] "
                        f"Failed to add user using Supertoken endpoints with status code {res.status_code}, "
                        "make sure API server has already started before "
                        "calling this script. "
                        "For more info about this error, check out: "
                        "https://github.com/NFSandbox/sh_trade_backend/wiki/Create-Database-Script#supertokenssignupfailed"
                    )

            # logger.info("Adding default users...")
            # ss.add_all(DEFAULT_USERS)

            logger.info("Adding default roles...")
            ss.add_all(DEFAULT_ROLES)

            logger.info("Adding user-role relationship...")
            test_user: orm.User = await ss.get(orm.User, 1)  # type: ignore
            assert test_user is not None
            roles: list[orm.Role] = await test_user.awaitable_attrs.roles
            admin_role: orm.Role = await ss.get(orm.Role, 1)  # type: ignore
            roles.append(admin_role)

            logger.info("Adding custom contact info...")
            contact_info: list[orm.ContactInfo] = (
                await test_user.awaitable_attrs.contact_info
            )
            contact_info.append(
                orm.ContactInfo(
                    contact_type=orm.ContactInfoType.email,
                    contact_info="nf@nfblogs.com",
                )
            )
        # auto commit
    # auto close ss


@logger.catch()
async def async_main(
    y: bool = False, no_drop: bool = False, h: bool = False, clear_st: bool = True
):
    # show help text, then return
    if h:
        logger.info(
            "Usage of create_db.py"
            "\n-h           Show help text"
            "\n-y           Confirm action, compulsory when execute without --no-drop"
            "\n--no-drop    Do not drop previous table when exists"
            "\n--clear-st   Reinitialize self-hosted supertoken info"
        )
        return

    # user operation confirm
    need_confirm = False
    if not no_drop:
        need_confirm = True
    if clear_st:
        need_confirm = True
    if no_drop:
        logger.success("No-drop mode enabled")
    if not clear_st:
        logger.success("Supertoken info kept")
    # check confirm if needed
    if need_confirm:
        logger.warning(
            "Executing this script will drop all previous data in the database, "
            "which may lead to inreversible data loss. "
        )

        if not y:
            logger.error(
                "If you want to continue this process, run 'python create_db.py -y'"
            )
            return

    # start init
    logger.info("Database initialization started")

    # supertokens
    if clear_st:
        await init_supertoken_db()

    # database
    logger.info("Initialize database schemas...")
    await init_database(no_drop=no_drop)

    # test data
    logger.info("Filling test data...")
    await add_default_data()

    logger.success("Database initialization successful!")


if __name__ == "__main__":
    fire.Fire(async_main)
