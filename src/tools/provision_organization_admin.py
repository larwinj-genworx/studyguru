from __future__ import annotations

import argparse
import asyncio

from src.core.services import admin_user_app_service
from src.data.clients.postgres import init_db
from src.schemas.auth import PlatformAdminProvisionRequest


async def _run(args: argparse.Namespace) -> None:
    await init_db()
    payload = PlatformAdminProvisionRequest(
        organization_name=args.organization_name,
        admin_email=args.admin_email,
        password=args.password,
    )
    organization, admin = await admin_user_app_service.provision_organization_admin(payload)

    print("Provisioned organization admin successfully.")
    print(f"Organization ID: {organization.id}")
    print(f"Organization Name: {organization.name}")
    print(f"Admin User ID: {admin.id}")
    print(f"Admin Email: {admin.email}")


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
