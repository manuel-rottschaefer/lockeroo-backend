"""Utils for all entity classes."""


class Entity():
    """Defines an entity object."""

    def __init__(self, document=None):
        # Initialize the document attribute
        self.doc = document

    def __getattr__(self, name):
        """Forward attribute access to the document if required, but not function calls"""
        if name == "doc":
            # Return the document attribute
            return self.doc
        elif "view" not in name and name != "exists":
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
    def exists(self) -> bool:
        """Check if the task exists."""
        return self.doc is not None
