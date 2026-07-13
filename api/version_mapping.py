"""Protocol API version to robot stack version mappings."""

from evaluate.env_config import ENVIRONMENT_CONFIGS

# Mapping of protocol API versions to robot stack release versions
# Source: https://docs.opentrons.com/v2/versioning.html
# Only includes versions 2.20 (8.0.0) and up
PROTOCOL_API_TO_ROBOT_STACK = {
    "2.13": "6.2.1",
    "2.20": "8.0.0",
    "2.21": "8.2.0",
    "2.22": "8.3.0",
    "2.23": "8.4.0",
    "2.24": "8.5.0",
    "2.25": "8.6.0",
    "2.26": "8.7.0",
    "2.27": "8.8.0",
    "2.28": "9.0.0",
    "2.29": "9.1.1",
}

VALID_ROBOT_VERSIONS = set(ENVIRONMENT_CONFIGS.keys())
# The special 'next' value tracks the latest published alpha build of Opentrons.
