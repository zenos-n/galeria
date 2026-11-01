"""Justified rows shared by the native widget and its geometry checks."""


def justified_rows(ratios, width, target=154, gap=3):
    if not ratios or width <= 0:
        return []
    rows, row, total = [], [], 0.0
    for index, ratio in enumerate(ratios):
        ratio = max(0.05, float(ratio))
        row.append((index, ratio))
        total += ratio
        if total * target + gap * (len(row) - 1) >= width:
            rows.append((row, (width - gap * (len(row) - 1)) / total))
            row, total = [], 0.0
    if row:
        rows.append((row, min(target, (width - gap * (len(row) - 1)) / total)))
    result, y = [], 0
    for row, height in rows:
        height = max(1, round(height))
        x = 0
        for index, ratio in row:
            item_width = max(1, round(height * ratio))
            item_width = min(item_width, max(1, width - x))
            result.append((index, x, y, item_width, height))
            x += item_width + gap
        y += height + gap
    return result
