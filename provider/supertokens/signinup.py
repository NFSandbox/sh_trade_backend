from supertokens_python import init, InputAppInfo
from supertokens_python.recipe import thirdparty, emailpassword, session
from supertokens_python.recipe.thirdparty.interfaces import (
    RecipeInterface as ThirdPartyRecipeInterface,
)
from supertokens_python.recipe.emailpassword.interfaces import (
    RecipeInterface as EmailPasswordRecipeInterface,
    SignInOkResult,
    SignInWrongCredentialsError,
    SignUpOkResult,
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
        email: str, password: str, tenant_id: str, user_context: Dict[str, Any]
    ):

        result = await original_emailpassword_sign_up(
            email, password, tenant_id, user_context
        )

        if isinstance(result, SignUpOkResult):
            # sign up successfully, update databases
            super_token_user_id = result.user.user_id
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
                        )

                        ss.add(orm_supertoken_user)
            except Exception as e:
                raise RuntimeError(
                    "Supertoken successfully handle user sign-up request, "
                    "however post-process failed to update info in database. "
                    f"SuperTokenID: {super_token_user_id}"
                ) from e

        return result

    async def emailpassword_sign_in(
        email: str, password: str, tenant_id: str, user_context: Dict[str, Any]
    ):
        res = await original_emailpassword_sign_in(
            email, password, tenant_id, user_context
        )

        # check the supertoken id has corresponding user in database
        if isinstance(res, SignInOkResult):
            super_token_user_id = res.user.user_id
            async with session_manager() as ss:
                orm_supertoken_user = await ss.get(
                    orm.SuperTokenUser, super_token_user_id
                )
                if (
                    orm_supertoken_user is None
                    or orm_supertoken_user.deleted_at is not None
                ):
                    return SignInWrongCredentialsError()
                orm_user = await ss.run_sync(lambda ss: orm_supertoken_user.user)
                if orm_user is None:
                    return SignInWrongCredentialsError()

        return res

    original_implementation.sign_up = emailpassword_sign_up
    original_implementation.sign_in = emailpassword_sign_in

    return original_implementation


# def override_thirdparty_functions(
#     original_implementation: ThirdPartyRecipeInterface,
# ) -> ThirdPartyRecipeInterface:
#     original_thirdparty_sign_in_up = original_implementation.sign_in_up

#     async def thirdparty_sign_in_up(
#         third_party_id: str,
#         third_party_user_id: str,
#         email: str,
#         oauth_tokens: Dict[str, Any],
#         raw_user_info_from_provider: RawUserInfoFromProvider,
#         tenant_id: str,
#         user_context: Dict[str, Any],
#     ):
#         result = await original_thirdparty_sign_in_up(
#             third_party_id,
#             third_party_user_id,
#             email,
#             oauth_tokens,
#             raw_user_info_from_provider,
#             tenant_id,
#             user_context,
#         )

#         # user object contains the ID and email of the user
#         user = result.user
#         print(user)

#         # This is the response from the OAuth 2 provider that contains their tokens or user info.
#         provider_access_token = result.oauth_tokens["access_token"]
#         print(provider_access_token)

#         if result.raw_user_info_from_provider.from_user_info_api is not None:
#             first_name = result.raw_user_info_from_provider.from_user_info_api[
#                 "first_name"
#             ]
#             print(first_name)

#         if result.created_new_user:
#             print("New user was created")
#             # TODO: Post sign up logic
#         else:
#             print("User already existed and was signed in")
#             # TODO: Post sign in logic

#         return result

#     original_implementation.sign_in_up = thirdparty_sign_in_up

#     return original_implementation
