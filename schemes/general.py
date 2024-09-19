from pydantic import BaseModel, NonNegativeInt


class BackendInfoOut(BaseModel):
    version: str
    on_cloud: bool


class BulkOpeartionInfo(BaseModel):
    """
    Pydantic schema used when backend need to return the result of bulk operation,
    for example Delete All Items"""

    success: bool = True
    operation: str | None = None
    total: NonNegativeInt = 0

    def inc(self, delta: int = 1):
        self.total += delta
