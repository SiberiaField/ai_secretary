import asyncio
import logging
from typing import List, Dict, Any
from pathlib import Path

import pandas as pd
from pandas import DataFrame
from pydantic import BaseModel
from jinja2 import Environment, PackageLoader

from task_managers import FileTaskManager, TaskStatus, register_data_model
from config import config

logger = logging.getLogger(__name__)


incoming_tasks_client = FileTaskManager(config.sending_agent.tasks_root_dir)

@register_data_model
class SendingTask(BaseModel):
    students: List[str]


jinja_env = Environment(
    loader=PackageLoader(
        "agents.sending_agent",
        "templates"
    )
)

output_dir = Path(config.sending_agent.output_dir)
output_dir.mkdir(parents=True, exist_ok=True)


def render_letter(template_name: str, context: Dict[str, Any]) -> str:
    """Рендерит текстовый/HTML шаблон письма через Jinja2."""
    template = jinja_env.get_template(template_name)
    return template.render(**context)


def render_word_document(template_name: str, context: Dict[str, Any], output_path: Path) -> Path:
    """Заглушка для рендеринга Word-документа. Заменить на docxtpl при необходимости."""
    logger.info("Word-документ не сгенерирован (заглушка): %s", output_path)
    return output_path


def send_email(recipient_email: str, subject: str, body: str, attachments: List[Path] | None = None) -> None:
    """Плейсхолдер отправки письма через IMAP/SMTP."""
    logger.info(
        "Отправка письма (плейсхолдер): to=%s, subject=%r, attachments=%s",
        recipient_email, subject, [str(a) for a in (attachments or [])],
    )


async def send_reminders(task_data: SendingTask) -> None:
    """Рассылает письма научным руководителям студентов из задачи."""
    students_df: DataFrame = pd.read_excel(config.database.excel_path, sheet_name=0)
    practice_leader_df: DataFrame = pd.read_excel(config.database.excel_path, sheet_name=1)

    for student_fio in task_data.students:
        student = students_df[students_df["ФИО"] == student_fio].iloc[0]
        student_id = student.get("id")
        student_fio = student.get("ФИО")
        supervisor_id = student.get("Руководитель практики")

        if not supervisor_id:
            logger.warning("Пропускаем студента id=%s (%s): не указан научный руководитель", student_id, student_fio)
            continue

        supervisor_rows = practice_leader_df[practice_leader_df["id"] == supervisor_id]

        if supervisor_rows.empty:
            logger.warning(
                "Руководитель с id=%s не найден в справочнике. Студент: id=%s (%s)", supervisor_id, student_id, student_fio
            )
            continue

        supervisor = supervisor_rows.iloc[0]
        supervisor_email = supervisor.get("Почта")
        if not supervisor_email:
            logger.warning("У руководителя с id=%s не указана почта. Пропускаем.", supervisor_id)
            continue

        context = {
            "student": student,
            "supervisor": supervisor.to_dict(),
        }
        body = render_letter("reminder.jinja2", context)
        subject = f"Индивидуальные задания для студента {student_fio}"

        attachments: List[Path] = []
        if config.sending_agent.generate_example_doc:
            output_path = output_dir / f"task_{student_id}.docx"
            render_word_document(
                template_name="indi",
                context=context,
                output_path=output_path,
            )
            if output_path.exists():
                attachments.append(output_path)

        try:
            send_email(
                recipient_email=supervisor_email,
                subject=subject,
                body=body,
                attachments=attachments,
            )
        except Exception as e:
            logger.exception("Ошибка при отправке письма руководителю %s: %s", supervisor_email, e)


async def main():
    while True:
        pending_tasks = incoming_tasks_client.get_tasks_by_status(TaskStatus.PENDING)
        if pending_tasks:
            for iter, pending_task in enumerate(pending_tasks):
                incoming_tasks_client.update_task(pending_task.id, TaskStatus.IN_PROGRESS, None)
                logger.info(f"[Sending Agent] Task {iter}/{len(pending_tasks)} started.")

                task_data: SendingTask = pending_task.get_typed_data()
                try:
                    await send_reminders(task_data)
                except Exception as e:
                    logger.error(f"[Sending Agent] Error occured during sending reminders. Task ID: {pending_task.id}. Error: {e}", exc_info=True)
                    continue
                
                incoming_tasks_client.update_task(pending_task.id, TaskStatus.COMPLETED, None)
        await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())
