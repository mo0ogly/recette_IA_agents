from langfuse import observe


@observe()
def run():
    """A PR bot traced with Langfuse."""
    return "ok"
