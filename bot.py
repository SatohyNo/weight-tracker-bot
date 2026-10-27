#!/usr/bin/env python3
"""Telegram weight tracker: log weights, see averages, pace, chart and calorie advice.

Token: BOT_TOKEN environment variable or the file ~/.weight_bot_token.
Time zone for "today": BOT_TZ (default Europe/Moscow).
Data: weights.db next to the script (SQLite), separate for every Telegram user.
"""
import csv, io, logging, os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import (BotCommand, InlineKeyboardButton as Btn, InlineKeyboardMarkup as Inline,
                      ReplyKeyboardMarkup, Update)
from telegram.constants import ParseMode
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes,
                          MessageHandler, filters)

import chart, db, stats

TZ = ZoneInfo(os.environ.get("BOT_TZ", "Europe/Moscow"))
HISTORY_ROWS = 20

B_ADD, B_STATS, B_CHART, B_HISTORY, B_ADVICE, B_GOAL, B_HELP = (
    "➕ Внести вес", "📊 Статистика", "📈 График", "📋 История", "💡 Совет", "🎯 Цель", "❓ Помощь")
MENU = ReplyKeyboardMarkup([[B_ADD, B_STATS], [B_CHART, B_HISTORY], [B_ADVICE, B_GOAL, B_HELP]],
                           resize_keyboard=True)

HELP = f"""<b>Как вносить вес</b>
Просто отправь сообщение:
• <code>82.5</code> — вес за сегодня
• <code>25.10 82,4</code> — за конкретную дату
• списком, каждая запись с новой строки:
<code>20.10 83.1
21.10 82.9
22.10 82.7</code>
Дата может быть <code>25.10</code>, <code>25.10.2026</code> или <code>2026-10-25</code>. Повторная дата перезаписывается.

<b>Цели</b> (идеальный темп)
• Набор: +0.25 кг/нед
• Сушка: −0.6 кг/нед
• Поддержка: 0 кг/нед

<b>Команды</b>
/kcal 2500 — сколько ккал ты сейчас ешь (для точных советов)
/del 25.10 — удалить запись за дату
/export — выгрузить всё в CSV
/clear — удалить все записи

Совет: взвешивайся утром натощак, после туалета — так цифры честнее."""


def today():
    return datetime.now(TZ).date()


def fmt(d):
    return d.strftime("%d.%m.%Y")


def goal_keyboard(current):
    return Inline([[Btn(("• " if k == current else "") + f"{title} ({rate:+.2f})", callback_data=f"goal:{k}")
                    for k, (title, rate, _) in stats.GOALS.items()]])


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    goal, _ = db.user(update.effective_user.id)
    await update.message.reply_text(
        f"Привет, {update.effective_user.first_name}! 👋\n"
        "Я веду дневник веса: считаю средние и темп, рисую график и подсказываю, "
        "когда менять калорийность.\n\nОтправь свой вес, например <code>82.5</code>, "
        "или сразу список с датами — /help.", parse_mode=ParseMode.HTML, reply_markup=MENU)
    await update.message.reply_text("Выбери цель:", reply_markup=goal_keyboard(goal))


async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP, parse_mode=ParseMode.HTML, reply_markup=MENU)


async def goal_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    goal, _ = db.user(update.effective_user.id)
    await update.message.reply_text(f"Текущая цель: <b>{stats.GOALS[goal][0]}</b>. Сменить:",
                                    parse_mode=ParseMode.HTML, reply_markup=goal_keyboard(goal))


async def kcal_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    try:
        kcal = int(ctx.args[0])
        assert 800 <= kcal <= 8000
    except (IndexError, ValueError, AssertionError):
        _, cur = db.user(uid)
        now = f"Сейчас указано: {cur} ккал.\n" if cur else ""
        await update.message.reply_text(f"{now}Напиши так: /kcal 2500 (от 800 до 8000).")
        return
    db.set_kcal(uid, kcal)
    await update.message.reply_text(f"Запомнил: {kcal} ккал/день. Теперь совет будет с точной цифрой.")


def stats_text(uid):
    goal, _ = db.user(uid)
    es = db.entries(uid)
    if not es:
        return None
    s = stats.summary(es)
    title, target, _ = stats.GOALS[goal]
    (d0, w0), (d1, w1) = s["first"], s["last"]
    lines = [f"📊 <b>Статистика</b> · цель: {title} ({target:+.2f} кг/нед)", "",
             f"Последний вес: <b>{w1:.1f} кг</b> ({fmt(d1)})"]
    if s["week_avg"] is not None:
        lines.append(f"Среднее за 7 дней: <b>{s['week_avg']:.2f} кг</b>")
    if s["prev_avg"] is not None:
        lines.append(f"Среднее за пред. неделю: {s['prev_avg']:.2f} кг")
    if s["rate_recent"] is not None:
        lines.append(f"Темп за последнюю неделю: <b>{s['rate_recent']:+.2f} кг/нед</b>")
    lines += ["",
              f"С {fmt(d0)}: {w0:.1f} → {w1:.1f} кг (<b>{s['total_change']:+.1f} кг</b> за {s['span']} дн.)"]
    if s["rate_total"] is not None and s["span"] >= 7:
        lines.append(f"Общий темп: <b>{s['rate_total']:+.2f} кг/нед</b>")
    lines.append(f"Мин: {s['min'][1]:.1f} ({fmt(s['min'][0])}) · Макс: {s['max'][1]:.1f} ({fmt(s['max'][0])})")
    lines.append(f"Записей: {s['count']}")
    return "\n".join(lines)


async def show_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = stats_text(update.effective_user.id)
    await update.message.reply_text(text or "Записей пока нет — отправь свой вес, например 82.5.",
                                    parse_mode=ParseMode.HTML)


async def show_advice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    goal, kcal = db.user(uid)
    es = db.entries(uid)
    if not es:
        await update.message.reply_text("Записей пока нет — отправь свой вес, например 82.5.")
        return
    icon, text = stats.advice(goal, stats.summary(es), kcal)
    await update.message.reply_text(f"{icon} <b>Совет по калориям</b> · {stats.GOALS[goal][0]}\n\n{text}",
                                    parse_mode=ParseMode.HTML)


def chart_keyboard():
    return Inline([[Btn("30 дней", callback_data="chart:30"), Btn("90 дней", callback_data="chart:90"),
                    Btn("Всё время", callback_data="chart:all")]])


async def send_chart(message, uid, period="all"):
    goal, _ = db.user(uid)
    es = db.entries(uid)
    if period != "all" and es:
        es = [e for e in es if e[0] > es[-1][0] - timedelta(days=int(period))]
    if len(es) < 2:
        await message.reply_text("Для графика нужно хотя бы 2 записи.")
        return
    label = "всё время" if period == "all" else f"{period} дней"
    png = chart.render(es, goal, f"Вес · {label} · {fmt(es[0][0])} — {fmt(es[-1][0])}")
    await message.reply_photo(png, caption=stats_text(uid), parse_mode=ParseMode.HTML,
                              reply_markup=chart_keyboard())


async def show_chart(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await send_chart(update.message, update.effective_user.id)


async def show_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    es = db.entries(update.effective_user.id)
    if not es:
        await update.message.reply_text("Записей пока нет.")
        return
    rows = []
    for i in range(max(0, len(es) - HISTORY_ROWS), len(es)):
        d, w = es[i]
        delta = f"{w - es[i - 1][1]:+.1f}" if i else ""
        rows.append(f"{d.strftime('%d.%m.%y')}  {w:6.1f}  {delta}")
    head = f"📋 <b>Последние {len(rows)} из {len(es)}</b>\n"
    kb = Inline([[Btn("🗑 Удалить последнюю", callback_data="del:last"),
                  Btn("📄 CSV", callback_data="export")]])
    await update.message.reply_text(head + f"<pre>{'Дата':<8}  {'Вес':>6}  Δ\n" + "\n".join(rows) + "</pre>",
                                    parse_mode=ParseMode.HTML, reply_markup=kb)


async def del_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        day = stats.parse_date(ctx.args[0], today())
    except (IndexError, ValueError):
        await update.message.reply_text("Напиши так: /del 25.10")
        return
    n = db.delete(update.effective_user.id, day)
    await update.message.reply_text(f"Удалил запись за {fmt(day)}." if n else f"За {fmt(day)} записи нет.")


async def clear_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = Inline([[Btn("Да, удалить всё", callback_data="clear:yes"), Btn("Отмена", callback_data="clear:no")]])
    await update.message.reply_text("Удалить <b>все</b> записи веса? Это нельзя отменить.",
                                    parse_mode=ParseMode.HTML, reply_markup=kb)


async def send_csv(message, uid):
    es = db.entries(uid)
    if not es:
        await message.reply_text("Записей пока нет.")
        return
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "weight_kg"])
    w.writerows((d.isoformat(), kg) for d, kg in es)
    await message.reply_document(buf.getvalue().encode(), filename=f"weight_{today().isoformat()}.csv")


async def export_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await send_csv(update.message, update.effective_user.id)


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid, text = update.effective_user.id, update.message.text
    if text == B_ADD:
        await update.message.reply_text(
            "Отправь вес числом (<code>82.5</code>) или списком с датами:\n<code>25.10 82.7\n26.10 82.4</code>",
            parse_mode=ParseMode.HTML)
        return

    entries, bad = stats.parse_entries(text, today())
    if not entries:
        await update.message.reply_text("Не понял 🤔 Отправь вес, например <code>82.5</code> или "
                                        "<code>25.10 82.5</code>. Подробнее — /help.", parse_mode=ParseMode.HTML)
        return

    before = {d: w for d, w in db.entries(uid)}
    replaced = db.add(uid, entries)
    es = db.entries(uid)
    if len(entries) == 1:
        d, w = entries[0]
        prev = [e for e in es if e[0] < d]
        msg = f"✅ Записал <b>{w:.1f} кг</b> за {fmt(d)}"
        if d in before:
            msg += f" (было {before[d]:.1f})"
        if prev:
            msg += f"\nК прошлому взвешиванию ({prev[-1][0].strftime('%d.%m')}): {w - prev[-1][1]:+.1f} кг"
    else:
        days = sorted(d for d, _ in entries)
        msg = f"✅ Записал {len(entries)} шт. ({fmt(days[0])} — {fmt(days[-1])})"
        if replaced:
            msg += f", из них обновлено: {replaced}"
    s = stats.summary(es)
    if s["week_avg"] is not None and len(es) > 1:
        msg += f"\nСреднее за 7 дней: {s['week_avg']:.2f} кг"
    if bad:
        msg += "\n\n⚠️ Не распознал строки:\n" + "\n".join(f"• {b}" for b in bad[:10])
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    kind, _, arg = q.data.partition(":")
    await q.answer()
    if kind == "goal":
        db.set_goal(uid, arg)
        title, rate, _ = stats.GOALS[arg]
        await q.edit_message_text(f"🎯 Цель: <b>{title}</b>, идеальный темп {rate:+.2f} кг/нед.",
                                  parse_mode=ParseMode.HTML)
    elif kind == "chart":
        await send_chart(q.message, uid, arg)
    elif kind == "export":
        await send_csv(q.message, uid)
    elif kind == "del":
        es = db.entries(uid)
        if es:
            db.delete(uid, es[-1][0])
            await q.message.reply_text(f"Удалил {es[-1][1]:.1f} кг за {fmt(es[-1][0])}.")
    elif kind == "clear":
        if arg == "yes":
            db.clear(uid)
        await q.edit_message_text("Все записи удалены." if arg == "yes" else "Ок, ничего не удалял.")


COMMANDS = [("stats", "Статистика"), ("chart", "График веса"), ("advice", "Совет по калориям"),
            ("history", "История записей"), ("goal", "Цель: набор / сушка / поддержка"),
            ("kcal", "Указать текущие калории: /kcal 2500"), ("export", "Выгрузить в CSV"),
            ("help", "Как вносить вес")]


async def post_init(app):
    await app.bot.set_my_commands([BotCommand(c, d) for c, d in COMMANDS])


def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        token = open(os.path.expanduser("~/.weight_bot_token")).read().strip()
    logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    app = Application.builder().token(token).post_init(post_init).build()
    for name, fn in (("start", start), ("help", help_cmd), ("goal", goal_cmd), ("kcal", kcal_cmd),
                     ("stats", show_stats), ("chart", show_chart), ("history", show_history),
                     ("advice", show_advice), ("del", del_cmd), ("clear", clear_cmd), ("export", export_cmd)):
        app.add_handler(CommandHandler(name, fn))
    for label, fn in ((B_STATS, show_stats), (B_CHART, show_chart), (B_HISTORY, show_history),
                      (B_ADVICE, show_advice), (B_GOAL, goal_cmd), (B_HELP, help_cmd)):
        app.add_handler(MessageHandler(filters.Text([label]), fn))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(CallbackQueryHandler(on_button))
    print("Weight bot is running. Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
