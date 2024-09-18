import asyncio
import time
from loguru import logger
import fire

from sqlalchemy.ext.asyncio import AsyncSession

from provider import database
from schemes.sql import SQLBaseModel
from schemes import sql as orm
from schemes import db as db_sche


async def init_models():
    async with database._engine.begin() as session:
        await session.run_sync(SQLBaseModel.metadata.drop_all)
        await session.run_sync(SQLBaseModel.metadata.create_all)


DEFAULT_USERS = [
    orm.User(
        user_id=1,
        username="nfnfgo",
        # password=string
        password="$2b$12$j4gfDdlPetmpb7Z0xGA7C.Vox3P7X0.848622qQrWwR6QTvXGFrHG",
    ),
    orm.User(
        user_id=2,
        username="admin",
        # password=admin
        password="$2b$12$P22k4V8ZPhE5Gobgs3Xms.okkwMdxqg43ik6XAJsuTy12ZvlZTK9a",
    ),
]

DEFAULT_ROLES = [
    orm.Role(role_name="admin", role_title="系统管理员"),
    orm.Role(role_name="moderator", role_title="管理员"),
]


async def add_default_data():
    session_maker = database.init_session_maker()
    async with session_maker() as ss:
        async with ss.begin():

            logger.info("Adding default users...")
            ss.add_all(DEFAULT_USERS)

            logger.info("Adding default roles...")
            ss.add_all(DEFAULT_ROLES)

            logger.info("Adding user-role relationship...")
            test_user: orm.User = await ss.get(orm.User, 1)  # type: ignore
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


async def async_main(y: bool = False):

    logger.warning(
        "Executing this script will drop all previous data in the database, "
        "which may led to unreversible data loss. "
    )

    if not y:
        logger.error(
            "If you want to continue this process, run 'python create_db.py -y'"
        )
        return

    logger.info("Database initialization started")

    logger.info("Initialize database schemas...")
    await init_models()

    logger.info("Filling test data...")
    await add_default_data()

    logger.success("Database initialization successful!")


if __name__ == "__main__":
    fire.Fire(async_main)
