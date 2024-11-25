"""Utils for all entity classes."""

from typing import Type


class Entity():
    """Defines an entity object."""

    def __getattr__(self, name):
        """Delegate attribute access to the internal document."""
        return getattr(self.document, name)

    def __setattr__(self, name, value):
        """Delegate attribute setting to the internal document, except for 'document' itself."""
        if name == "document":
            # Directly set the 'document' attribute on the instance
            super().__setattr__(name, value)
        else:
            # Delegate setting other attributes to the document
            setattr(self.document, name, value)

    async def fetch_links(self):
        """Fetch all links of the document."""
        await self.document.fetch_all_links()
