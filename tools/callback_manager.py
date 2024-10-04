from typing import Callable, Any, Awaitable
from inspect import isawaitable

from loguru import logger

from exception.error import BaseError


class CallbackInterrupted(BaseError):
    def __init__(
        self,
        callback_key: str,
        name: str = "callback_interrupted",
        message: str = "Notification sending process is interrupted by callback function.",
    ) -> None:
        message += f"Callback key: {callback_key}"
        super().__init__(name=name, message=message, status=500)


class CallbackManager[
    **CallbackArgs,
    CallableRetType: Awaitable | Any,
    SignalType: str,
]:
    """
    Generic callback manager class.

    - `**CallbackArgs` Parameters list of callback functions
    - `CallableRetType` Return type of the callback functions, to support async functions,
      use `Awaitable[...] | ...`
    - `SignalType` Type of allowed signals for this callback manager. This type must be
      able to use as `key` of a Python dict.
    """

    # CallbackFnType = Callable[["NotificationSender"], Awaitable[Any] | Any]
    # SignalType = Literal["before", "upon", "after"]

    disabled: bool = False

    def __init__(self) -> None:
        self.callbacks: dict[
            SignalType, dict[str, Callable[CallbackArgs, CallableRetType]]
        ] = {}
        """Store all callbacks of this callback manager"""

        self.disabled: bool = False
        """Disable callbacks trigger and execution"""

    def clear(self):
        """
        Clear all callbacks.
        """
        self.callbacks = {}

    async def trigger(
        self,
        signal: SignalType,
        *args: CallbackArgs.args,
        **kwargs: CallbackArgs.kwargs,
    ) -> None:
        """
        Trigger callbacks for a given signal.

        Raise `CallbackInterrupted` if callback want to interrput the process
        """
        # check if disabled
        if self.disabled:
            return None

        # get all callbacks to trigger
        cb_dict = self.callbacks[signal]

        should_continue = True
        interrput_key: str | None = None
        for k, fn in cb_dict.items():
            logger.debug(
                f"Trigger callback {fn.__name__} (key: '{k}') with signal '{signal}'"
            )

            res = None

            # trigger callback, compatible with both sync and async function
            if callable(fn):
                res = fn(*args, **kwargs)
                if isawaitable(res):
                    res = await res

            if res == False:
                should_continue = False
                interrput_key = k

        if not should_continue:
            assert interrput_key is not None
            raise CallbackInterrupted(callback_key=interrput_key)

    def add(
        self,
        signal: SignalType,
        fn: Callable[CallbackArgs, CallableRetType],
        key: str | None = None,
    ) -> None:
        """
        Add a callback function to the specified signal.
        """
        if key is None:
            key = fn.__name__
        try:
            self.callbacks[signal][key] = fn
        except KeyError:
            raise KeyError(
                f"Callback with key '{key}' in signal '{signal}' alrady exists"
            )

    def remove(self, signal: SignalType, key: str) -> None:
        """
        Remove a callback function from the specified signal.
        """
        try:
            del self.callbacks[signal][key]
        except KeyError:
            raise KeyError(f"Callback with key '{key}' in signal '{signal}' not found")
