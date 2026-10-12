def date_to_season(month: int, day: int) -> str:
    """Meteorological season for month/day, northern hemisphere."""
    import datetime
    try:
        datetime.date(2000, int(month), int(day))
    except ValueError as exc:
        raise ValueError("invalid calendar date") from exc
    if not (1 <= int(month) <= 12):
        raise ValueError(f"month {month!r} outside [1, 12]")
    if not (1 <= int(day) <= 31):
        raise ValueError(f"day {day!r} outside [1, 31]")
    if month in (12, 1, 2):
        return "winter"
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    return "autumn"
