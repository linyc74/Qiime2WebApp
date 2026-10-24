import csv
from io import StringIO
from pathlib import Path


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
