import threading
import time
import random
from datetime import datetime, timedelta
from telebot import types

players = {}
roles = {}
votes = {}
night_actions = {}
game_in_progress = False
INACTIVITY_TIMEOUT = timedelta(minutes=5)
bot_instance = None


def load_game_data():
    pass


def save_game_data():
    pass


def check_player_count(chat_id, bot):
    if len(players) < 5:
        bot.send_message(chat_id, "Для начала игры требуется минимум 5 игроков.")
        return False
    elif len(players) > 8:
        bot.send_message(chat_id, "Максимальное количество игроков - 8.")
        return False
    return True


def start_new_game(chat_id, bot):
    global game_in_progress, roles, votes, night_actions
    game_in_progress = True
    roles = assign_roles(players)
    votes = {}
    night_actions = {}
    for player_id, role in roles.items():
        bot.send_message(player_id, f"Ваша роль: {role}")
    bot.send_message(chat_id, "Игра началась! Ночь начинается.")
    start_night_phase(chat_id, bot)


def assign_roles(players):
    player_ids = list(players.keys())
    random.shuffle(player_ids)
    num_players = len(player_ids)
    roles = {}

    if num_players >= 5:
        roles[player_ids[0]] = 'Мафия'
        roles[player_ids[1]] = 'Комиссар'
        roles[player_ids[2]] = 'Доктор'
        for i in range(3, num_players):
            roles[player_ids[i]] = 'Мирный житель'
    if num_players >= 6:
        roles[player_ids[3]] = 'Мафия'
    if num_players >= 7:
        roles[player_ids[4]] = 'Мирный житель'
    if num_players == 8:
        roles[player_ids[5]] = 'Мирный житель'

    return roles


def start_night_phase(chat_id, bot):
    global night_actions
    night_actions = {'Мафия': None, 'Доктор': None, 'Комиссар': None}
    bot.send_message(chat_id,
                     "Ночь наступила. Мафия, Доктор и Комиссар, проверьте свои личные сообщения для выполнения действий.")

    for player_id, role in roles.items():
        if role == 'Мафия':
            markup = types.InlineKeyboardMarkup()
            for target_id, target_name in players.items():
                if target_id != player_id:
                    markup.add(
                        types.InlineKeyboardButton(text=target_name['name'], callback_data=f'night_kill_{target_id}'))
            bot.send_message(player_id, "Выберите цель для убийства:", reply_markup=markup)
        elif role == 'Доктор':
            markup = types.InlineKeyboardMarkup()
            for target_id, target_name in players.items():
                markup.add(
                    types.InlineKeyboardButton(text=target_name['name'], callback_data=f'night_save_{target_id}'))
            bot.send_message(player_id, "Выберите цель для лечения:", reply_markup=markup)
        elif role == 'Комиссар':
            markup = types.InlineKeyboardMarkup()
            for target_id, target_name in players.items():
                if target_id != player_id:
                    markup.add(
                        types.InlineKeyboardButton(text=target_name['name'], callback_data=f'night_check_{target_id}'))
            bot.send_message(player_id, "Выберите цель для проверки:", reply_markup=markup)


def handle_night_action_callback(call, bot):
    global night_actions
    action, target_id = call.data.split('_')[1], int(call.data.split('_')[2])
    player_id = call.from_user.id
    role = roles[player_id]

    if role == 'Мафия' and action == 'kill':
        night_actions['Мафия'] = target_id
    elif role == 'Доктор' and action == 'save':
        night_actions['Доктор'] = target_id
    elif role == 'Комиссар' and action == 'check':
        night_actions['Комиссар'] = target_id

    bot.send_message(player_id, f"Вы выбрали {players[target_id]['name']}")

    if all(action is not None for action in night_actions.values()):
        end_night_phase(call.message.chat.id, bot)


def end_night_phase(chat_id, bot):
    global night_actions
    kill_target = night_actions['Мафия']
    save_target = night_actions['Доктор']
    check_target = night_actions['Комиссар']
    kill_result = 'Никто не был убит.'

    if kill_target != save_target:
        kill_result = f"{players[kill_target]['name']} был убит."
        del players[kill_target]
        del roles[kill_target]

    check_result = f"{players[check_target]['name']} является {roles[check_target]}."

    for player_id, role in roles.items():
        if role == 'Комиссар':
            bot.send_message(player_id, check_result)
        elif role == 'Мафия':
            bot.send_message(player_id, kill_result)

    bot.send_message(chat_id, kill_result)
    check_win_condition(chat_id, bot)


def start_day_phase(chat_id, bot):
    markup = types.InlineKeyboardMarkup()
    for player_id, player_info in players.items():
        markup.add(types.InlineKeyboardButton(text=player_info['name'], callback_data=f'vote_{player_id}'))
    bot.send_message(chat_id, "День начался. Голосуйте за подозреваемого:", reply_markup=markup)


def handle_vote(call, bot):
    global votes
    voter_id = call.from_user.id
    target_id = int(call.data.split('_')[1])

    votes[voter_id] = target_id
    bot.send_message(voter_id, f"Вы проголосовали за {players[target_id]['name']}")

    if len(votes) == len(players):
        end_day_phase(call.message.chat.id, bot)


def end_day_phase(chat_id, bot):
    global votes
    vote_counts = {}
    for target_id in votes.values():
        if target_id in vote_counts:
            vote_counts[target_id] += 1
        else:
            vote_counts[target_id] = 1

    max_votes = max(vote_counts.values())
    to_eliminate = [target_id for target_id, count in vote_counts.items() if count == max_votes]

    if len(to_eliminate) == 1:
        eliminated_id = to_eliminate[0]
    else:
        eliminated_id = random.choice(to_eliminate)

    bot.send_message(chat_id, f"{players[eliminated_id]['name']} был изгнан. Он был {roles[eliminated_id]}.")
    del players[eliminated_id]
    del roles[eliminated_id]

    check_win_condition(chat_id, bot)


def check_win_condition(chat_id, bot):
    mafia_count = sum(1 for role in roles.values() if role == 'Мафия')
    non_mafia_count = len(players) - mafia_count

    if mafia_count >= non_mafia_count:
        bot.send_message(chat_id, "Мафия победила!")
        end_game()
    elif mafia_count == 0:
        bot.send_message(chat_id, "Мирные жители победили!")
        end_game()
    else:
        start_night_phase(chat_id, bot)


def monitor_inactivity():
    while True:
        now = datetime.now()
        for player_id, player_info in list(players.items()):
            last_active = player_info.get('last_active')
            if last_active and now - last_active > INACTIVITY_TIMEOUT:
                end_game_due_to_inactivity(player_id)
                break
        time.sleep(60)


def end_game_due_to_inactivity(inactive_player_id):
    global game_in_progress
    game_in_progress = False
    for player_id, player_info in players.items():
        bot_instance.send_message(player_id,
                                  f"Игра завершена из-за неактивности игрока {players[inactive_player_id]['name']}.")
    players.clear()
    roles.clear()
    votes.clear()
    night_actions.clear()


def end_game():
    global game_in_progress
    game_in_progress = False
    for player_id in players.keys():
        bot_instance.send_message(player_id, "Игра завершена.")
    players.clear()
    roles.clear()
    votes.clear()
    night_actions.clear()


inactivity_thread = threading.Thread(target=monitor_inactivity, daemon=True)
inactivity_thread.start()
