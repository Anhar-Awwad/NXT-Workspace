import logging
import os
from typing import Optional, TypedDict

import httpx

logger = logging.getLogger(__name__)

NEXTCLOUD_URL = os.getenv("NEXTCLOUD_URL", "http://nextcloud").rstrip("/")


class NextcloudUser(TypedDict):
    username: str
    display_name: str
    groups: list[str]


async def verify_nextcloud_user(username: str, password: str) -> Optional[NextcloudUser]:
    if not username or not password:
        return None

    url = f"{NEXTCLOUD_URL}/ocs/v1.php/cloud/user"
    try:
        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
            response = await client.get(
                url,
                auth=(username, password),
                headers={"OCS-APIRequest": "true", "Accept": "application/json"},
                params={"format": "json"},
            )
    except httpx.RequestError as e:
        logger.error(f"Could not reach Nextcloud at {NEXTCLOUD_URL}: {e}")
        return None

    if response.status_code != 200:
        logger.info(f"Nextcloud auth failed for user '{username}': HTTP {response.status_code}")
        return None

    try:
        data = response.json()["ocs"]["data"]
    except (KeyError, ValueError) as e:
        logger.error(f"Unexpected Nextcloud OCS response shape: {e}")
        return None

    groups = data.get("groups", [])
    return NextcloudUser(
        username=data.get("id", username),
        display_name=data.get("display-name", username),
        groups=list(groups) if groups else [],
    )