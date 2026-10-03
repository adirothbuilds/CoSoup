class ServiceError(Exception):
    def __init__(self, code, message, status=409):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


class Cancelled(ServiceError):
    def __init__(self):
        super().__init__("cancelled", "Task cancelled at a safe checkpoint")
