from pydantic import BaseModel


# DO NOT CHANGE THE CODE OF THIS CLASS UNLESS YOU KNOW WHAT YOU ARE DOING.
class RoleInfo(BaseModel):
    name: str = ''
    password: str = ''

    def auth(self, role: 'RoleInfo') -> bool:
        """
        Check if the input RoleInfo could be authenticated as this role.
        :param role:
        :return:
        """
        return self.name == role.name and self.password == role.password


# define the valid roles and corresponding password
ROLE_LIST: list[RoleInfo] = [
    RoleInfo(name='admin', password='adminadmin'),
    RoleInfo(name='user', password='useruser'),
]

# Generated secret key used to generate JWT token for users.
PYJWT_SECRET_KEY: str = 'YOUR_OWN_SECRET_KEY_HERE'
PYJWT_ALGORITHM: str = 'HS256'

# Determine how many days before a JWT token invalid since it has been created
# with unit HOURS.
TOKEN_EXPIRES_DELTA_HOURS: int = 240

# Controls the cookies key in the frontend to store JWT info.
JWT_FRONTEND_COOKIE_KEY: str = 'role_info'
