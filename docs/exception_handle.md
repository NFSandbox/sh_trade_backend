# Basic

All codes about _Custom Error_ should be written inside `exception` directory.

We use `FastAPI Error Handler` feature to handle all custom error derived from `BaseError`. So it's strongly
recommend to create a new sub class when a custom error is needed.

# About BaseClass

There are three members:

- `name` The **display name** of this error, **may be shown at frontend**.
- `message` The **brief description** of this error, **may be shown at frontend**.
- `status` Used by the _FastAPI Custom Error Handler_ to determine the response _HTTP Status Code_.

## Naming Convention

- `name` Should only contain `lowercase alphabets` and `_`. E.g.: `auth_error`, `token_expired`.

Just for beauty.

- One name could only be used to represent one error. **Don't let different errors have same name, even if they are in
  same category**.

For example token error could have several different subcategory, for example the token is invalid or token is
expired. In this case, **do NOT using something like `token_error` to represent all token error. Instead, using
`token_expired`, `invalid_token` etc to represent each sub error**.

## Pydantic Support

The `BaseError` class is a sub-class of Python Exception, which means it's competible with Python error handling
process.

However in order to make our custom error system works with FastAPI, we need a `Pydantic` version of our error class,
which is `BaseErrorOut`.

But anyway when throwing error or creating subclasses, we don't need to consider this part of mechanism, and we only
need to create new class from `BaseError`.

# Creating Custom Error Sub-class

Generally, the only thing we should do in subclass of `BaseError` is the `__init__()` function. In which:

- Deal with initialize logic of this kind of error. Determine `name`, `message` and `status` based on the logic.
- Call `super().__init__(name=..., message=..., status=...)`

Recommend checking out `TokenError` subclass for more info.

<details>
<summary>Code Snippet</summary>

```python
class TokenError(BaseError):
    """
    Raise when error occurred while verifying token.

    Check out __init__() for more info.
    """

    def __init__(
            self,
            message: str | None = None,
            expired: bool | None = None,
            role_not_match: bool | None = None,
            no_token: bool | None = None,
    ) -> None:
        final_name = 'token_error'
        final_message = message
        """
        Create an `TokenError` instance.
        :param message:
        :param expired: If `true`, indicates the token is expired.
        :param role_not_match: If `true`, indicates the role are not match the requirements.
        """
        if message is None:
            message = 'Could not verify the user tokens'

        if expired:
            final_name = 'token_expired'
            message = 'Token expired, try login again to get a new token'

        if role_not_match:
            final_name = 'token_role_not_match'
            message = 'Current role are not match the requirements to perform this operation or access this resources'

        if no_token:
            final_name = 'token_required'
            message = 'Could not found a valid token, try login to an valid account'

        # only when message is None, then use presets, otherwise always use the original message passed.
        if final_message is None:
            final_message = message

        super().__init__(
            name=final_name,
            message=final_message,
            status=401
        )
```

As you see, although we say that we need to use different `name` for every sub-category error, **we can still use a 
same class to deal with errors in same category** based on the actual requirements.

</details>