from typing import Any, Union

from supertokens_python import init, InputAppInfo
from supertokens_python.recipe import thirdparty, emailpassword, session
from supertokens_python.recipe.thirdparty.interfaces import (
    RecipeInterface as ThirdPartyRecipeInterface,
)
from supertokens_python.recipe.emailpassword.interfaces import (
    RecipeInterface as EmailPasswordRecipeInterface,
    SignInOkResult,
    SignUpOkResult,
    WrongCredentialsError,
)
from supertokens_python.recipe.thirdparty.types import RawUserInfoFromProvider
from typing import Dict, Any

from loguru import logger

from schemes import sql as orm
from ..database import session_manager, try_commit
from exception import error as exc


# if signup
def override_emailpassword_functions(
    original_implementation: EmailPasswordRecipeInterface,
) -> EmailPasswordRecipeInterface:
    original_emailpassword_sign_up = original_implementation.sign_up
    original_emailpassword_sign_in = original_implementation.sign_in

    # override sign up process
    async def emailpassword_sign_up(
        email: str,
        password: str,
        tenant_id: str,
        session: Any,
        user_context: Dict[str, Any],
        should_try_linking_with_session_user,
    ):

        result = await original_emailpassword_sign_up(
            email,
            password,
            tenant_id,
            session,
            should_try_linking_with_session_user,
            user_context,
        )

        if isinstance(result, SignUpOkResult):
            # sign up successfully, update databases
            super_token_user_id = result.user.id
            try:
                async with session_manager() as ss:
                    async with ss.begin():
                        # orm user
                        orm_user = orm.User(
                            username=email,
                        )

                        ss.add(orm_user)

                        # user-supertoken_user relationship
                        orm_supertoken_user = orm.SuperTokenUser(
                            user=orm_user,
                            supertoken_id=super_token_user_id,
                            supertoken_contact_info=email,
                        )
                        ss.add(orm_supertoken_user)

                        # user ahu-email relationship with verified state
                        #
                        # here notice that the actual email verification control is
                        # handled by supertoken recipe.
                        #
                        # If the user email is not verified, the supertoken /signin endpoint
                        # should be responsible to return a 403 and not returning session
                        # tokens. So even if here we marked the email verified, user should
                        # still not be able to login to system until they finished the email
                        # verification and the email verification state updated in supertoken
                        # system.
                        ahu_contact_info = orm.ContactInfo(
                            user=orm_user,
                            contact_type=orm.ContactInfoType.ahuemail,
                            contact_info=email,
                            verified=True,
                        )

                        ss.add(ahu_contact_info)

            except Exception as e:
                raise RuntimeError(
                    "Supertoken successfully handle user sign-up request, "
                    "however post-process failed to update info in database. "
                    f"SuperTokenID: {super_token_user_id}"
                ) from e

        return result

    async def emailpassword_sign_in(
        email: str,
        password: str,
        tenant_id: str,
        session: Any,
        should_try_linking_with_session_user: Union[bool, None],
        user_context: Dict[str, Any],
    ):
        res = await original_emailpassword_sign_in(
            email,
            password,
            tenant_id,
            session,
            should_try_linking_with_session_user,
            user_context,
        )

        # check the supertoken id has corresponding user in database
        if isinstance(res, SignInOkResult):
            super_token_user_id = res.user.id
            async with session_manager() as ss:
                orm_supertoken_user = await ss.get(
                    orm.SuperTokenUser, super_token_user_id
                )
                if (
                    orm_supertoken_user is None
                    or orm_supertoken_user.deleted_at is not None
                ):
                    return WrongCredentialsError()
                orm_user = await ss.run_sync(lambda ss: orm_supertoken_user.user)
                if orm_user is None:
                    return WrongCredentialsError()

        return res

    original_implementation.sign_up = emailpassword_sign_up  # type: ignore
    original_implementation.sign_in = emailpassword_sign_in  # type: ignore

    return original_implementation
