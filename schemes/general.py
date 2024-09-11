from pydantic import BaseModel


class BackendInfoOut(BaseModel):
    version: str
    on_cloud: bool
