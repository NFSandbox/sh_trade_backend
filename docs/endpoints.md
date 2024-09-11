# Endpoint Tags

Currently, all `endpoints` should belongs to one or more following tags.

- **Authentication** About role authentication.
- **Info** Return or update some info.
  - **Statistics** Get statistics info.
  - **Records** Operation or data about records.
- **AHU** Related to AHU website or AHU config.
- **Test** Used for feature test when developing.

## Where To Add Tags

Generally, endpoints in the **same sub-router should have the same tag**. When adding such tags, **add it in `main.py`
when including sub-routers**. Check code example below:

```python
app.include_router(infoRouter, prefix="/info", tags=['Info'])
app.include_router(auth_router, prefix='/auth', tags=['Authentication'])
app.include_router(ahu_router, prefix='/ahu', tags=['AHU'])
```

However, if the tags is related to the endpoint itself, we may **add the tag directly at the endpoint function
decorator**.

```python
@infoRouter.get('/statistics', response_model=Statistics, tags=['Statistics'])
async def get_electrical_usage_statistic():
    ...
```