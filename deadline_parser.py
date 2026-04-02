# deadline_parser.py
from datetime import datetime, timedelta, date
import re


WEEKDAYS = {
    "понедельник": 0,
    "понед": 0,
    "пн": 0,

    "вторник": 1,
    "втор": 1,
    "вт": 1,

    "среда": 2,
    "ср": 2,

    "четверг": 3,
    "четв": 3,
    "чт": 3,

    "пятница": 4,
    "пятн": 4,
    "пт": 4,

    "суббота": 5,
    "суб": 5,
    "сб": 5,

    "воскресенье": 6,
    "воскр": 6,
    "вс": 6
}


MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12
}


def _next_weekday(target_weekday: int, from_date: date | None = None) -> date:
    """
    target_weekday: Monday=0 ... Sunday=6
    """
    if from_date is None:
        from_date = datetime.now().date()

    days_ahead = target_weekday - from_date.weekday()
    if days_ahead <= 0:
        days_ahead += 7

    return from_date + timedelta(days=days_ahead)


def parse_deadline(text: str) -> str | None:
    """
    Пытается распознать дедлайн из текста.
    Возвращает строку YYYY-MM-DD или None.
    """
    if not text:
        return None

    text = text.lower().strip()
    today = datetime.now().date()

    # завтра
    if "завтра" in text:
        return (today + timedelta(days=1)).isoformat()

    # послезавтра
    if "послезавтра" in text:
        return (today + timedelta(days=2)).isoformat()

    # сегодня
    if "сегодня" in text:
        return today.isoformat()

    # через N дней
    m = re.search(r"через\s+(\d+)\s+дн", text)
    if m:
        days = int(m.group(1))
        return (today + timedelta(days=days)).isoformat()

    # до понедельника / к пятнице / в понедельник
    for key, weekday in WEEKDAYS.items():
        if key in text:
            return _next_weekday(weekday, today).isoformat()

    # 10 апреля / 5 мая
    m = re.search(r"(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)", text)
    if m:
        day = int(m.group(1))
        month = MONTHS[m.group(2)]
        year = today.year

        # если дата уже прошла в этом году -> следующий год
        try:
            d = date(year, month, day)
            if d < today:
                d = date(year + 1, month, day)
            return d.isoformat()
        except ValueError:
            return None

    # YYYY-MM-DD
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if m:
        return m.group(1)

    return None