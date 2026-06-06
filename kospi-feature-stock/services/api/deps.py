from fastapi import Request
import asyncpg
import redis.asyncio as redis_lib


def get_db(request: Request) -> asyncpg.Pool:
    return request.app.state.db


def get_redis(request: Request) -> redis_lib.Redis:
    return request.app.state.redis
