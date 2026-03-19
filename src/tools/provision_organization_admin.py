from __future__ import annotations

import argparse
import asyncio
import logging

from src.config.settings import get_settings
from src.core.services import admin_user_app_service
from src.core.logging import configure_logging
from src.data.clients.postgres import init_db
from src.schemas.auth import PlatformAdminProvisionRequest

configure_logging(get_settings(), service_name="studyguru-admin-tool")
logger = logging.getLogger(__name__)


async def _run(args: argparse.Namespace) -> None:
    await init_db()
    payload = PlatformAdminProvisionRequest(
        organization_name=args.organization_name,
        admin_email=args.admin_email,
        password=args.password,
    )
    organization, admin = await admin_user_app_service.provision_organization_admin(payload)

    logger.info(
        "Provisioned organization admin successfully.",
        extra={
            "organization_id": organization.id,
            "organization_name": organization.name,
            "admin_user_id": admin.id,
            "admin_email": admin.email,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Provision an organization and its initial admin account."
    )
    parser.add_argument("--organization-name", required=True, help="Display name of the organization.")
    parser.add_argument("--admin-email", required=True, help="Email address for the organization admin.")
    parser.add_argument("--password", required=True, help="Initial password for the organization admin.")
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
