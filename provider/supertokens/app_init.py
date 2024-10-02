# core deps
from supertokens_python import init, InputAppInfo, SupertokensConfig
from supertokens_python.recipe import (
    thirdparty,
    emailpassword,
    session,
    dashboard,
    userroles,
)

# third-party login deps
from supertokens_python.recipe.thirdparty.provider import (
    ProviderInput,
    ProviderConfig,
    ProviderClientConfig,
)
from supertokens_python.recipe import thirdparty

from .signinup import override_emailpassword_functions

from supertokens_python.framework import BaseRequest
from typing import Dict, Any


from config import general as gene_config


def get_token_transfer_method(
    req: BaseRequest, for_create_new_session: bool, user_context: Dict[str, Any]
):
    # OR use session.init(get_token_transfer_method=lambda *_: "header")
    return "cookie"


init(
    app_info=InputAppInfo(
        app_name="AHUPY",
        api_domain="http://localhost:8000",
        website_domain="http://localhost:3000",
        api_base_path="/auth",
        website_base_path="/auth",
    ),
    supertokens_config=SupertokensConfig(
        # https://try.supertokens.com is for demo purposes. Replace this with the address of your core instance (sign up on supertokens.com), or self host a core.
        connection_uri=f"{gene_config.ST_PROTOCAL}://{gene_config.ST_HOST}:{gene_config.ST_PORT}",
        # api_key=<API_KEY(if configured)>
    ),
    framework="fastapi",
    recipe_list=[
        session.init(
            get_token_transfer_method=get_token_transfer_method
        ),  # initializes session features
        # thirdparty.init(
        # ),
        emailpassword.init(
            override=emailpassword.InputOverrideConfig(
                functions=override_emailpassword_functions
            )
        ),
        dashboard.init(),
        userroles.init(),
    ],
    mode="asgi",  # use wsgi if you are running using gunicorn
)


# Template, not used yet
thirdparty.init(
    sign_in_and_up_feature=thirdparty.SignInAndUpFeature(
        providers=[
            # We have provided you with development keys which you can use for testing.
            # IMPORTANT: Please replace them with your own OAuth keys for production use.
            ProviderInput(
                config=ProviderConfig(
                    third_party_id="google",
                    clients=[
                        ProviderClientConfig(
                            client_id="1060725074195-kmeum4crr01uirfl2op9kd5acmi9jutn.apps.googleusercontent.com",
                            client_secret="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",
                        ),
                    ],
                ),
            ),
            ProviderInput(
                config=ProviderConfig(
                    third_party_id="apple",
                    clients=[
                        ProviderClientConfig(
                            client_id="4398792-io.supertokens.example.service",
                            additional_config={
                                "keyId": "7M48Y4RYDL",
                                "privateKey": "-----BEGIN PRIVATE KEY-----\nMIGTAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBHkwdwIBAQQgu8gXs+XYkqXD6Ala9Sf/iJXzhbwcoG5dMh1OonpdJUmgCgYIKoZIzj0DAQehRANCAASfrvlFbFCYqn3I2zeknYXLwtH30JuOKestDbSfZYxZNMqhF/OzdZFTV0zc5u5s3eN+oCWbnvl0hM+9IW0UlkdA\n-----END PRIVATE KEY-----",
                                "teamId": "YWQCXGJRJL",
                            },
                        ),
                    ],
                ),
            ),
            ProviderInput(
                config=ProviderConfig(
                    third_party_id="github",
                    clients=[
                        ProviderClientConfig(
                            client_id="467101b197249757c71f",
                            client_secret="e97051221f4b6426e8fe8d51486396703012f5bd",
                        ),
                    ],
                ),
            ),
        ]
    )
)
