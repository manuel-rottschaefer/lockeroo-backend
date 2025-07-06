"""
Lockeroo.entity
-------------------------
This module provides the Entity class

Key Features:
    - Provides a functionality wrapper for Beanie Documents
"""


class Entity():
    """
    Lockeroo.Entity
    -------
    A class representing a lockeroo application entity.
    An Entity is a wrapper for Beanie ODM Docuemnts that adds behavior to them.

    Key Features:
    - `__init__`: Initializes an entity object and assigns the passed document
    - '__getattr__': Forwards attribute access to the document (depreceated)
    - '__setattr__: Forwards attribute modifiers to the document (depreceated)
    - 'insert': Passes the insert call to the document function
    """

    def __init__(self, document=None):
        # Initialize the document attribute
        self.doc = document

    def __getattr__(self, name):
        """Forward attribute access to the document if required, but not function calls"""
        if name == "doc":
            # Return the document attribute
            return self.doc
        elif "view" not in name and name not in ["exists", "handle_expiration"]:
            # Forward attribute access to the document
            attr = getattr(self.doc, name)
            if callable(attr):
                raise AttributeError(
                    f"'{type(self).__name__}' object has no attribute '{name}'")
            return attr

    def __setattr__(self, name, value):
        """Delegate attribute setting to the internal document, except for 'document' itself."""
        if name == "doc":
            # Directly set the 'document' attribute on the instance
            super().__setattr__(name, value)
        else:
            # Delegate setting other attributes to the document
            setattr(self.doc, name, value)

    @property
    def exists(self):
        """Check if the document exists in the database."""
        return self.doc is not None

    async def insert(self):
        await self.doc.insert()
        return self
