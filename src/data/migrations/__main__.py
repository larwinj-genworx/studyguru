from __future__ import annotations

import asyncio

from src.data.clients.postgres import engine
from src.data.migrations.runner import apply_migrations


async def _main() -> None:
    async with engine.begin() as conn:
        await apply_migrations(conn)


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
