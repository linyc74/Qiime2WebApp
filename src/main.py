import secrets
from nicegui import ui
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from . import view  # registers @ui.page('/')
from .api import router  # connects all API endpoints
from .constant import ASSETS_DIR, BASE_URL, VERSION


app = FastAPI(version=VERSION)
app.add_middleware(
    SessionMiddleware,
    secret_key=secrets.token_urlsafe(32),
    session_cookie='oidc_state',
    max_age=600,
    same_site='lax',
    https_only=BASE_URL.startswith('https://'),
)
app.include_router(router)

ui.run_with(
    app,
    title='QIIME 2 App',
    favicon=f'{ASSETS_DIR}/qiime2.png',
)
