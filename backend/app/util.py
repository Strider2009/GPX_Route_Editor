import re


def slugify(value: str) -> str:
    value = re.sub(r"[^\w\-]+", "-", value.strip().lower())
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "route"
