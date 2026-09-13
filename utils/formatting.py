from datetime import date


def display_date(value: str) -> str:
    return date.fromisoformat(value).strftime("%d %b %Y")
