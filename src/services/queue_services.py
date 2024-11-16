"""Provides utility functions for the the queue management backend."""

# Models
from src.models.queue_models import QueueItemModel, QueueStates


async def active_queue_count() -> int:
    """Get the amount of overall active queue threads in order to supervise application load."""
    return await QueueItemModel.find(
        QueueItemModel.queue_state == QueueStates.PENDING
    ).count()
