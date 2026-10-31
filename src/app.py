import os
import secrets
import zipfile
from nicegui import ui
from typing import Iterator
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from starlette.middleware.sessions import SessionMiddleware
from .database import Database
from .view import PipelinePage, to_valid_filename
from .auth import oauth, get_user, create_session, delete_session
from .constant import VERSION, BASE_URL, ASSETS_DIR, USERS_DIR, SESSION_TTL, SESSION_COOKIE


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


@app.get('/download-jobs')
async def download_jobs(
        request: Request,
        job_timestamps: list[str] = Query(...)) -> StreamingResponse:
    
    user: dict | None = await get_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail='Unauthorized')

    user_id = user['user_id']
    db = Database()
    email = db.execute(
        '''
            SELECT email FROM users WHERE id = :user_id
        ''',
        {'user_id': user_id}
    ).scalar_one()
    user_job_dir = f'{USERS_DIR}/{user_id}_{to_valid_filename(email)}/jobs'

    return StreamingResponse(
        iter_zip_jobs(user_job_dir, job_timestamps),
        media_type='application/zip',
        headers={'Content-Disposition': 'attachment; filename="jobs.zip"'},
    )


class _ZipStreamBuffer:
    """Write-only buffer that forces zipfile.ZipFile into streaming mode."""

    def __init__(self) -> None:
        self._chunks: list[bytes] = []
        self._pos: int = 0

    def write(self, data: bytes) -> int:
        self._chunks.append(data)
        self._pos += len(data)
        return len(data)

    def tell(self) -> int:
        return self._pos

    def seekable(self) -> bool:
        return False

    def flush(self) -> None:
        pass

    def pop_bytes(self) -> bytes:
        if not self._chunks:
            return b''
        data = b''.join(self._chunks)
        self._chunks.clear()
        return data


def iter_zip_jobs(
        user_job_dir: str,
        job_timestamps: list[str],
        chunk_size: int = 64 * 1024) -> Iterator[bytes]:
    """Stream a ZIP archive of selected job directories chunk by chunk.

    Args:
        user_job_dir: Base job directory for the user.
        job_timestamps: List of job timestamps to include.
        chunk_size: Uncompressed read chunk size in bytes.

    Yields:
        Compressed ZIP archive bytes chunks.
    """
    buf = _ZipStreamBuffer()
    with zipfile.ZipFile(buf, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
        for job_timestamp in job_timestamps:
            job_dir = f'{user_job_dir}/{job_timestamp}'
            if not os.path.isdir(job_dir):
                continue
            for root, _, files in os.walk(job_dir):
                for file in files:
                    filepath = f'{root}/{file}'
                    if not os.path.isfile(filepath):
                        continue
                    arcname = os.path.relpath(filepath, user_job_dir)
                    zinfo = zipfile.ZipInfo.from_file(filepath, arcname)
                    zinfo.compress_type = zipfile.ZIP_DEFLATED

                    with zf.open(zinfo, mode='w') as dest, open(filepath, 'rb') as src:
                        while chunk := src.read(chunk_size):
                            dest.write(chunk)
                            if data := buf.pop_bytes():
                                yield data

                    if data := buf.pop_bytes():
                        yield data

    if data := buf.pop_bytes():
        yield data


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


ui.run_with(
    app,
    title='QIIME 2 App',
    favicon=f'{ASSETS_DIR}/qiime2.png',
)
