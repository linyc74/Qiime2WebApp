import os
import subprocess


def get_app_version() -> str:
    """Return the running git commit as the app version, e.g. 'a1b2c3d · 2026-11-01'.

    Resolution order:
        1. The APP_VERSION environment variable, if set.
        2. The short SHA and commit date of HEAD in the project repository.
        3. 'dev' if neither is available.
    """
    env = os.environ.get('APP_VERSION')
    if env:
        return env

    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        sha = __git(['rev-parse', '--short', 'HEAD'], cwd=repo_dir)
        date = __git(['log', '-1', '--format=%cs'], cwd=repo_dir)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return 'dev'

    return f'{sha} · {date}'


def __git(args: list[str], cwd: str) -> str:
    return subprocess.check_output(
        ['git', *args],
        cwd=cwd,
        stderr=subprocess.DEVNULL,
    ).decode().strip()
