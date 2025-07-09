from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default=None)
user_id_var: ContextVar[str] = ContextVar("user_id", default=None)

def set_request_id(value: str):
    request_id_var.set(value)


def set_user_id(value: str):
    user_id_var.set(value)


def get_request_id() -> str:
    return request_id_var.get()


def get_user_id() -> str:
    return user_id_var.get()

