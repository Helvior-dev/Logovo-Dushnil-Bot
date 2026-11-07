import os
import random
from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import datetime
import asyncio
from dotenv import load_dotenv

load_dotenv()

# ── Хранилище ─────────────────────────────────────────────────────────────────
user_stats = {}
reputation = {}
active_duels = {}
active_lotteries = {}
active_votes = {}

def get_stats(user_id):
    if user_id not in user_stats:
        user_stats[user_id] = {'mutes': 0, 'bans': 0, 'pardons': 0}
    return user_stats[user_id]

def get_rep(user_id):
    return reputation.get(user_id, 0)

# ── Helpers ───────────────────────────────────────────────────────────────────

async def delete_later(context, chat_id, message_ids, delay=900):
    await asyncio.sleep(delay)
    for message_id in message_ids:
        try:
            await context.bot.delete_message(chat_id, message_id)
        except:
            pass

async def reply_and_delete(message, text, context, extra_ids=None):
    sent = await message.reply_text(text)
    ids = [message.message_id, sent.message_id]
    if extra_ids:
        ids += extra_ids
    asyncio.create_task(delete_later(context, message.chat_id, ids))
    return sent

async def send_and_delete(context, chat_id, text):
    sent = await context.bot.send_message(chat_id, text)
    asyncio.create_task(delete_later(context, chat_id, [sent.message_id]))
    return sent

def cancel_apology_timeout(context):
    task = context.user_data.pop('timeout_task', None)
    if task and task is not asyncio.current_task() and not task.done():
        task.cancel()

async def try_mute(context, chat_id, user_id, minutes):
    until_date = datetime.datetime.now() + datetime.timedelta(minutes=minutes)
    await context.bot.restrict_chat_member(
        chat_id=chat_id,
        user_id=user_id,
        permissions=ChatPermissions(can_send_messages=False),
        until_date=until_date
    )
    get_stats(user_id)['mutes'] += 1

# ── /raketka ──────────────────────────────────────────────────────────────────

async def raketka(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.message.from_user
    chat_id = update.message.chat_id

    if (context.user_data.get('awaiting_apology')
            and context.user_data.get('apology_chat_id') == chat_id):
        cancel_apology_timeout(context)
        try:
            await try_mute(context, chat_id, user.id, 60)
            await reply_and_delete(update.message, "Ты проигнорировал требование извиниться и теперь отправляешься в мут на 1 час.", context)
        except Exception:
            await reply_and_delete(update.message, "Дали звук президенту!", context)
        context.user_data['awaiting_apology'] = False
        context.user_data.pop('apology_chat_id', None)
        return

    outcome = random.choices(['none', 'mute', 'ban', 'admin', 'rasstrel'], weights=[45, 45, 5, 1, 15], k=1)[0]

    if outcome == 'mute':
        try:
            await try_mute(context, chat_id, user.id, 15)
            await reply_and_delete(update.message, "В этот раз тебе повезло, и санитары уже проводят тебя в палату на целых 15 минут, подумай над своим поведением, слейв.", context)
        except Exception:
            await reply_and_delete(update.message, "Дали звук президенту!", context)

    elif outcome == 'ban':
        await reply_and_delete(update.message, "Тебе несказанно повезло, ты будешь забанен через 10 секунд. У тебя есть время для последнего слова!", context)
        asyncio.create_task(handle_ban(context, chat_id, user.id))

    elif outcome == 'admin':
        try:
            await context.bot.promote_chat_member(
                chat_id=chat_id, user_id=user.id,
                can_manage_chat=True, can_delete_messages=True
            )
            sent = await update.message.reply_text("Партия тобой не довольна, так как ты получил админские права на 3 минуты.")
            asyncio.create_task(delete_later(context, chat_id, [update.message.message_id]))
            asyncio.create_task(revoke_admin_rights(context, chat_id, user.id, sent))
        except Exception:
            await reply_and_delete(update.message, "Партия хотела наградить тебя, но ты уже слишком крут 👑", context)

    elif outcome == 'rasstrel':
        sent = await update.message.reply_text(
            "Ты пользуешься ботом, но делаешь это без уважения. Напиши в чат: «Я прошу прощения у бота за то, что использую его в своих корыстных целях», и, может быть, я тебя прощу. У тебя есть полторы минуты"
        )
        asyncio.create_task(delete_later(context, chat_id, [update.message.message_id, sent.message_id]))
        cancel_apology_timeout(context)
        context.user_data['awaiting_apology'] = True
        context.user_data['apology_chat_id'] = chat_id
        context.user_data['timeout_task'] = asyncio.create_task(timeout_check(update, context))
        context.user_data['expected_apology'] = "Я прошу прощения у бота за то, что использую его в своих корыстных целях"

    else:
        await reply_and_delete(update.message, "В этот раз тебе не повезло, и ты ничего не выиграл, ну тупо лох.", context)

# ── /duel ─────────────────────────────────────────────────────────────────────

async def duel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    challenger = update.message.from_user

    if not update.message.reply_to_message:
        await reply_and_delete(update.message, "Ответь на сообщение того, кого хочешь вызвать на дуэль, лох.", context)
        return

    target = update.message.reply_to_message.from_user

    if target.id == challenger.id:
        await reply_and_delete(update.message, "Ты вызываешь на дуэль себя? Ну и дурак.", context)
        return

    if chat_id in active_duels:
        await reply_and_delete(update.message, "В чате уже идёт дуэль, подожди пока эти двое разберутся.", context)
        return

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("⚔️ Принять дуэль", callback_data=f"duel_accept_{challenger.id}_{target.id}")
    ]])

    response = await update.message.reply_text(
        f"{challenger.first_name} вызывает {target.first_name} на дуэль.\n"
        f"{target.first_name}, у тебя 60 секунд чтобы принять или слиться как последний трус.",
        reply_markup=keyboard
    )
    asyncio.create_task(delete_later(context, chat_id, [update.message.message_id]))

    active_duels[chat_id] = {
        'challenger': challenger.id,
        'target': target.id,
        'message_id': response.message_id
    }

    asyncio.create_task(duel_timeout(context, chat_id, challenger, target, response))

async def duel_timeout(context, chat_id, challenger, target, response):
    await asyncio.sleep(60)
    duel_data = active_duels.get(chat_id)
    if duel_data and duel_data['message_id'] == response.message_id:
        del active_duels[chat_id]
        try:
            await response.edit_text(f"{target.first_name} слился как последний трус. Дуэль отменена.")
            asyncio.create_task(delete_later(context, chat_id, [response.message_id]))
        except:
            pass

async def duel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    chat_id = query.message.chat_id
    data = query.data.split("_")
    challenger_id = int(data[2])
    target_id = int(data[3])

    duel_data = active_duels.get(chat_id)
    if (not duel_data or duel_data['challenger'] != challenger_id
            or duel_data['target'] != target_id
            or duel_data['message_id'] != query.message.message_id):
        await query.answer("Эта дуэль уже закончилась.", show_alert=True)
        return

    if query.from_user.id != duel_data['target']:
        await query.answer("Это не твоя дуэль, не лезь.", show_alert=True)
        return

    del active_duels[chat_id]
    await query.answer()

    winner_id = random.choice([challenger_id, target_id])
    loser_id = target_id if winner_id == challenger_id else challenger_id

    challenger_member = await context.bot.get_chat_member(chat_id, challenger_id)
    target_member = await context.bot.get_chat_member(chat_id, target_id)
    winner_name = challenger_member.user.first_name if winner_id == challenger_id else target_member.user.first_name
    loser_name = target_member.user.first_name if winner_id == challenger_id else challenger_member.user.first_name

    try:
        await try_mute(context, chat_id, loser_id, 15)
        await query.edit_message_text(
            f"{winner_name} победил в дуэли.\n{loser_name} проиграл и отправляется в мут на 15 минут, позор."
        )
    except Exception:
        await query.edit_message_text(
            f"{winner_name} победил в дуэли.\n{loser_name} проиграл, но он неприкосновенен, повезло тебе."
        )
    asyncio.create_task(delete_later(context, chat_id, [query.message.message_id]))

# ── /lottery ──────────────────────────────────────────────────────────────────

async def lottery(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id

    if chat_id in active_lotteries:
        await reply_and_delete(update.message, "Лотерея уже идёт, пиши + чтобы участвовать, не мешай.", context)
        return

    active_lotteries[chat_id] = {'participants': set()}
    await reply_and_delete(
        update.message,
        "Лотерея началась. Пиши + в чат чтобы поучаствовать.\nЧерез 30 секунд один из вас пожалеет об этом.",
        context
    )
    asyncio.create_task(lottery_end(context, chat_id))

async def lottery_end(context, chat_id):
    await asyncio.sleep(30)
    if chat_id not in active_lotteries:
        return

    participants = list(active_lotteries[chat_id]['participants'])
    del active_lotteries[chat_id]

    if len(participants) < 2:
        await send_and_delete(context, chat_id, "Никто не захотел участвовать. Ну и лохи.")
        return

    loser_id = random.choice(participants)
    outcome = random.choice(['mute', 'mute', 'mute', 'nothing'])

    try:
        loser = await context.bot.get_chat_member(chat_id, loser_id)
        loser_name = loser.user.first_name

        if outcome == 'mute':
            await try_mute(context, chat_id, loser_id, 10)
            await send_and_delete(context, chat_id,
                f"Лотерея окончена. Судьба выбрала {loser_name}.\n"
                f"Поздравляю, ты получил мут на 10 минут. Не надо было соглашаться, лох."
            )
        else:
            await send_and_delete(context, chat_id,
                f"Лотерея окончена. Судьба выбрала {loser_name}, но в этот раз помиловала.\nСчитай что повезло."
            )
    except Exception:
        await send_and_delete(context, chat_id, "Лотерея окончена, но победитель оказался неприкосновенным. Бывает.")

# ── /roulette ─────────────────────────────────────────────────────────────────

async def roulette(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.message.from_user
    chat_id = update.message.chat_id
    chamber = random.randint(1, 6)

    if chamber == 1:
        try:
            await try_mute(context, chat_id, user.id, 20)
            await reply_and_delete(update.message, "🔫 Выстрел.\nПоздравляю, ты единственный идиот который попал. Мут на 20 минут.", context)
        except Exception:
            await reply_and_delete(update.message, "🔫 Выстрел, но пуля отрикошетила. Неприкосновенный, иди нахуй.", context)
    else:
        await reply_and_delete(update.message, f"🔫 Щелчок. Патрон в барабане #{chamber}, не сегодня.\nВезунчик.", context)

# ── /vip ──────────────────────────────────────────────────────────────────────

async def vip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.message.from_user
    outcomes = [
        "Поздравляю, ты теперь VIP. Это ничего не значит и никто тебя уважать больше не станет.",
        "VIP статус выдан. Наслаждайся своим воображаемым превосходством.",
        "Ты VIP на следующие 5 минут. Потом снова никто.",
        "Система выдала тебе VIP. Система сожалеет об этом решении.",
        "VIP активирован. Все остальные участники чата не заметят разницы.",
    ]
    await reply_and_delete(update.message, f"{user.first_name}, {random.choice(outcomes)}", context)

# ── /stats ────────────────────────────────────────────────────────────────────

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.message.from_user
    s = get_stats(user.id)
    rep = get_rep(user.id)
    await reply_and_delete(update.message,
        f"Досье на {user.first_name}:\n"
        f"Мутов получено: {s['mutes']}\n"
        f"Банов получено: {s['bans']}\n"
        f"Помилований: {s['pardons']}\n"
        f"Репутация: {rep}\n\n"
        f"{'Ты конченый.' if s['mutes'] > 5 else 'Пока терпимо.'}",
        context
    )

# ── /compliment ───────────────────────────────────────────────────────────────

async def compliment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.message.from_user
    compliments = [
        f"{user.first_name}, ты сегодня выглядишь как человек который не выспался и об этом знает весь чат.",
        f"{user.first_name}, у тебя очень запоминающаяся личность. Жаль что запоминается не то.",
        f"{user.first_name}, ты уникален. Таких как ты больше нет. Это не комплимент.",
        f"{user.first_name}, ты явно стараешься. Просто результат пока не очевиден.",
        f"{user.first_name}, с тобой всегда есть о чём помолчать.",
        f"{user.first_name}, ты определённо существуешь. Это уже что-то.",
        f"{user.first_name}, в тебе есть что-то особенное. Пока непонятно что именно, но надежда есть.",
    ]
    await reply_and_delete(update.message, random.choice(compliments), context)

# ── /plus и /minus ────────────────────────────────────────────────────────────

async def plus_rep(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message.reply_to_message:
        await reply_and_delete(update.message, "Ответь на сообщение того кому хочешь дать плюс, не угадываю же я.", context)
        return
    giver = update.message.from_user
    target = update.message.reply_to_message.from_user
    if giver.id == target.id:
        await reply_and_delete(update.message, "Себе плюсы ставишь? Ну и жалкое зрелище.", context)
        return
    reputation[target.id] = get_rep(target.id) + 1
    await reply_and_delete(update.message, f"{target.first_name} получает +1 к репутации. Теперь {get_rep(target.id)}. Всё равно никто не уважает.", context)

async def minus_rep(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message.reply_to_message:
        await reply_and_delete(update.message, "Ответь на сообщение того кому хочешь дать минус, телепат в отпуске.", context)
        return
    giver = update.message.from_user
    target = update.message.reply_to_message.from_user
    if giver.id == target.id:
        await reply_and_delete(update.message, "Себе минусы ставишь? Хотя бы честный.", context)
        return
    reputation[target.id] = get_rep(target.id) - 1
    await reply_and_delete(update.message, f"{target.first_name} получает -1 к репутации. Теперь {get_rep(target.id)}. Заслужил.", context)

# ── /pandora ──────────────────────────────────────────────────────────────────

async def pandora(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.message.from_user
    chat_id = update.message.chat_id

    outcome = random.choices(
        ['nothing', 'self_mute', 'mass_mute', 'rep_nuke'],
        weights=[15, 35, 25, 25],
        k=1
    )[0]

    if outcome == 'nothing':
        await reply_and_delete(update.message, "Ящик открыт. Оттуда вышел сквозняк и всё. Повезло, идиот.", context)

    elif outcome == 'self_mute':
        try:
            await try_mute(context, chat_id, user.id, 60)
            await reply_and_delete(update.message,
                f"{user.first_name} открыл ящик Пандоры и получил мут на час. "
                f"Поздравляю с собственноручно выкопанной ямой.", context)
        except Exception:
            await reply_and_delete(update.message, "Ящик хотел тебя покарать, но ты неприкосновенен. Ящик расстроен.", context)

    elif outcome == 'mass_mute':
        await reply_and_delete(update.message,
            f"{user.first_name} открыл ящик Пандоры.\n"
            f"Все в чате идут в мут на 5 минут. Спасибо за это можешь сказать {user.first_name}.", context)
        for uid in list(user_stats.keys()):
            if uid != user.id:
                try:
                    await try_mute(context, chat_id, uid, 5)
                except:
                    pass

    elif outcome == 'rep_nuke':
        await reply_and_delete(update.message,
            f"{user.first_name} открыл ящик Пандоры.\n"
            f"Все теряют по 10 репутации. Включая тебя. Особенно тебя.", context)
        for uid in list(reputation.keys()):
            reputation[uid] = get_rep(uid) - 10

# ── /vote ─────────────────────────────────────────────────────────────────────

async def vote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    initiator = update.message.from_user

    if not update.message.reply_to_message:
        await reply_and_delete(update.message, "Ответь на сообщение того кого хочешь замутить, не угадываю.", context)
        return

    target = update.message.reply_to_message.from_user

    if target.id == initiator.id:
        await reply_and_delete(update.message, "Голосуешь за мут самого себя? Ну давай, помогу.", context)
        try:
            await try_mute(context, chat_id, initiator.id, 5)
        except:
            pass
        return

    if chat_id in active_votes:
        await reply_and_delete(update.message, "Голосование уже идёт, подожди пока чат разберётся с предыдущим.", context)
        return

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("👎 Замутить", callback_data=f"vote_yes_{target.id}"),
        InlineKeyboardButton("👍 Помиловать", callback_data=f"vote_no_{target.id}")
    ]])

    response = await update.message.reply_text(
        f"Голосование за мут {target.first_name}.\n"
        f"Инициатор: {initiator.first_name}\n"
        f"Нужно 3 голоса за мут. Времени 60 секунд.\n"
        f"Голосуй или молчи в тряпочку.",
        reply_markup=keyboard
    )
    asyncio.create_task(delete_later(context, chat_id, [update.message.message_id]))

    active_votes[chat_id] = {
        'target_id': target.id,
        'target_name': target.first_name,
        'voters_yes': {initiator.id},
        'voters_no': set(),
        'all_voters': {initiator.id},
        'message_id': response.message_id
    }

    asyncio.create_task(vote_end(context, chat_id, target, response))

async def vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    chat_id = query.message.chat_id
    voter = query.from_user
    data = query.data.split("_")
    vote_type = data[1]
    target_id = int(data[2])

    if chat_id not in active_votes:
        await query.answer("Голосование уже закончилось.", show_alert=True)
        return

    vote_data = active_votes[chat_id]

    if (vote_data['target_id'] != target_id
            or vote_data['message_id'] != query.message.message_id):
        await query.answer("Это голосование уже закончилось.", show_alert=True)
        return

    if voter.id == vote_data['target_id']:
        await query.answer("За себя не голосуют, это не демократия.", show_alert=True)
        return

    if voter.id in vote_data['all_voters']:
        await query.answer("Ты уже проголосовал, не жульничай.", show_alert=True)
        return

    vote_data['all_voters'].add(voter.id)
    if vote_type == "yes":
        vote_data['voters_yes'].add(voter.id)
    else:
        vote_data['voters_no'].add(voter.id)

    yes_count = len(vote_data['voters_yes'])
    no_count = len(vote_data['voters_no'])

    await query.answer(f"Принято. За мут: {yes_count}, против: {no_count}")

    try:
        await query.edit_message_text(
            f"Голосование за мут {vote_data['target_name']}.\n"
            f"За мут: {yes_count} | Против: {no_count}\n"
            f"Нужно 3 голоса. Осталось время.",
            reply_markup=query.message.reply_markup
        )
    except:
        pass

    if yes_count >= 3:
        if chat_id in active_votes:
            del active_votes[chat_id]
        try:
            await try_mute(context, chat_id, target_id, 15)
            await query.edit_message_text(
                f"Чат проголосовал. {vote_data['target_name']} идёт в мут на 15 минут.\n"
                f"Демократия работает только когда результат нравится большинству."
            )
        except Exception:
            await query.edit_message_text(
                f"Чат проголосовал за мут {vote_data['target_name']}, но он неприкосновенен. Система сломана."
            )
        asyncio.create_task(delete_later(context, chat_id, [query.message.message_id]))

async def vote_end(context, chat_id, target, response):
    await asyncio.sleep(60)
    vote_data = active_votes.get(chat_id)
    if not vote_data or vote_data['message_id'] != response.message_id:
        return

    del active_votes[chat_id]

    yes_count = len(vote_data['voters_yes'])
    no_count = len(vote_data['voters_no'])

    try:
        await response.edit_text(
            f"Время вышло. За мут: {yes_count} | Против: {no_count}\n"
            f"{target.first_name} помилован за недостатком голосов. Повезло."
        )
    except:
        pass
    asyncio.create_task(delete_later(context, chat_id, [response.message_id]))

# ── Старые функции ────────────────────────────────────────────────────────────

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id

    if chat_id in active_lotteries and update.message.text.strip() == "+":
        active_lotteries[chat_id]['participants'].add(update.message.from_user.id)
        try:
            await update.message.delete()
        except:
            pass
        return

    if (context.user_data.get('awaiting_apology')
            and context.user_data.get('apology_chat_id') == chat_id
            and context.user_data.get('expected_apology')):
        user_text = update.message.text
        expected_text = context.user_data['expected_apology']

        if user_text.strip() == expected_text:
            forgive = random.choice([True, False])
            if forgive:
                cancel_apology_timeout(context)
                context.user_data['awaiting_apology'] = False
                context.user_data['expected_apology'] = None
                context.user_data.pop('apology_chat_id', None)
                get_stats(update.message.from_user.id)['pardons'] += 1
                await reply_and_delete(update.message, "Спасибо за извинения, на этот раз я тебя прощаю.", context)
            else:
                cancel_apology_timeout(context)
                context.user_data['awaiting_apology'] = False
                context.user_data.pop('apology_chat_id', None)
                try:
                    await try_mute(context, chat_id, update.message.from_user.id, 30)
                    await reply_and_delete(update.message, "Твое извинение звучит неискренне, так что, старина, сьеби нахуй на 30 минут.", context)
                except Exception:
                    await reply_and_delete(update.message, "Твое извинение неискренне, но ты неприкосновенен 👑", context)
        else:
            await reply_and_delete(update.message, "Это не то, что я просил сказать. Попробуй снова.", context)

async def handle_ban(context, chat_id, user_id):
    await asyncio.sleep(10)
    try:
        await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
        await send_and_delete(context, chat_id, "Время истекло! Ты забанен на 1 минуту.")
        get_stats(user_id)['bans'] += 1
        await asyncio.sleep(60)
        await context.bot.unban_chat_member(chat_id=chat_id, user_id=user_id)
        await send_and_delete(context, chat_id, "Разбанен. Добро пожаловать обратно, лох.")
    except Exception:
        await send_and_delete(context, chat_id, "Хотел забанить, но этот человек неприкосновенен 👑")

async def revoke_admin_rights(context, chat_id, user_id, response):
    await asyncio.sleep(180)
    await context.bot.promote_chat_member(
        chat_id=chat_id, user_id=user_id,
        can_manage_chat=False, can_delete_messages=False
    )
    sent = await send_and_delete(context, chat_id, "Всё, время вышло, сдавай корочку.")
    asyncio.create_task(delete_later(context, chat_id, [response.message_id]))

async def timeout_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    task = asyncio.current_task()
    await asyncio.sleep(90)
    if (context.user_data.get('timeout_task') is task
            and context.user_data.get('awaiting_apology')
            and context.user_data.get('apology_chat_id') == update.message.chat_id):
        context.user_data['awaiting_apology'] = False
        context.user_data.pop('apology_chat_id', None)
        context.user_data.pop('timeout_task', None)
        try:
            await try_mute(context, update.message.chat_id, update.message.from_user.id, 60)
            await send_and_delete(context, update.message.chat_id, "Ты думаешь что самый умный? Даю тебе 1 час на подумать")
        except Exception:
            await send_and_delete(context, update.message.chat_id, "Хотел наказать, но этот человек неприкосновенен 👑")

# ── main ──────────────────────────────────────────────────────────────────────

def main():
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise SystemExit("BOT_TOKEN is not set. Add it to the environment or a local .env file.")

    application = Application.builder().token(bot_token).build()

    application.add_handler(CommandHandler("raketka", raketka))
    application.add_handler(CommandHandler("duel", duel))
    application.add_handler(CommandHandler("lottery", lottery))
    application.add_handler(CommandHandler("roulette", roulette))
    application.add_handler(CommandHandler("vip", vip))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("compliment", compliment))
    application.add_handler(CommandHandler("plus", plus_rep))
    application.add_handler(CommandHandler("minus", minus_rep))
    application.add_handler(CommandHandler("pandora", pandora))
    application.add_handler(CommandHandler("vote", vote))
    application.add_handler(CallbackQueryHandler(duel_callback, pattern="^duel_accept_"))
    application.add_handler(CallbackQueryHandler(vote_callback, pattern="^vote_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    application.run_polling()

if __name__ == "__main__":
    main()
