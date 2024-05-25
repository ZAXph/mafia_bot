import threading
import time
import random
from datetime import datetime
from telebot import types, TeleBot
from config import (API_TOKEN, MIN_USER_IN_GAME,
                    MAX_USER_IN_GAME, LOSE_MAFIA,
                    INACTIVITY_TIMEOUT)
from db.sqlite.repository import DataBase
from db.sqlite.schema import TABLE_NAME_USERS, USERS_TABLE_CREATE
from db.json.dynamic_database import Json

# players = {}
# roles = {}
# votes = {}
# night_actions = {}
# game_in_progress = False

table_chat = Json()
table_users = DataBase(TABLE_NAME_USERS, USERS_TABLE_CREATE)

bot = TeleBot(API_TOKEN)


def check_player_count(chat_id, data):
    if len(data["chat_id"][chat_id]["players"]) < MIN_USER_IN_GAME:
        bot.send_message(int(chat_id), "Для начала игры требуется минимум 5 игроков.")
        return False
    elif len(data["chat_id"][chat_id]["players"]) > MAX_USER_IN_GAME:
        bot.send_message(int(chat_id), "Максимальное количество игроков - 8.")
        return False
    return True


def start_new_game(chat_id):
    data = table_chat.open_json_file_and_write()
    # global game_in_progress, roles, votes, night_actions
    data["chat_id"][chat_id]["game_in_progress"] = True
    assign_roles(chat_id, data)
    for player_id, role in data["chat_id"][chat_id]["players"].items():
        if "Мафия" in role["roles"] and role["roles"]["Мафия"] is not None:
            bot.send_message(int(player_id), f'Ваша роль: {role}\n Ваш тиммейт: {role["roles"]["Мафия"]}')
        else:
            bot.send_message(int(player_id), f'Ваша роль: {role}')
    bot.send_message(int(chat_id), "Игра началась! Ночь начинается.")
    table_chat.save_json_file_and_write(data)
    start_night_phase(chat_id)


def assign_roles(chat_id, data):  # JSON DATABASE
    player_ids = list(data["chat_id"][chat_id]["players"].keys())
    random.shuffle(player_ids)
    num_players = len(player_ids)

    if num_players >= 5:
        data["chat_id"][chat_id]["players"][player_ids[0]]["roles"] = {'Мафия': None}
        data["chat_id"][chat_id]["players"][player_ids[1]]["roles"] = 'Комиссар'
        data["chat_id"][chat_id]["players"][player_ids[2]]["roles"] = 'Доктор'
        for i in range(3, num_players):
            data["chat_id"][chat_id]["players"][player_ids[i]]["roles"] = 'Мирный житель'
    if num_players >= 6:
        data["chat_id"][chat_id]["players"][player_ids[3]]["roles"] = {'Мафия': player_ids[0]}
        data["chat_id"][chat_id]["players"][player_ids[0]]["roles"] = {'Мафия': player_ids[3]}  # Подпись тиммейтов
    if num_players >= 7:
        data["chat_id"][chat_id]["players"][player_ids[4]]["roles"] = 'Мирный житель'
    if num_players == 8:
        data["chat_id"][chat_id]["players"][player_ids[5]]["roles"] = 'Мирный житель'
    table_chat.save_json_file_and_write(data)


def start_night_phase(chat_id):
    # global night_actions
    data = table_chat.open_json_file_and_write()
    data["chat_id"][chat_id]["night_actions"] = {'Мафия': None, 'Доктор': None, 'Комиссар': None}
    bot.send_message(int(chat_id),
                     "Ночь наступила. Мафия, Доктор и Комиссар, проверьте свои личные сообщения для выполнения действий.")

    for player_id, role in data["chat_id"][chat_id]["players"].items():
        if role["roles"] == 'Мафия':
            markup = types.InlineKeyboardMarkup()
            for target_id, target_name in data["chat_id"][chat_id]["players"].items():
                if target_id != player_id:
                    markup.add(
                        types.InlineKeyboardButton(text=target_name['name'],
                                                   callback_data=f'night_kill_{target_id}_{chat_id}'))
            bot.send_message(int(player_id), "Выберите цель для убийства:", reply_markup=markup)
        elif role["roles"] == 'Доктор':
            markup = types.InlineKeyboardMarkup()
            for target_id, target_name in data["chat_id"][chat_id]["players"].items():
                markup.add(
                    types.InlineKeyboardButton(text=target_name['name'],
                                               callback_data=f'night_save_{target_id}_{chat_id}'))
            bot.send_message(int(player_id), "Выберите цель для лечения:", reply_markup=markup)
        elif role["roles"] == 'Комиссар':
            markup = types.InlineKeyboardMarkup()
            for target_id, target_name in data["chat_id"][chat_id]["players"].items():
                if target_id != player_id:
                    markup.add(
                        types.InlineKeyboardButton(text=target_name['name'],
                                                   callback_data=f'night_check_{target_id}_{chat_id}'))
            bot.send_message(int(player_id), "Выберите цель для проверки:", reply_markup=markup)


def handle_night_action_callback(call):
    data = table_chat.open_json_file_and_write()
    # global night_actions
    action, target_id, chat_id = call.data.split('_')[1], int(call.data.split('_')[2]), call.data.split('_')[3]
    player_id = call.from_user.id
    role = data["chat_id"][chat_id]["players"][player_id]["roles"]

    if role == 'Мафия' and action == 'kill':
        data["chat_id"][chat_id]["night_actions"]['Мафия'] = target_id
    elif role == 'Доктор' and action == 'save':
        data["chat_id"][chat_id]["night_actions"]['Доктор'] = target_id
    elif role == 'Комиссар' and action == 'check':
        data["chat_id"][chat_id]["night_actions"]['Комиссар'] = target_id

    bot.send_message(int(player_id), f"Вы выбрали {data['chat_id'][chat_id]['players'][target_id]['name']}")
    table_chat.save_json_file_and_write(data)

    if all(action is not None for action in data["chat_id"][chat_id]["night_actions"].values()):
        end_night_phase(chat_id)


def end_night_phase(chat_id):
    # global night_actions
    data = table_chat.open_json_file_and_write()
    kill_target = data["chat_id"][chat_id]["night_actions"]['Мафия']
    save_target = data["chat_id"][chat_id]["night_actions"]['Доктор']
    check_target = data["chat_id"][chat_id]["night_actions"]['Комиссар']
    kill_result = 'Никто не был убит.'

    if kill_target != save_target:
        kill_result = f'{data["chat_id"][chat_id]["players"][kill_target]["name"]} был убит.'
        del data["chat_id"][chat_id]["players"][kill_target]
        # del roles[kill_target]

    check_result = f'{data["chat_id"][chat_id]["players"][check_target]["name"]} является {data["chat_id"][chat_id]["players"][check_target]["roles"]}.'

    bot.send_message(chat_id, kill_result)
    for player_id, role in data["chat_id"][chat_id]["players"].items():
        if role["roles"] == 'Комиссар':
            bot.send_message(int(player_id), check_result)

    check_win_condition(chat_id)
    table_chat.save_json_file_and_write(data)
    start_day_phase(chat_id)


def start_day_phase(chat_id):
    data = table_chat.open_json_file_and_write()
    for player_id, player_info in data["chat_id"][chat_id]["players"].items():
        markup = types.InlineKeyboardMarkup()
        for target_id, target_info in data["chat_id"][chat_id]["players"].items():
            if target_id != player_id:
                markup.add(
                    types.InlineKeyboardButton(text=target_info['name'], callback_data=f'vote_{target_id}_{chat_id}'))
        bot.send_message(int(chat_id), "День начался. Дается одна минута на переговоры.", reply_markup=markup)
        time.sleep(60)
        markup_day = types.InlineKeyboardMarkup()
        markup_day.add(types.InlineKeyboardButton(text="Чат с ботом", callback_data='@mor_ten_bot'))
        bot.send_message(int(chat_id), "День начался. Голосование в лс", reply_markup=markup_day)
        bot.send_message(int(player_id), "День начался. Голосуйте за подозреваемого:", reply_markup=markup)


def handle_vote(call):
    data = table_chat.open_json_file_and_write()
    # global votes
    voter_id = str(call.from_user.id)
    target_id = int(call.data.split('_')[1])
    chat_id = call.data.split('_')[2]

    data["chat_id"][chat_id]["votes"][voter_id] = target_id
    bot.send_message(int(voter_id), f"Вы проголосовали за {data['chat_id'][chat_id]['players'][target_id]['name']}")
    table_chat.save_json_file_and_write(data)

    if len(data["chat_id"][chat_id]["votes"]) == len(data['chat_id'][chat_id]['players']):
        end_day_phase(chat_id)


def end_day_phase(chat_id):
    data = table_chat.open_json_file_and_write()  # надо чат айди в json переделать чтобы не в лс последнему голосовавшему слал а в общую группу
    # global votes
    vote_counts = {}
    for target_id in data["chat_id"][chat_id]["votes"].values():
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

    bot.send_message(int(chat_id),
                     f'{data["chat_id"][chat_id]["players"][eliminated_id]["name"]} был изгнан. Он был {data["chat_id"][chat_id]["players"][eliminated_id]["roles"]}.')
    del data["chat_id"][chat_id]["players"][eliminated_id]
    table_chat.save_json_file_and_write(data)
    # del roles[eliminated_id]

    check_win_condition(chat_id)
    start_night_phase(chat_id)


def check_win_condition(chat_id):  # здесь тоже самое переделать
    data = table_chat.open_json_file_and_write()
    mafia_count = sum(1 for role in data["chat_id"][chat_id]["players"].values() if role["roles"] == 'Мафия')
    non_mafia_count = len(data["chat_id"][chat_id]["players"]) - mafia_count

    if mafia_count >= non_mafia_count:
        bot.send_message(int(chat_id), "Мафия победила!")
        end_game(chat_id)
    elif mafia_count == LOSE_MAFIA:
        bot.send_message(int(chat_id), "Мирные жители победили!")
        end_game(chat_id)


def monitor_inactivity():
    while True:
        data = table_chat.open_json_file_and_write()
        now = datetime.now()
        for chat_id in data["chat_id"]:
            for player_id, player_info in data["chat_id"][chat_id]["players"].items():
                last_active = player_info.get('last_active')
                if last_active and now - last_active > INACTIVITY_TIMEOUT:
                    end_game_due_to_inactivity(player_id, chat_id)
        time.sleep(60)


def end_game_due_to_inactivity(player_id, chat_id):
    data = table_chat.open_json_file_and_write()
    bot.send_message(int(chat_id),
                     f'Игра завершена из-за неактивности игрока {data["chat_id"][chat_id]["players"][player_id]["name"]}.')
    del data["chat_id"][chat_id]
    table_chat.save_json_file_and_write(data)


def end_game(chat_id):
    data = table_chat.open_json_file_and_write()
    del data["chat_id"][chat_id]
    table_chat.save_json_file_and_write(data)


def update_last_active(player_id):
    data = table_chat.open_json_file_and_write()  # SQL
    for chat_id in data["chat_id"]:
        if player_id in data["chat_id"][chat_id]["players"]:
            data["chat_id"][chat_id]["players"][player_id]['last_active'] = datetime.now()
    table_chat.save_json_file_and_write(data)


inactivity_thread = threading.Thread(target=monitor_inactivity, daemon=True)
inactivity_thread.start()
