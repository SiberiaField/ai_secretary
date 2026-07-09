import asyncio
import logging
from typing import List, Dict, Any
from pathlib import Path

import pandas as pd
from pandas import DataFrame
from pydantic import BaseModel
from jinja2 import Environment

from task_managers import Task, TaskStatus, FileTaskManager, register_data_model
from config import config

logger = logging.getLogger(__name__)


@register_data_model
class SendingTask(BaseModel):
    student_ids: List[str]


class IncomingTasksService():
    def __init__(
            self,
            tasks: List[Task],
            jinja_env: Environment,
            incoming_tasks_manager: FileTaskManager,
            output_dir: Path
        ):
        self.jinja_env = jinja_env
        self.incoming_tasks_manager = incoming_tasks_manager
        self.tasks = tasks
        self.output_dir = output_dir
    
    def _render_letter(self, template_name: str, context: Dict[str, Any]) -> str:
        """Рендерит текстовый/HTML шаблон письма через Jinja2."""
        template = self.jinja_env.get_template(template_name)
        return template.render(**context)

    def _render_word_document(self, template_name: str, context: Dict[str, Any], output_path: Path) -> Path:
        """Заглушка для рендеринга Word-документа. Заменить на docxtpl при необходимости."""
        logger.info("[Sending Agent] Word-документ не сгенерирован (заглушка)")
        return output_path

    def _send_email(self, recipient_email: str, subject: str, body: str, attachments: List[Path] | None = None) -> None:
        """Плейсхолдер отправки письма через IMAP/SMTP."""
        logger.info("[Sending Agent] Отправка письма (плейсхолдер)")

    async def _send_reminders(self, task_data: SendingTask) -> None:
        """Рассылает письма научным руководителям студентов из задачи."""
        students_df: DataFrame = await asyncio.to_thread(pd.read_excel, io=config.database.excel_path, sheet_name=0)
        students_df["id"] = students_df["id"].astype(str)
        students_df["Руководитель практики"] = students_df["Руководитель практики"].astype(str)

        practice_leader_df: DataFrame = await asyncio.to_thread(pd.read_excel, io=config.database.excel_path, sheet_name=1)
        practice_leader_df["id"] = students_df["id"].astype(str)

        for student_id in task_data.student_ids:
            student = students_df[students_df["id"] == student_id]
            student_fio = student.get("ФИО").item()
            supervisor_id = student.get("Руководитель практики").item()

            if not supervisor_id:
                logger.warning("[Sending Agent] Пропускаем студента id=%s (%s): не указан научный руководитель", student_id, student_fio)
                continue

            supervisor_rows = practice_leader_df[practice_leader_df["id"] == supervisor_id]

            if supervisor_rows.empty:
                logger.warning(
                    "[Sending Agent] Руководитель с id=%s не найден в справочнике. Студент: id=%s (%s)", supervisor_id, student_id, student_fio
                )
                continue

            supervisor = supervisor_rows.iloc[0]
            supervisor_email = supervisor.get("Почта")
            if not supervisor_email:
                logger.warning("[Sending Agent] У руководителя с id=%s не указана почта. Пропускаем.", supervisor_id)
                continue

            context = {"secretary_name": config.secretary.name}
            body = await asyncio.to_thread(self._render_letter, template_name="reminder.jinja2", context=context)
            subject = f"Индивидуальные задания для студента {student_fio}"

            attachments: List[Path] = []
            if config.sending_agent.generate_example_doc:
                output_path = self.output_dir / f"task_{student_id}.docx"
                self._render_word_document(
                    template_name="indi",
                    context=context,
                    output_path=output_path
                )
                if output_path.exists():
                    attachments.append(output_path)

            try:
                self._send_email(
                    recipient_email=supervisor_email,
                    subject=subject,
                    body=body,
                    attachments=attachments,
                )
            except Exception as e:
                logger.exception("[Sending Agent] Ошибка при отправке письма руководителю %s: %s", supervisor_email, e)

    async def run(self):
        logger.info(f"[Sending Agent] Found tasks -> process")
        for iter, task in enumerate(self.tasks):
            await self.incoming_tasks_manager.update_task(task.id, TaskStatus.IN_PROGRESS, None)
            logger.info(f"[Sending Agent] Task {iter}/{len(self.tasks)} started.")

            task_data: SendingTask = task.get_typed_data()
            try:
                await self._send_reminders(task_data)
            except Exception as e:
                await self.incoming_tasks_manager.update_task(task.id, TaskStatus.FAILED, None)
                logger.error(f"[Sending Agent] Error occured during sending reminders. Task ID: {task.id}. Error: {e}", exc_info=True)
                continue
                
            await self.incoming_tasks_manager.update_task(task.id, TaskStatus.COMPLETED, None)