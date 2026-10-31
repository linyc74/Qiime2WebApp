import os
import zipfile
from typing import Iterator
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from .database import Database
from .utils import to_valid_filename
from .auth import oauth, get_user, create_session
from .constant import BASE_URL, USERS_DIR, SESSION_TTL, SESSION_COOKIE


router = APIRouter()


@router.get('/login')
async def login(request: Request):
    if str(request.base_url).rstrip('/') != BASE_URL:
        return RedirectResponse(f'{BASE_URL}/login')
    return await oauth.google.authorize_redirect(
        request, f'{BASE_URL}/auth/callback'
    )


@router.get('/auth/callback')
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


@router.get('/download-jobs')
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
