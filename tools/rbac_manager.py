from typing import Literal, List, Dict, Sequence, Collection, Set, Any
from copy import copy, deepcopy
from functools import wraps
from pprint import pformat

from loguru import logger

from exception.error import BaseError


class RBACError(BaseError):
    def __init__(
        self,
        name: str = "rbac_error",
        message: str = "Error occurred when trying to proceed with RBAC system. ",
        status=500,
    ) -> None:
        super().__init__(name, message, status=status)


class InvalidRole(RBACError):
    def __init__(
        self,
        role: Any,
    ) -> None:
        super().__init__(
            name="invalid_role",
            message=f"Role '{role}' is invalid as a RBAC role, "
            "ensure you passed a role in the configured role list",
        )


class InsufficientPermission(RBACError):
    """
    Raised when RBAC permission check failed.

    Notice that since this error has `403` error code which is lower then `500`,
    the error message may reach client side if you do not actively handles it.
    """

    def __init__(
        self,
        role: Any,
        permission: Any,
    ) -> None:
        super().__init__(
            name="insufficient_permission",
            message=f"Role {role} has no permission {permission}",
            status=403,
        )


@wraps(logger.debug)
def debug_log(*args, **kwargs):
    logger.debug(*args, **kwargs)


@wraps(logger.success)
def success_log(*args, **kwargs):
    logger.success(*args, **kwargs)


@wraps(logger.error)
def error_log(*args, **kwargs):
    logger.error(*args, **kwargs)


class RBACManager[
    RoleType: str,
    PermissionType: str,
]:
    def __init__(
        self,
        roles: Set[RoleType],
        role_inheritance: Dict[RoleType, Set[RoleType]],
        role_permissions: Dict[RoleType, Set[PermissionType]],
    ) -> None:
        self.roles = roles
        self.role_inheritance = role_inheritance
        self.role_permissions = role_permissions

        self._compiled_role_permissions: Dict[RoleType, Set[PermissionType]] = {}
        self._compile_permissions()

    def _compile_permissions(self):
        # clear
        self._compiled_role_permissions = deepcopy(self.role_permissions)

        mutated = True
        iteration_count = 0

        while mutated:
            # update flags
            iteration_count += 1
            mutated = False

            if iteration_count > 50:
                raise RBACError(
                    message=f"Failed to compile permission list since max compile "
                    f"iteration reached. Current iteration: {iteration_count}. "
                )

            # propagate permissions for all roles
            for role in self.roles:
                try:
                    # set role permissions if prev is empty
                    self._compiled_role_permissions.setdefault(role, set())

                    # previous permission length of this role
                    prev_len = len(self._compiled_role_permissions[role])

                    # iterate through all directly inherited roles
                    for inherited_role in self.role_inheritance.get(role, {}):

                        # propagate permissions from this inherited role
                        self._compiled_role_permissions[role].update(
                            self._compiled_role_permissions.get(inherited_role, {})
                        )

                    # mark mutated if the permission set become larger
                    curr_len = len(self._compiled_role_permissions[role])
                    assert curr_len >= prev_len
                    if len(self._compiled_role_permissions[role]) > prev_len:
                        mutated = True
                except Exception as e:
                    raise RBACError(
                        message=f"Failed to compile RBAC permissions when trying "
                        f"to propagate permissions to '{role}'. "
                    ) from e

        # compile finished
        debug_log(
            f"RBAC permission compilation finished after {iteration_count} iterations.",
        )

        success_log(
            f"RBAC Compiled, result: \n{pformat(self._compiled_role_permissions)}"
        )

    def check_role(self, role):
        if role not in self.roles:
            raise InvalidRole(role)

    def check_role_has_permission(
        self,
        role: RoleType | Any,
        permission: PermissionType,
    ) -> None:
        self.check_role(role)

        if not permission in self._compiled_role_permissions[role]:
            raise InsufficientPermission(role, permission)
