from redis.asyncio import Redis

from app.core.config import Settings

redis_client: Redis | None = None


def init_redis(settings: Settings) -> None:
    global redis_client
    if redis_client is None:
        redis_client = Redis.from_url(settings.redis_url, decode_responses=True)


async def close_redis() -> None:
    global redis_client
    if redis_client is not None:
        await redis_client.aclose()
    redis_client = None


def get_redis() -> Redis:
    if redis_client is None:
        raise RuntimeError("Redis is not initialized")
    return redis_client
