from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from database import get_active_tasks, get_task_recipients
from email_sender import send_task_email
import logging

scheduler = BackgroundScheduler()
scheduler.start()


def schedule_task_reminders():
    tasks = get_active_tasks()

    for task in tasks:
        if not task["deadline"]:
            continue

        deadline_dt = datetime.fromisoformat(task["deadline"])
        recipients_rows = get_task_recipients(task["id"])
        recipients = [r["email"] for r in recipients_rows]

        reminder_times = [
            deadline_dt - timedelta(days=1),
            deadline_dt,
            deadline_dt + timedelta(days=1)
        ]

        for rt in reminder_times:
            if rt < datetime.now():
                continue

            scheduler.add_job(
                send_task_email,
                "date",
                run_date=rt,
                args=[recipients, task["task_text"], task["deadline"]],
                id=f"task_{task['id']}_{rt.isoformat()}",
                replace_existing=True
            )

        logging.info(f"Reminders scheduled for task {task['id']}")