"""
Lockeroo.task_services
-------------------------
This module provides task management utilities

Key Features:
    - Provides a task manager class
    - Provides task expiration logic
    
Dependencies:
    - beanie
"""
# Basics
from datetime import datetime, timezone
from typing import Optional
from asyncio import Task as AsyncTask, create_task, sleep
import traceback
# Beanie
from beanie import SortDirection
# Entities
from src.entities.task_entity import Task
# Services
from src.services.logging_services import logger_service as logger
# Models
from lockeroo_models.task_models import TaskItemModel, TaskState


class TaskManager:
    """Task expiration manager."""

    def __init__(self):
        self.task: Optional[AsyncTask] = None

    async def expiration_manager_loop(self):
        """Coordinate the expiration of tasks.
        Get the time to the next expiration, then wait until the task expires.
        If the task is still pending, fire up the expiration handler.

        Raises:
            AssertionError: If the task has already expired or has no expiration date
        """
        # Log a list of pending tasks for debugging
        pending_tasks = await TaskItemModel.find(
            TaskItemModel.task_state == TaskState.PENDING
        ).sort(
            (TaskItemModel.expires_at, SortDirection.ASCENDING)
        ).to_list()
        if pending_tasks:
            logger.debug("Pending tasks:")
            for task in pending_tasks:
                logger.debug(
                    f"Hello Task ID: {task.id}, Expires at: {task.expires_at}, State: {task.task_state}")
        else:
            logger.debug("No pending tasks found.")
            return

        next_expiring_task: Task = pending_tasks[0]

        # 1: Get time to next expiration
        # next_expiring_task: TaskItemModel = await TaskItemModel.find(
        #    TaskItemModel.task_state == TaskState.PENDING,
        # ).sort(
        #    (TaskItemModel.expires_at, SortDirection.ASCENDING)
        # ).first_or_none()
        # if next_expiring_task is None:
        #    logger.debug("No pending expirations found.")
        #    return
        # assert (next_expiring_task.expires_at is not None
        #        ), f"No expiration date found for task '#{next_expiring_task.id}'."
        try:
            # Ensure next_expiring_task.expires_at is timezone-aware (UTC)
            expires_at_utc = next_expiring_task.expires_at
            if expires_at_utc.tzinfo is None:
                expires_at_utc = expires_at_utc.replace(tzinfo=timezone.utc)

            time_diff_seconds = (
                expires_at_utc - datetime.now(timezone.utc)).total_seconds()
            logger.debug(time_diff_seconds)
        except TypeError as e:
            logger.error(f"TypeError during time difference calculation: {e}")
            logger.error(
                f"Value of next_expiring_task.expires_at: {next_expiring_task.expires_at}")
            logger.error(
                f"Type of next_expiring_task.expires_at: {type(next_expiring_task.expires_at)}")
            # Re-raise the exception if you want the function to still terminate
            # or handle it appropriately (e.g., by returning or skipping the task)
            raise  # Or handle error, e.g., return

        # Ensure next_expiring_task.expires_at is timezone-aware for sleep_duration calculation as well
        expires_at_utc_for_sleep = next_expiring_task.expires_at
        if expires_at_utc_for_sleep.tzinfo is None:
            expires_at_utc_for_sleep = expires_at_utc_for_sleep.replace(
                tzinfo=timezone.utc)

        sleep_duration = (expires_at_utc_for_sleep -
                          datetime.now(timezone.utc)).total_seconds()
        print(type(sleep_duration))
        # Debug next expiring task id and sleep duration
        logger.debug(
            f"Next expiring task: #{next_expiring_task.id}, "
            f"expires at {next_expiring_task.expires_at}, "
            f"sleep duration: {round(sleep_duration)} seconds."
        )

        # 2: Check if the task will expire in the future
        if sleep_duration > 0:
            logger.debug((
                f"Task '#{next_expiring_task.id}' will expire next "
                f"to {next_expiring_task.timeout_states[0]} "
                f"in {round(sleep_duration)} seconds."))
            # Wait until the task expires
            await sleep(sleep_duration)
            await next_expiring_task.sync()
        else:
            logger.debug("negative sleep")
            logger.debug((
                f"Task '#{next_expiring_task.id}' should have expired "
                f"{abs(sleep_duration)} seconds ago."))
            # session_id=next_expiring_task.assigned_session.id)

        if next_expiring_task.task_state == TaskState.PENDING:
            try:
                await Task(next_expiring_task).handle_expiration(task_manager=self)
            except Exception as error:
                logger.error((
                    f"Task '#{next_expiring_task.id}' expired, but "
                    f"could not be handled: {error}"
                ))
                tb = traceback.format_exc()
                logger.error((
                    f"Task '#{next_expiring_task.id}' expired, but could not be handled: {error}\n"
                    f"Traceback:\n{tb}"
                ))
                return
        else:
            logger.debug((
                f"Task '#{next_expiring_task.id}' has already expired, "
                f"is now in '{next_expiring_task.task_state}'."
            ), session_id=next_expiring_task.assigned_session.id)

    def restart(self):
        """Restart the task expiration manager."""
        if self.task:
            self.task.cancel()
        logger.debug("Restarting task expiration manager.")
        self.task = create_task(self.expiration_manager_loop())


task_manager = TaskManager()
