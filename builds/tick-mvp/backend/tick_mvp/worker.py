import asyncio
import sys

from tick_mvp.config import get_settings


async def run(role: str) -> None:
    settings = get_settings()
    print(f"tick-mvp {role} started env={settings.tick_env} venue={settings.default_venue}", flush=True)
    while True:
        await asyncio.sleep(30)


def main() -> None:
    role = sys.argv[1] if len(sys.argv) > 1 else "worker"
    asyncio.run(run(role))


if __name__ == "__main__":
    main()

