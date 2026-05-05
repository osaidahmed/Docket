from csv import DictReader

from integrations.imports.helpers import MediaImportError


def decode_csv_file(file):
    """Return a DictReader over a UTF-8 decoded uploaded file."""
    try:
        decoded = file.read().decode("utf-8").splitlines()
    except UnicodeDecodeError as e:
        msg = "Invalid file format. Please upload a CSV file."
        raise MediaImportError(msg) from e
    return DictReader(decoded)
