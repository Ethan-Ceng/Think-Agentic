"""Import an immutable standard Skill package into the Marketplace."""

import argparse
import asyncio
import json
from pathlib import Path

from app.dependencies.infrastructure import (
    get_skill_package_service,
    get_skill_package_storage,
)
from app.dependencies.uow import get_uow
from app.extensions.database import get_db
from app.services.marketplace_skill_service import MarketplaceSkillService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Skill directory or .skill/.zip package")
    parser.add_argument("--display-name")
    parser.add_argument("--description")
    parser.add_argument("--changelog", default="")
    parser.add_argument("--version", type=int, dest="expected_version")
    return parser.parse_args()


async def run(args: argparse.Namespace) -> dict:
    database = get_db()
    await database.init()
    try:
        service = MarketplaceSkillService(
            uow_factory=get_uow,
            package_service=get_skill_package_service(),
            package_storage=get_skill_package_storage(),
        )
        result = await service.import_package(
            args.source,
            display_name=args.display_name,
            description=args.description,
            changelog=args.changelog,
            expected_version=args.expected_version,
        )
        return result.structured_output()
    finally:
        await database.shutdown()


def main() -> None:
    print(json.dumps(asyncio.run(run(parse_args())), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
