def resolve_operation(method: str) -> str:
    method = method.upper()
    if method == "GET":
        return "READ"
    if method == "POST":
        return "CREATE"
    if method in ("PUT", "PATCH"):
        return "UPDATE"
    if method == "DELETE":
        return "DELETE"
    return "READ"
