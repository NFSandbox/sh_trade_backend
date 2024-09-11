# Version of backend
BACKEND_API_VER: str = "0.1.1"

# If this program are running on a VPS
ON_CLOUD: bool = False

# allow origins to access backend
# since here we use allowCredentials = True
# there could not be "*" wildcard matcher in this list since we need to enable WithCredential feature.
ALLOWED_ORIGINS: list[str] = [
    "https://your-frontend-website-address.com",
    "https://your-backend-address.com",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

PORT: int = 8000

# value in minutes that represents the max distance limit when doing data point spreading.
# we recommend this value be concurred with the ``backend_update_time_duration``.
POINT_SPREADING_DIS_LIMIT_MIN: int = 60

# time range tolerance when checking if a point need to be spread.
# For more info, checkout docs/usage_calc.md - Data Point Spreading.
POINT_SPREADING_TOLERANCE_MIN: int = 10

# the duration between two data of backend.
# this value will be used to calculate the factor when converting usage list to the unit of usage per hour.
BACKEND_CATCH_TIME_DURATION_MIN: int = 60
