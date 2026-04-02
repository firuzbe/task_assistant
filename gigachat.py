# gigachat.py
import requests
import uuid
import json
import urllib3
from datetime import datetime

from config import GIGACHAT_AUTH_KEY, GIGACHAT_AUTH_URL, GIGACHAT_API_URL

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def get_access_token() -> str:
    headers = {
        "Authorization": f"Basic {GIGACHAT_AUTH_KEY}",
        "RqUID": str(uuid.uuid4()),
        "Content-Type": "application/x-www-form-urlencoded"
    }

    data = {"scope": "GIGACHAT_API_PERS"}

    resp = requests.post(GIGACHAT_AUTH_URL, headers=headers, data=data, verify=False)

    if resp.status_code != 200:
        raise Exception(f"Ошибка получения токена: {resp.text}")

    return resp.json()["access_token"]


def parse_task_with_gigachat(text: str, employees: list[str]) -> dict:
    """
    Парсер: извлекает текст задачи, дедлайн и список email получателей.
    В prompt передаём текущую дату, чтобы LLM корректно считала "до понедельника".
    """
    token = get_access_token()
    today = datetime.now().strftime("%Y-%m-%d")

    system_prompt = f"""
Ты ассистент для постановки задач.
Сегодняшняя дата: {today}

Твоя задача:
- выделить текст задачи
- выделить срок (если есть)
- выделить адресатов

Верни JSON строго в формате:
{{
  "task_text": "...",
  "deadline": "YYYY-MM-DD" или null,
  "recipients": ["email1", "email2"]
}}

Если срок указан словами ("до понедельника", "завтра", "через 3 дня"),
то переведи срок в дату относительно сегодняшней даты.

Разрешённые сотрудники (используй только их email):
{employees}

Если срок не указан — deadline null.
Если адресаты не указаны — recipients пустой список.
Верни ТОЛЬКО JSON, без комментариев и текста.
"""

    payload = {
        "model": "GigaChat",
        "messages": [
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": text.strip()}
        ],
        "temperature": 0.2
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        resp = requests.post(GIGACHAT_API_URL, headers=headers, json=payload, verify=False, timeout=60)
    except requests.exceptions.RequestException as e:
        return {"status": 500, "message": str(e)}

    if resp.status_code != 200:
        return {"status": resp.status_code, "message": resp.text}

    data = resp.json()

    try:
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception:
        return {"status": 500, "message": "Ошибка парсинга ответа Gigachat"}


def parse_task_with_assignee(text: str, employees_names: list[str]) -> dict:
    """
    Парсер для режима /newtask:
    извлекает исполнителя (ФИО/фамилия), текст задачи и дедлайн.
    """
    token = get_access_token()
    today = datetime.now().strftime("%Y-%m-%d")

    system_prompt = f"""
Ты помощник руководителя.
Сегодняшняя дата: {today}

Из текста извлеки задачу и исполнителя.

Верни JSON строго в формате:

{{
  "task_text": "...",
  "deadline": "YYYY-MM-DD" или null,
  "assignee": "Фамилия или ФИО"
}}

Исполнитель должен быть строго из списка:
{employees_names}

Если срок указан словами ("до понедельника", "к пятнице", "завтра", "через 2 дня"),
то переведи срок в дату относительно сегодняшней даты.

Если исполнитель не найден — assignee null.
Если срок не найден — deadline null.

Верни ТОЛЬКО JSON, без комментариев.
"""

    payload = {
        "model": "GigaChat",
        "messages": [
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": text.strip()}
        ],
        "temperature": 0.2
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        resp = requests.post(GIGACHAT_API_URL, headers=headers, json=payload, verify=False, timeout=60)
    except requests.exceptions.RequestException as e:
        return {"status": 500, "message": str(e)}

    if resp.status_code != 200:
        return {"status": resp.status_code, "message": resp.text}

    data = resp.json()

    try:
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception:
        return {"status": 500, "message": "Ошибка парсинга ответа Gigachat"}