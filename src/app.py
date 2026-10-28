import os
import secrets
from nicegui import ui
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from . import VERSION
from .view import PipelinePage
from .database import Database
from .auth import SESSION_TTL, SESSION_COOKIE, oauth, get_user, create_session, delete_session


BASE_URL = os.environ.get('BASE_URL', 'http://localhost:8080').rstrip('/')


app = FastAPI(version=VERSION)

app.add_middleware(
    SessionMiddleware,
    secret_key=secrets.token_urlsafe(32),
    session_cookie='oidc_state',
    max_age=600,
    same_site='lax',
    https_only=BASE_URL.startswith('https://'),
)


@app.get('/login')
async def login(request: Request):
    if str(request.base_url).rstrip('/') != BASE_URL:
        return RedirectResponse(f'{BASE_URL}/login')
    return await oauth.google.authorize_redirect(
        request, f'{BASE_URL}/auth/callback'
    )


@app.get('/auth/callback')
async def callback(request: Request) -> RedirectResponse:
    token = await oauth.google.authorize_access_token(request)  # authorize access token
    userinfo = token['userinfo']
    email = userinfo['email']

    db = Database()
    ret = db.execute(
        '''
            INSERT INTO users (email)
            VALUES (:email)
            ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email
            RETURNING id
        ''',
        {'email': email}
    )
    user_id = ret.scalar_one()

    sid = await create_session(request, {'user_id': user_id})

    response = RedirectResponse(BASE_URL, status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        sid,
        httponly=True,
        secure=BASE_URL.startswith('https://'),
        samesite='lax',
        max_age=SESSION_TTL,
        path='/',
    )
    return response


@ui.page('/')
async def home(request: Request):
    ui.colors(primary='#12329A', secondary='#25636b')

    user: dict | None = await get_user(request)

    if user is None:
        with ui.column().classes('w-full max-w-4xl mx-auto p-4 sm:p-8 gap-6'):
            with ui.row().classes('w-full items-center justify-between'):
                with ui.row().classes('items-baseline gap-2'):
                    ui.label('Qiime2 App').classes('text-3xl font-semibold')
                    ui.label(VERSION).classes('text-sm text-slate-400')
            ui.label('Please sign in').classes('text-sm text-slate-500')
            with ui.row().classes('w-full gap-3'):
                ui.button(
                    'Sign in with Google',
                    icon='login',
                    on_click=lambda: ui.navigate.to(f'{BASE_URL}/login'),
                )
        return

    async def logout():
        await delete_session(request)
        ui.navigate.to('/')

    PipelinePage(user_id=user['user_id'], on_logout=logout)


ui.run_with(app, title='Qiime2 App')
