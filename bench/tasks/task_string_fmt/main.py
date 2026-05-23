def format_name(first, last, middle=None, title=None):
    parts = []
    if title:
        parts.append(title)
    parts.append(first)
    if middle:
        parts.append(middle[0] + ".")
    parts.append(last)
    return " ".join(parts)

def truncate(text, max_len):
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."
