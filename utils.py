def split_message(message, max_length=2000):
    if len(message) <= max_length:
        return [message]

    parts = []
    lines = message.split("\n")
    current = ""

    for line in lines:
        if len(current) + len(line) + 1 > max_length:
            if current:
                parts.append(current.rstrip())
            if len(line) > max_length:
                for i in range(0, len(line), max_length):
                    parts.append(line[i:i+max_length])
                current = ""
            else:
                current = line + "\n"
        else:
            current += line + "\n"

    if current:
        parts.append(current.rstrip())

    return [p for p in parts if p]