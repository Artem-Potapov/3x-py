
class ClientEmailAlreadyExistsError(Exception):
    def __init__(self, *args):
        super().__init__(args[0] if len(args) == 0 else args)

class EmailNotExistsError(Exception):
    def __init__(self, *args):
        super().__init__(args[0] if len(args) == 0 else args)

class ClientDoesNotExistError(Exception):
    def __init__(self, *args):
        super().__init__(args[0] if len(args) == 0 else args)
