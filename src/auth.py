import os
import json
import secrets
from fastapi import Request
from redis.asyncio import Redis
from authlib.integrations.starlette_client import OAuth
from .constant import REDIS_HOST, REDIS_PORT, SESSION_TTL, SESSION_COOKIE


redis = Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

oauth = OAuth()
oauth.register(
    name='google',
    client_id=os.environ['GOOGLE_CLIENT_ID'],
    client_secret=os.environ['GOOGLE_CLIENT_SECRET'],
    server_metadata_url=(
        'https://accounts.google.com/.well-known/openid-configuration'
    ),
    client_kwargs={
        'scope': 'openid email profile',
        'code_challenge_method': 'S256',
    },
)


async def get_user(request: Request) -> dict | None:
    sid = request.cookies.get(SESSION_COOKIE)
    if not sid:
        return None
    data = await redis.get(f'session:{sid}')
    return json.loads(data) if data else None


async def create_session(request: Request, user: dict) -> str:
    old_sid = request.cookies.get(SESSION_COOKIE)  # get old session ID if it exists
    if old_sid:
        await redis.delete(f'session:{old_sid}')

    sid = secrets.token_urlsafe(32)  # create new session ID
    await redis.set(
        f'session:{sid}', json.dumps(user), ex=SESSION_TTL
    )
    request.session.clear()
    return sid


async def delete_session(request: Request) -> None:
    sid = request.cookies.get(SESSION_COOKIE)
    if sid:
        await redis.delete(f'session:{sid}')
