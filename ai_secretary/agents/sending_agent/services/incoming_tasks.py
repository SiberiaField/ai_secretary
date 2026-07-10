import asyncio
import logging
from typing import List, Dict, Any
from pathlib import Path
from enum import Enum

import pandas as pd
from pandas import DataFrame
from pydantic import BaseModel, Field
from jinja2 import Environment

from task_managers import Task, TaskStatus, FileTaskManager, register_data_model
from config import config

logger = logging.getLogger(__name__)


class StudentStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"


class StudentInfo(BaseModel):
    id: str | None = Field(default=None)
    result: StudentStatus | None = Field(default=None)
    extra: str | None = Field(default=None)


class ReportData(BaseModel):
    num_of_students: int = Field(default=0)
    num_of_success: int = Field(default=0)
    students: List[StudentInfo] = Field(default_factory=list)


@register_data_model
class SendingTask(BaseModel):
    student_ids: List[str]
    report: ReportData | None = Field(default=None)


class IncomingTasksService():
    def __init__(
            self,
            tasks: List[Task],
            jinja_env: Environment,
            incoming_tasks_manager: FileTaskManager,
            sorting_agent_msgs_manager: FileTaskManager,
            output_dir: Path
        ):
        self.jinja_env = jinja_env
        self.incoming_tasks_manager = incoming_tasks_manager
        self.sorting_agent_msgs_manager = sorting_agent_msgs_manager
        self.tasks = tasks
        self.output_dir = output_dir
    
    def _render_letter(self, template_name: str, context: Dict[str, Any]) -> str:
        """Рендерит текстовый/HTML шаблон письма через Jinja2."""
        template = self.jinja_env.get_template(template_name)
        return template.render(**context)
    
    async def _send_report_to_sorting_agent(self, report_data: ReportData, task_status: TaskStatus, task_id: str):
        context = {
            "status": task_status.value,
            "num_of_students": report_data.num_of_students,
            "num_of_success": report_data.num_of_success,
            "detailed_report_path": str(config.sending_agent.tasks_root_dir / task_status.value / task_id)
        }
        report_content = self._render_letter("report.jinja2", context)
        await self.sorting_agent_msgs_manager.create_task({"agent_name": "Агент-рассыльщик", "content": report_content}, "AgentMsg")
        logger.info("[Sending Agent] Sent report to sorting agent")

    def _render_word_document(self, template_name: str, context: Dict[str, Any], output_path: Path) -> Path:
        """Заглушка для рендеринга Word-документа. Заменить на docxtpl при необходимости."""
        logger.info("[Sending Agent] Word-документ не сгенерирован (заглушка)")
        return output_path

    def _send_email(self, recipient_email: str, subject: str, body: str, attachments: List[Path] | None = None) -> None:
        """Плейсхолдер отправки письма через IMAP/SMTP."""
        logger.info("[Sending Agent] Отправка письма (плейсхолдер)")

    async def _send_reminders(self, task_data: SendingTask):
        """Рассылает письма научным руководителям студентов из задачи."""
        students_df: DataFrame = await asyncio.to_thread(pd.read_excel, io=config.database.excel_path, sheet_name=0)
        students_df["id"] = students_df["id"].astype(str)
        students_df["Руководитель практики"] = students_df["Руководитель практики"].astype(str)

        practice_leader_df: DataFrame = await asyncio.to_thread(pd.read_excel, io=config.database.excel_path, sheet_name=1)
        practice_leader_df["id"] = practice_leader_df["id"].astype(str)

        if task_data.report is None:
            task_data.report = ReportData()

        task_data.report.num_of_students = len(task_data.student_ids)
        task_data.report.num_of_success = 0
        task_data.report.students = []

        for student_id in task_data.student_ids:
            student = students_df[students_df["id"] == student_id]

            # Проверка: студент найден в базе
            if student.empty:
                reason = "Студент не найден в базе данных"
                logger.warning("[Sending Agent] Пропускаем студента id=%s: %s", student_id, reason)
                task_data.report.students.append(
                    StudentInfo(result=StudentStatus.FAILED, extra=reason)
                )
                continue

            student_fio = student.get("ФИО").item()
            supervisor_id = student.get("Руководитель практики").item()

            # Проверка: указан научный руководитель
            if not supervisor_id or supervisor_id == "nan":
                reason = "не указан научный руководитель"
                logger.warning(
                    "[Sending Agent] Пропускаем студента id=%s (%s): %s",
                    student_id, student_fio, reason
                )
                task_data.report.students.append(
                    StudentInfo(id=student_id, result=StudentStatus.FAILED, extra=reason)
                )
                continue

            supervisor_rows = practice_leader_df[practice_leader_df["id"] == supervisor_id]

            # Проверка: руководитель найден в справочнике
            if supervisor_rows.empty:
                reason = f"Руководитель с id={supervisor_id} не найден в справочнике"
                logger.warning(
                    "[Sending Agent] %s. Студент: id=%s (%s)",
                    reason, student_id, student_fio
                )
                task_data.report.students.append(
                    StudentInfo(id=student_id, result=StudentStatus.FAILED, extra=reason)
                )
                continue

            supervisor = supervisor_rows.iloc[0]
            supervisor_email = supervisor.get("Почта")

            # Проверка: у руководителя указана почта
            if not supervisor_email or pd.isna(supervisor_email):
                reason = f"У руководителя с id={supervisor_id} не указана почта"
                logger.warning("[Sending Agent] %s. Пропускаем.", reason)
                task_data.report.students.append(
                    StudentInfo(id=student_id, result=StudentStatus.FAILED, extra=reason)
                )
                continue

            context = {"secretary_name": config.secretary.name}
            body = await asyncio.to_thread(
                self._render_letter, template_name="reminder.jinja2", context=context
            )
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
                task_data.report.students.append(
                    StudentInfo(id=student_id, result=StudentStatus.SUCCESS)
                )
                task_data.report.num_of_success += 1
            except Exception as e:
                reason = f"Не получилось отправить письмо из-за внутренней ошибки"
                logger.exception(
                    "[Sending Agent] Ошибка при отправке письма руководителю %s: %s",
                    supervisor_email, e
                )
                task_data.report.students.append(
                    StudentInfo(id=student_id, result=StudentStatus.FAILED, extra=reason)
                )

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
                logger.error(
                    f"[Sending Agent] Error occured during sending reminders. "
                    f"Task ID: {task.id}. Error: {e}",
                    exc_info=True
                )
                if task_data.report:
                    await self._send_report_to_sorting_agent(task_data.report, TaskStatus.FAILED, task.id)
                else:
                    await self._send_report_to_sorting_agent(ReportData(len(task_data.student_ids), 0, []), TaskStatus.FAILED, task.id)
                continue
            
            await self.incoming_tasks_manager.update_task(task.id, TaskStatus.COMPLETED, task_data)
            await self._send_report_to_sorting_agent(task_data.report, TaskStatus.COMPLETED, task.id)