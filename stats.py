"""Weight math: input parsing, averages, rates, calorie advice. No Telegram here."""
import re
from datetime import date, timedelta

KCAL_PER_KG = 7700  # ~energy in 1 kg of body tissue
GOALS = {
    # key: (title, target kg/week, tolerance kg/week)
    "gain": ("Набор", 0.25, 0.10),
    "cut": ("Сушка", -0.60, 0.15),
    "maintain": ("Поддержка", 0.0, 0.20),
}
MIN_W, MAX_W = 25, 350
MAX_STEP = 300  # max calorie change recommended at once, kcal/day
CUT_TOO_FAST = -1.0  # kg/week; faster than this on a cut is a problem
ADVICE_DAYS = 21  # advice is based on the trend over this many days

_LINE = re.compile(
    r"^\s*(?:(?P<date>\d{1,4}[./-]\d{1,2}(?:[./-]\d{2,4})?)\s*[-–—:,;]?\s*)?"
    r"(?P<w>\d{2,3}(?:[.,]\d{1,2})?)\s*(?:кг|kg)?\s*$",
    re.IGNORECASE,
)


def parse_date(s, today):
    parts = [int(p) for p in re.split(r"[./-]", s)]
    if len(parts) == 3 and parts[0] > 31:  # 2026-10-25
        y, m, d = parts
    elif len(parts) == 3:  # 25.10.2026 / 25.10.26
        d, m, y = parts
        y += 2000 if y < 100 else 0
    else:  # 25.10 — this year, or last year if it would be in the future
        d, m = parts
        y = today.year
        if date(y, m, d) > today + timedelta(days=31):  # December entries typed in January
            y -= 1
    return date(y, m, d)


def parse_entries(text, today):
    """Lines like "82.5", "25.10 82,5", "2026-10-25 - 82.5 кг" -> ([(date, kg)], [bad lines])."""
    good, bad = [], []
    for line in text.strip().splitlines():
        if not line.strip():
            continue
        m = _LINE.match(line)
        try:
            if not m:
                raise ValueError
            d = parse_date(m["date"], today) if m["date"] else today
            w = float(m["w"].replace(",", "."))
            if not MIN_W <= w <= MAX_W or d > today:
                raise ValueError
            good.append((d, w))
        except ValueError:
            bad.append(line.strip())
    return good, bad


def avg(entries, start, end):
    """Mean weight for dates in (start, end]."""
    ws = [w for d, w in entries if start < d <= end]
    return sum(ws) / len(ws) if ws else None


def slope_per_week(entries):
    """Least-squares trend, kg/week (None if not enough spread)."""
    if len(entries) < 2:
        return None
    xs = [(d - entries[0][0]).days for d, _ in entries]
    ys = [w for _, w in entries]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx * 7


def rolling(entries, days=7):
    """[(date, mean of the entries within the previous `days` days)] for each entry."""
    return [(d, avg(entries, d - timedelta(days=days), d)) for d, _ in entries]


def summary(entries):
    """Everything the stats screen and the advice need. entries are sorted by date."""
    last = entries[-1][0]
    week = avg(entries, last - timedelta(days=7), last)
    prev = avg(entries, last - timedelta(days=14), last - timedelta(days=7))
    recent = [e for e in entries if e[0] > last - timedelta(days=14)]
    trend = [e for e in entries if e[0] > last - timedelta(days=ADVICE_DAYS)]
    span = (last - entries[0][0]).days
    return {
        "count": len(entries),
        "first": entries[0],
        "last": entries[-1],
        "span": span,
        "week_avg": week,
        "prev_avg": prev,
        # week-over-week change of averages; fall back to the 14-day trend
        "rate_recent": week - prev if prev is not None else slope_per_week(recent),
        "rate_total": slope_per_week(entries),
        # smoother pace for advice: one noisy week shouldn't change the calories
        "rate_trend": slope_per_week(trend),
        "total_change": entries[-1][1] - entries[0][1],
        "min": min(entries, key=lambda e: e[1]),
        "max": max(entries, key=lambda e: e[1]),
    }


def _round(x, step=50):
    return int(round(x / step) * step)


def advice(goal, s, kcal=None):
    """(status emoji, text) — whether to change calories and by how much."""
    title, target, tol = GOALS[goal]
    rate = s["rate_trend"]
    if s["span"] < 10 or s["count"] < 5 or rate is None:
        return "⏳", ("Пока мало данных для совета. Нужно хотя бы 5 взвешиваний за 10+ дней — "
                      "лучше взвешиваться каждый день утром натощак.")

    diff = rate - target
    # how much the daily intake differs from what the target pace needs
    gap = -diff * KCAL_PER_KG / 7
    step = max(-MAX_STEP, min(MAX_STEP, _round(gap)))
    if abs(step) < 100:
        step = 100 if gap > 0 else -100

    pace = f"Темп за {ADVICE_DAYS // 7} нед. (по тренду): {rate:+.2f} кг/нед, цель ({title.lower()}): {target:+.2f} кг/нед."
    new = f"\nНовая цель: ~{kcal + step} ккал/день (сейчас {kcal})." if kcal else ""
    hint = "" if kcal else "\n\nУкажи текущие калории командой /kcal 2500 — буду считать точные цифры."

    if abs(diff) <= tol:
        return "✅", f"{pace}\nВсё идёт по плану — калории не меняй.{hint}"

    if goal == "cut":
        if rate > target:  # losing too slowly / weight stands
            why = "Вес стоит." if abs(rate) < 0.15 else "Вес уходит медленнее цели."
            text = (f"{why} Снизь калорийность на ~{-step} ккал/день "
                    f"(или добавь активность: ~8–10 тыс. шагов в день).")
        elif rate >= CUT_TOO_FAST:
            return "✅", (f"{pace}\nЧуть быстрее цели, но в пределах нормы — калории можно не менять. "
                          f"Если тяжело или падают силовые — добавь ~100–150 ккал/день.{hint}")
        else:
            why = "Слишком быстрое снижение — риск потери мышц и срыва."
            text = f"{why} Подними калорийность на ~{step} ккал/день, держи белок 1.8–2.2 г/кг."
    elif goal == "gain":
        if rate < target:
            why = "Вес стоит." if abs(rate) < 0.1 else ("Вес снижается." if rate < 0 else "Набор медленнее цели.")
            text = f"{why} Повысь калорийность на ~{step} ккал/день (проще всего — углеводы)."
        else:
            text = f"Набор быстрее цели — лишнее пойдёт в жир. Снизь калорийность на ~{-step} ккал/день."
    else:
        direction = "растёт" if rate > 0 else "снижается"
        verb = "Снизь" if step < 0 else "Подними"
        text = f"Вес {direction}. {verb} калорийность на ~{abs(step)} ккал/день, чтобы удержать вес."

    note = ("\nПосле изменения подожди 1–2 недели и оцени снова: "
            "вес колеблется от воды, соли и углеводов.")
    return "⚠️", f"{pace}\n{text}{new}{note}{hint}"
