def format_bytes(bytes_count):
    if bytes_count is None:
        return "—"
    value = float(bytes_count)
    for unit in ["Б", "КБ", "МБ", "ГБ", "ТБ"]:
        if value < 1024:
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{value:.2f} ПБ"


def mb_to_bytes(mb_value):
    if mb_value is None:
        return None
    return int(mb_value) * 1024 * 1024
