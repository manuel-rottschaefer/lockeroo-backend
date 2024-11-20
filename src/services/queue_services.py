"""Provides utility functions for the the queue management backend."""

# Models
from src.models.task_models import TaskItemModel, TaskStates


async def active_queue_count() -> int:
    """Get the amount of overall active queue threads in order to supervise application load."""
    return await TaskItemModel.find(
        TaskItemModel.task_state == TaskStates.PENDING
    ).count()
