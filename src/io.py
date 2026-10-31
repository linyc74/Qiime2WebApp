import os
import re
import csv
import hashlib
import zipfile
from io import StringIO
from pathlib import Path
from typing import Iterator


def parse_md5(name: str, text: str) -> dict[str, str]:
    """
    Parse MD5 checksum file content into a filename-to-hash dictionary.

    Supports both standard ``<md5>  <filename>`` (or ``MD5 (file) = <hash>``)
    and single-hash ``<md5>`` sidecar files (e.g. ``sample.fastq.gz.md5``).
    """
    result: dict[str, str] = {}
    for raw_line in text.lstrip('\ufeff').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        bsd_match = re.match(r'^MD5\s*\((.+)\)\s*=\s*([0-9a-fA-F]{32})$', line)
        if bsd_match:
            filename = os.path.basename(bsd_match.group(1).strip())
            result[filename] = bsd_match.group(2).lower()
            continue
        parts = line.split(None, 1)
        if len(parts) == 2 and re.fullmatch(r'[0-9a-fA-F]{32}', parts[0]):
            filename = os.path.basename(parts[1].lstrip('*').strip())
            result[filename] = parts[0].lower()
        elif len(parts) == 1 and re.fullmatch(r'[0-9a-fA-F]{32}', parts[0]):
            if name.lower().endswith('.md5') and len(name) > 4:
                result[name[:-4]] = parts[0].lower()
    return result


def compute_file_md5(filepath: str, chunk_size: int = 1024 * 1024) -> str:
    md5 = hashlib.md5()
    with open(filepath, 'rb') as f:
        while chunk := f.read(chunk_size):
            md5.update(chunk)
    return md5.hexdigest()


def read_parameters(name: str, text: str) -> dict:
    suffix = Path(name).suffix.lower()
    text = text.lstrip('\ufeff')
    if suffix in ('.csv', '.tsv', '.tab'):
        rows = csv.reader(StringIO(text), delimiter=',' if suffix == '.csv' else '\t')
    elif suffix == '.txt':
        rows = (line.split(':', 1) for line in text.splitlines())
    else:
        raise ValueError('Choose a CSV, TSV, TAB, or TXT parameter file.')
    result = {}
    for row in rows:
        if not row or not row[0].strip():
            continue
        if len(row) > 2:
            raise ValueError('Each parameter row must contain a key and at most one value.')
        key = row[0].strip()
        value = row[1].strip() if len(row) == 2 else ''
        result[key] = value if value else True
    return result


def write_parameters(parameters: dict, suffix: str) -> bytes:
    output = StringIO(newline='')
    writer = csv.writer(output, delimiter=',' if suffix == '.csv' else '\t', lineterminator='\n')
    for key, value in parameters.items():
        if value is False:
            continue
        row = [key] if value is True else [key, str(value)]
        if suffix == '.txt':
            output.write(': '.join(row) + '\n')
        else:
            writer.writerow(row)
    return output.getvalue().encode('utf-8')


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
