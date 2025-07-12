def other_agent(message: str, name: str) -> str:
    return f"[NOT-A-HUMAN | Agent {name}]\n\n{message}"


def system_message(content: str) -> str:
    return f"[NOT-A-HUMAN | SYSTEM]\n\n{content}"


def user_message(content: str) -> str:
    return f"[ACTUAL USER]\n\n{content}"
