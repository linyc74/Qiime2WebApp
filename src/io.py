import os
import re
import csv
import hashlib
from io import StringIO
from pathlib import Path


def parse_md5(name: str, text: str) -> dict[str, str]:
    """Parse MD5 checksum file content into a filename-to-hash mapping.

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
    """Compute the MD5 hex digest of a file on disk."""
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
