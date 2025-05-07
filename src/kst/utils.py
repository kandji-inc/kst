import re
import unicodedata

from ruamel.yaml import YAML

yaml = YAML()
yaml.indent(mapping=2, sequence=4, offset=2)


def sanitize_filename(value: str) -> str:
    replacement = "_"
    max_length = 255

    # https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file#naming-conventions
    # Linux/macOS don't allow / or \0
    invalid_chars_pattern = re.compile(r'[<>:"/\\|?*\x00-\x1F]')

    # https://docs.python.org/3/library/unicodedata.html#unicodedata.normalize
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")

    # Replace invalid characters with the replacement character then collapse
    value = re.sub(invalid_chars_pattern, replacement, value)
    value = re.sub(f"{replacement}+", replacement, value)

    # Strip leading/trailing replacement characters and spaces
    # Strip trailing periods (for Windows)
    value = value.lstrip(" ")
    value = value.rstrip(". ")

    if not value:
        return replacement

    return value[:max_length]
