import smtplib
from email.mime.text import MIMEText
from config import SMTP_SERVER, SMTP_PORT, EMAIL_LOGIN, EMAIL_PASSWORD


def send_task_email(recipients: list[str], task_text: str, deadline: str):
    subject = "Новая задача"
    body = f"Задача: {task_text}\nСрок: {deadline}"

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = EMAIL_LOGIN
    msg["To"] = ", ".join(recipients)

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_LOGIN, EMAIL_PASSWORD)
        server.sendmail(EMAIL_LOGIN, recipients, msg.as_string())


def send_cancel_email(recipients: list[str], task_text: str, deadline: str):
    subject = "Задача отменена"
    body = f"Задача отменена.\n\nЗадача: {task_text}\nСрок: {deadline}"

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = EMAIL_LOGIN
    msg["To"] = ", ".join(recipients)

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_LOGIN, EMAIL_PASSWORD)
        server.sendmail(EMAIL_LOGIN, recipients, msg.as_string())