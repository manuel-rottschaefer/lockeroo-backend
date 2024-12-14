"""Utils for all entity classes."""

# Typing
from typing import List

# Beanie
from beanie import After


class Entity():
    """Defines an entity object."""

    def __init__(self, document=None):
        # Initialize the document attribute
        self.document = document

    def __getattr__(self, name):
        """Delegate attribute and method access to the internal document."""
        return getattr(self.document, name)

    def __setattr__(self, name, value):
        """Delegate attribute setting to the internal document, except for 'document' itself."""
        if name == "document":
            # Directly set the 'document' attribute on the instance
            super().__setattr__(name, value)
        else:
            # Delegate setting other attributes to the document
            setattr(self.document, name, value)

    async def save_model_changes(self, notify: bool = False):
        """Save local changes to the database with the option to broadcast changes."""
        # TODO: Make the skip-actions list dynamic
        if notify:
            await self.document.save_changes()
        else:
            await self.document.save_changes(skip_actions=[After])
