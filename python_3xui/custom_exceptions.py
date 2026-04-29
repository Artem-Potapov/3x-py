
class ClientEmailAlreadyExistsError(Exception):
    """Raised when the panel rejects a new client because its email exists."""

    def __init__(self, *args):
        if len(args) == 1:
            super().__init__(args[0])
        else:
            super().__init__(*args)

class EmailNotExistsError(Exception):
    """Raised when a requested client email cannot be found on the panel."""

    def __init__(self, *args):
        if len(args) == 1:
            super().__init__(args[0])
        else:
            super().__init__(*args)

class ClientDoesNotExistError(Exception):
    """Raised when a requested client UUID is absent from the target inbound."""

    def __init__(self, *args):
        if len(args) == 1:
            super().__init__(args[0])
        else:
            super().__init__(*args)
