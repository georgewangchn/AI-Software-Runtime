def is_leap_year(year):
    return year % 4 == 0

def days_in_month(year, month):
    if month in (4, 6, 9, 11):
        return 30
    elif month == 2:
        return 29 if is_leap_year(year) else 28
    return 31

def parse_date(date_str):
    parts = date_str.split("-")
    if len(parts) != 3:
        raise ValueError("Invalid format, expected YYYY-MM-DD")
    y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
    if m < 1 or m > 12:
        raise ValueError("Invalid month")
    max_days = days_in_month(y, m)
    if d < 1 or d > max_days:
        raise ValueError("Invalid day")
    return (y, m, d)
