from typing import Annotated
import json

import pandas as pd
from pydantic import Field

from ai_agent.tools import Tool
from task_managers import FileTaskManager
from config import config


sender_tasks_client = FileTaskManager(config.sending_agent.tasks_root_dir)

_PARAM_TO_COLUMN = {
    "faculty": "Факультет",
    "degree": "Степень",
    "course": "Курс",
    "group": "Группа",
    "major": "Направление подготовки",
    "profile": "Профиль",
}


def _filter_students(students_df: pd.DataFrame, filters: dict[str, object]) -> pd.DataFrame:
    """Фильтрует DataFrame по заданным критериям (точное совпадение).

    Применяются только те фильтры, которые были переданы.
    Пустые (NaN) значения в ячейках не совпадают ни с одним критерием.
    """
    mask = pd.Series(True, index=students_df.index)
    for param_name, value in filters.items():
        column = _PARAM_TO_COLUMN[param_name]
        if column not in students_df.columns:
            return pd.DataFrame()
        mask &= students_df[column] == value
    return students_df.loc[mask]


@Tool.from_function
async def create_sending_task(
    faculty: Annotated[str, Field(description="Название факультета (например, 'ФИТ')")] = None,
    degree: Annotated[str, Field(description="Степень обучения: 'Бакалавриат' или 'Магистратура'")] = None,
    course: Annotated[int, Field(description="Курс обучения (от 1 до 4)", ge=1, le=4)] = None,
    group: Annotated[str, Field(description="Номер группы (например, '23938')")] = None,
    major: Annotated[str, Field(description="Код и название направления подготовки (например, '09.04.01 Информатика и вычислительная техника')")] = None,
    profile: Annotated[str, Field(description="Профиль подготовки (например, 'Программная инженерия и компьютерные науки')")] = None
) -> str:
    """
    Используй этот инструмент, когда пользователь просит сделать рассылку
    научным руководителям студентов с просьбой составить индивидуальные задания.

    Инструмент находит подходящих студентов по указанным атрибутам в Excel-таблице
    и создаёт задачу для агента-рассыльщика через FileTaskManager.
    """
    raw_filters = {
        "faculty": faculty,
        "degree": degree,
        "course": course,
        "group": group,
        "major": major,
        "profile": profile,
    }
    filters = {k: v for k, v in raw_filters.items() if v is not None}

    if not filters:
        return json.dumps(
            {"feedback": "Не удалось создать задачу: не указан ни один критерий для поиска студентов."},
            ensure_ascii=False,
        )

    try:
        students_df = pd.read_excel(config.database.excel_path, 0)
        if "Курс" in students_df.columns:
            students_df["Курс"] = pd.to_numeric(students_df["Курс"], errors="coerce").astype("Int64")
    except FileNotFoundError:
        raise FileNotFoundError(json.dumps(
            {"feedback": f"Не удалось создать задачу: файл БД '{config.database.excel_path}' не найден."}, 
            ensure_ascii=False
        ))
    except Exception as e:
        raise Exception(json.dumps(
            {"feedback": f"Не удалось создать задачу: ошибка чтения БД — {e}"}, 
            ensure_ascii=False
        ))

    matched_df = _filter_students(students_df, filters)

    if matched_df.empty:
        return json.dumps(
            {
                "feedback": "Задача не создана: по заданным критериям не найдено ни одного студента.",
                "students_count": 0,
            },
            ensure_ascii=False,
        )

    student_ids = matched_df["id"].astype(str).to_list()

    try:
        await sender_tasks_client.create_task(task_data={"student_ids": student_ids}, data_type="SendingTask")
    except Exception as e:
        raise RuntimeError(json.dumps(
            {
                "feedback": f"Не удалось создать задачу в TaskManager: {e}",
                "students_count": len(student_ids),
            },
            ensure_ascii=False,
        ))

    return json.dumps(
        {
            "feedback": "Задача на рассылку успешно создана.",
            "students_count": len(student_ids),
        },
        ensure_ascii=False,
    )
