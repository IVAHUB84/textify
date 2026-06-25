__version__: str = "1.10.0"


def parse_version(s: str) -> tuple[int, int, int]:
    try:
        parts = s.split(".")
        if len(parts) != 3:
            return (-1, -1, -1)
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, AttributeError):
        return (-1, -1, -1)
