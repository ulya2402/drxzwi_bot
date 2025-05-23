from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import Message, ReplyKeyboardRemove, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
import json
import os
import logging
import math
import html
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Union
from utils import trigger_manager, admin_manager, database
from config import SUPER_ADMIN_ID
from aiogram.enums import ParseMode

router = Router()
TRIGGERS_PER_PAGE = 7


def load_locale(lang_code, file_path='locales'):
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    locale_path = os.path.join(base_dir, file_path, f'{lang_code}.json')
    fallback_locale_path = os.path.join(base_dir, file_path, 'en.json')
    try:
        with open(locale_path, 'r', encoding='utf-8') as f: return json.load(f)
    except FileNotFoundError:
        try:
            with open(fallback_locale_path, 'r', encoding='utf-8') as f: return json.load(f)
        except FileNotFoundError:
            logging.error(f"Fallback locale en.json not found at {fallback_locale_path}"); return {}


class LearnStates(StatesGroup):
    waiting_for_trigger = State()
    waiting_for_response_type = State()
    waiting_for_response_content = State()


async def is_admin(user_id: int) -> bool:
    return await admin_manager.is_user_admin(user_id)

CALLBACK_LEARN_FROM_START = "start_learn_button"


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_lang = message.from_user.language_code if message.from_user else 'en'
    locales = load_locale(user_lang)
    
    start_text = locales.get("start_message", "Hello! Welcome to the bot.") # Memberi default yang lebih jelas jika key tidak ada

    if await is_admin(message.from_user.id):
        builder = InlineKeyboardBuilder()
        builder.button(
            text=locales.get("button_learn_start", "🚀 Teach New Responses"), 
            callback_data=CALLBACK_LEARN_FROM_START
        )
        await message.answer(start_text, reply_markup=builder.as_markup())
    else:
        await message.answer(start_text)

@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext):
    await state.clear()
    user_lang = message.from_user.language_code if message.from_user else 'en'
    locales = load_locale(user_lang)
    base_help_text = locales.get("help_message", "Help text not available.")

    if await is_admin(message.from_user.id): # Sudah benar dengan await
        admin_help_header = locales.get("admin_commands_header", "\n\n👑 Admin Management:")
        add_admin_usage = locales.get("add_admin_usage", "/addadmin <user_id> or reply")
        remove_admin_usage = locales.get("remove_admin_usage", "/removeadmin <user_id> or reply")
        list_admins_usage = "/listadmins"

        admin_help_text = (
            f"{admin_help_header}\n"
            f"- `{add_admin_usage}`\n"
            f"- `{remove_admin_usage}`\n"
            f"- `{list_admins_usage}`"
        )
        base_help_text += admin_help_text

    await message.answer(base_help_text, parse_mode="Markdown")

# --- Cancel Handler (Universal for FSM) ---
@router.message(Command("cancel"))
@router.message(F.text.casefold() == "/cancel", LearnStates.waiting_for_trigger)
@router.message(F.text.casefold() == "/cancel", LearnStates.waiting_for_response_type)
@router.message(F.text.casefold() == "/cancel", LearnStates.waiting_for_response_content)
async def cmd_cancel_fsm(message: Message, state: FSMContext):
    user_lang = message.from_user.language_code if message.from_user else 'en'
    locales = load_locale(user_lang)
    current_state_str = await state.get_state()
    if current_state_str is None:
        logging.info(f"User {message.from_user.id} sent /cancel, but no active state.")
        return
    logging.info(f"Cancelling state {current_state_str} for user {message.from_user.id}")
    await state.clear()
    await message.answer(locales.get("action_cancelled", "Action cancelled."), reply_markup=ReplyKeyboardRemove())
    

# --- Learn Command and FSM Handlers ---
LEARN_TYPE_CALLBACK_PREFIX = "learn_type:"

async def _initiate_learn_process(user_id: int, chat_id: int, state: FSMContext, bot: Bot, locales: dict):
    if not await is_admin(user_id):
        await bot.send_message(chat_id, locales.get("permission_denied_learn"))
        return
    await state.clear()
    await bot.send_message(chat_id, locales.get("learn_command_prompt"), reply_markup=ReplyKeyboardRemove())
    await state.set_state(LearnStates.waiting_for_trigger)

@router.message(Command("learn"))
async def cmd_learn_start(message: Message, state: FSMContext, bot: Bot): # Tambahkan bot
    user_lang = message.from_user.language_code if message.from_user else 'en'
    locales = load_locale(user_lang)
    await _initiate_learn_process(message.from_user.id, message.chat.id, state, bot, locales)

@router.callback_query(F.data == CALLBACK_LEARN_FROM_START)
async def cq_learn_from_start(callback_query: CallbackQuery, state: FSMContext, bot: Bot): # Tambahkan bot
    user_lang = callback_query.from_user.language_code if callback_query.from_user else 'en'
    locales = load_locale(user_lang)

    # Hapus tombol setelah diklik (opsional, tapi UX bagus)
    try:
        await callback_query.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        logging.info(f"Could not edit message from start_learn_button click: {e}")

    await _initiate_learn_process(callback_query.from_user.id, callback_query.message.chat.id, state, bot, locales)
    await callback_query.answer()

@router.message(LearnStates.waiting_for_trigger)
async def process_trigger_phrase(message: Message, state: FSMContext):
    user_lang = message.from_user.language_code if message.from_user else 'en'
    locales = load_locale(user_lang)
    if not await is_admin(message.from_user.id): # <<< PERBAIKAN: Ditambahkan await
        await state.clear(); await message.answer(locales.get("permission_denied_learn")); return
    if not message.text or message.text.startswith('/'):
        await message.answer(locales.get("invalid_input_for_trigger")); return
    trigger_text = message.text.strip()
    if await trigger_manager.trigger_exists(trigger_text): # Sudah benar dengan await
        await message.answer(locales.get("learn_trigger_exists").format(trigger=trigger_text)); return
    await state.update_data(trigger_text=trigger_text)
    builder = InlineKeyboardBuilder()
    builder.row( InlineKeyboardButton(text=locales.get("learn_button_text"), callback_data=f"{LEARN_TYPE_CALLBACK_PREFIX}text"), InlineKeyboardButton(text=locales.get("learn_button_image"), callback_data=f"{LEARN_TYPE_CALLBACK_PREFIX}photo") )
    builder.row( InlineKeyboardButton(text=locales.get("learn_button_gif"), callback_data=f"{LEARN_TYPE_CALLBACK_PREFIX}animation"), InlineKeyboardButton(text=locales.get("learn_button_sticker"), callback_data=f"{LEARN_TYPE_CALLBACK_PREFIX}sticker") )
    await message.answer(locales.get("learn_ask_response_type").format(trigger=trigger_text), reply_markup=builder.as_markup())
    await state.set_state(LearnStates.waiting_for_response_type)

@router.callback_query(F.data.startswith(LEARN_TYPE_CALLBACK_PREFIX), LearnStates.waiting_for_response_type)
async def process_response_type_selection(callback_query: CallbackQuery, state: FSMContext):
    user_lang = callback_query.from_user.language_code if callback_query.from_user else 'en'
    locales = load_locale(user_lang)
    if not await is_admin(callback_query.from_user.id): # Sudah benar dengan await
        await callback_query.answer(locales.get("permission_denied_learn"), show_alert=True); await state.clear(); return
    response_type = callback_query.data[len(LEARN_TYPE_CALLBACK_PREFIX):]
    await state.update_data(response_type=response_type)
    try: await callback_query.message.edit_reply_markup(reply_markup=None)
    except Exception as e: logging.info(f"Could not edit reply markup for learn type selection: {e}")
    prompt_key_map = { "text": "learn_prompt_text_response", "photo": "learn_prompt_image_response", "animation": "learn_prompt_gif_response", "sticker": "learn_prompt_sticker_response" }
    prompt_message_key = prompt_key_map.get(response_type)
    if not prompt_message_key:
        logging.error(f"Invalid response_type '{response_type}' received."); await callback_query.message.answer(locales.get("learn_invalid_type_selection", "Invalid selection.")); await state.clear(); await callback_query.answer(); return
    await callback_query.message.answer(locales.get(prompt_message_key))
    await state.set_state(LearnStates.waiting_for_response_content)
    await callback_query.answer()

async def save_learned_trigger_final(message_or_cq: Union[Message, CallbackQuery], state: FSMContext, actual_response_type: str, response_content: str):
    user_obj = message_or_cq.from_user
    user_lang = user_obj.language_code if user_obj else 'en'
    locales = load_locale(user_lang); fsm_data = await state.get_data()
    trigger_text = fsm_data.get("trigger_text")
    if not await is_admin(user_obj.id): # Sudah benar dengan await
        await state.clear(); 
        if isinstance(message_or_cq, Message): await message_or_cq.answer(locales.get("permission_denied_learn")); return
    if not trigger_text:
        await state.clear(); error_msg = "An error occurred (missing data in state), please start over with /learn."
        if isinstance(message_or_cq, Message): await message_or_cq.answer(error_msg)
        logging.error(f"Missing trigger_text in FSM data for user {user_obj.id}."); return
    creator_id = user_obj.id 
    result = await trigger_manager.add_trigger(trigger_text, actual_response_type, response_content, creator_id)
    response_message_key = ""; format_params = {}
    if result is True:
        if actual_response_type == "text": response_message_key = "learn_response_received_text"; format_params = {"response": response_content, "trigger": trigger_text}
        else: response_message_key = "learn_response_received_media"; format_params = {"media_type": actual_response_type, "trigger": trigger_text}
    elif result == "exists": response_message_key = "learn_trigger_exists"; format_params = {"trigger": trigger_text}
    else: response_message_key = "generic_error_learn"; format_params = {}; logging.error(f"Failed to save trigger '{trigger_text}' by {user_obj.id}. Result: {result}")
    final_message_text = locales.get(response_message_key, "Error processing.").format(**format_params)
    if isinstance(message_or_cq, Message): await message_or_cq.answer(final_message_text)
    elif isinstance(message_or_cq, CallbackQuery): await message_or_cq.message.answer(final_message_text)
    await state.clear()

@router.message(LearnStates.waiting_for_response_content, F.text)
async def process_response_content_text(message: Message, state: FSMContext):
    fsm_data = await state.get_data(); selected_type = fsm_data.get("response_type")
    locales = load_locale(message.from_user.language_code if message.from_user else 'en')
    if selected_type != "text": await message.answer(locales.get("learn_response_type_mismatch").format(expected_type=selected_type)); return
    if message.text and message.text.startswith('/'): await message.answer(locales.get("invalid_response_type")); return
    await save_learned_trigger_final(message, state, "text", message.text)

@router.message(LearnStates.waiting_for_response_content, F.photo)
async def process_response_content_photo(message: Message, state: FSMContext):
    fsm_data = await state.get_data(); selected_type = fsm_data.get("response_type")
    if selected_type != "photo": await message.answer(load_locale(message.from_user.language_code if message.from_user else 'en').get("learn_response_type_mismatch").format(expected_type=selected_type)); return
    await save_learned_trigger_final(message, state, "photo", message.photo[-1].file_id)

@router.message(LearnStates.waiting_for_response_content, F.animation)
async def process_response_content_animation(message: Message, state: FSMContext):
    fsm_data = await state.get_data(); selected_type = fsm_data.get("response_type")
    if selected_type != "animation": await message.answer(load_locale(message.from_user.language_code if message.from_user else 'en').get("learn_response_type_mismatch").format(expected_type=selected_type)); return
    await save_learned_trigger_final(message, state, "animation", message.animation.file_id)

@router.message(LearnStates.waiting_for_response_content, F.sticker)
async def process_response_content_sticker(message: Message, state: FSMContext):
    fsm_data = await state.get_data(); selected_type = fsm_data.get("response_type")
    if selected_type != "sticker": await message.answer(load_locale(message.from_user.language_code if message.from_user else 'en').get("learn_response_type_mismatch").format(expected_type=selected_type)); return
    await save_learned_trigger_final(message, state, "sticker", message.sticker.file_id)

@router.message(LearnStates.waiting_for_response_content)
async def process_response_content_invalid(message: Message, state: FSMContext):
    user_lang = message.from_user.language_code if message.from_user else 'en'
    locales = load_locale(user_lang); fsm_data = await state.get_data()
    selected_type = fsm_data.get("response_type", "an expected type")
    await message.answer(locales.get("learn_response_type_mismatch").format(expected_type=selected_type))


# --- Admin Management Commands ---
async def get_target_user_id(message: Message, command: CommandObject, locales: dict) -> Union[int, None]:
    target_user_id_str = None
    if command.args:
        target_user_id_str = command.args.strip()

    target_user_id = None
    if target_user_id_str and target_user_id_str.isdigit():
        target_user_id = int(target_user_id_str)
    elif message.reply_to_message and message.reply_to_message.from_user:
        target_user_id = message.reply_to_message.from_user.id
    else:
        usage_key = ""
        if message.text and "/addadmin" in message.text.lower(): 
            usage_key = "add_admin_usage"
        elif message.text and "/removeadmin" in message.text.lower(): 
            usage_key = "remove_admin_usage"

        if usage_key:
            await message.reply(locales.get(usage_key, "Invalid usage. Please provide a User ID or reply to a user's message."))
        else: 
            await message.reply("Invalid command usage. Please provide a User ID or reply to a user's message.")
    return target_user_id

@router.message(Command("addadmin"))
async def cmd_add_admin(message: Message, command: CommandObject):
    user_lang = message.from_user.language_code if message.from_user else 'en'
    locales = load_locale(user_lang)

    if not await is_admin(message.from_user.id): # Sudah benar dengan await
        await message.reply(locales.get("permission_denied_admin_command"))
        return

    target_user_id = await get_target_user_id(message, command, locales)
    if not target_user_id:
        return 

    if await is_admin(target_user_id): # Sudah benar dengan await
        await message.reply(locales.get("add_admin_already_admin").format(user_id=target_user_id))
        return

    if await admin_manager.add_admin(target_user_id, message.from_user.id): # Sudah benar dengan await
        await message.reply(locales.get("add_admin_success").format(user_id=target_user_id))
    else:
        await message.reply(locales.get("add_admin_failed").format(user_id=target_user_id))

@router.message(Command("removeadmin"))
async def cmd_remove_admin(message: Message, command: CommandObject):
    user_lang = message.from_user.language_code if message.from_user else 'en'
    locales = load_locale(user_lang)

    if not await is_admin(message.from_user.id): # Sudah benar dengan await
        await message.reply(locales.get("permission_denied_admin_command"))
        return

    target_user_id = await get_target_user_id(message, command, locales)
    if not target_user_id:
        return

    if target_user_id == SUPER_ADMIN_ID: 
        await message.reply(locales.get("remove_admin_cannot_remove_super"))
        return

    is_target_actually_admin = await is_admin(target_user_id) # Sudah benar dengan await
    if not is_target_actually_admin:
        await message.reply(locales.get("remove_admin_not_admin").format(user_id=target_user_id))
        return

    if await admin_manager.remove_admin(target_user_id): # Sudah benar dengan await
        await message.reply(locales.get("remove_admin_success").format(user_id=target_user_id))
    else:
        await message.reply(locales.get("remove_admin_failed").format(user_id=target_user_id))

@router.message(Command("listadmins"))
async def cmd_list_admins(message: Message):
    user_lang = message.from_user.language_code if message.from_user else 'en'
    locales = load_locale(user_lang)

    if not await is_admin(message.from_user.id): # Sudah benar dengan await
        await message.reply(locales.get("permission_denied_admin_command"))
        return

    admin_records = await database.get_all_admins_from_db() 

    reply_text = locales.get("list_admins_title") + "\n"
    found_any_admin = False

    if SUPER_ADMIN_ID: 
        reply_text += f"— ID: {SUPER_ADMIN_ID}{locales.get('list_admins_super_admin_indicator', ' (Super Admin)')}\n"
        found_any_admin = True

    if admin_records:
        for admin_rec in admin_records:
            if admin_rec['user_id'] == SUPER_ADMIN_ID: continue 

            added_by_str = str(admin_rec.get('added_by', 'N/A'))
            added_at_raw = admin_rec.get('added_at')
            added_at_str = "N/A"
            if added_at_raw:
                try:
                    dt_obj = datetime.fromisoformat(added_at_raw.replace("Z", "+00:00"))
                    added_at_str = dt_obj.strftime("%Y-%m-%d %H:%M")
                except ValueError: added_at_str = added_at_raw
            reply_text += locales.get("list_admins_entry").format(user_id=admin_rec['user_id'], added_by=added_by_str, added_at=added_at_str) + "\n"
            found_any_admin = True

    if not found_any_admin: 
        reply_text = locales.get("list_admins_empty")

    await message.reply(reply_text)

# --- Delete Trigger Command and Handlers ---
DELETE_CALLBACK_PREFIX = "del_trigger:"
DELETE_PAGE_CALLBACK_PREFIX = "del_page:"
async def _send_delete_trigger_page(message_or_cq: Union[Message, CallbackQuery], state: FSMContext, page: int = 0):
    user_id = message_or_cq.from_user.id
    user_lang = message_or_cq.from_user.language_code if message_or_cq.from_user else 'en'
    locales = load_locale(user_lang)
    if not await is_admin(user_id): # Sudah benar dengan await
        if isinstance(message_or_cq, CallbackQuery): await message_or_cq.answer(locales.get("permission_denied_delete"), show_alert=True)
        else: await message_or_cq.answer(locales.get("permission_denied_delete")); return
    logging.info(f"Admin {user_id} accessing delete trigger page: {page}")
    all_triggers = await trigger_manager.get_all_triggers_for_admins()
    if not all_triggers:
        logging.info(f"No triggers found for admin {user_id} to delete (page: {page}).")
        text = locales.get("delete_trigger_list_empty")
        if isinstance(message_or_cq, CallbackQuery): await message_or_cq.message.edit_text(text, reply_markup=None)
        else: await message_or_cq.answer(text); return
    total_items = len(all_triggers); total_pages = math.ceil(total_items / TRIGGERS_PER_PAGE)
    current_page_display = page + 1
    start_index = page * TRIGGERS_PER_PAGE; end_index = start_index + TRIGGERS_PER_PAGE
    triggers_on_page = all_triggers[start_index:end_index]
    builder = InlineKeyboardBuilder()
    if not triggers_on_page and page > 0:
        logging.warning(f"Admin {user_id} requested empty page {page}. Resetting to 0.")
        await _send_delete_trigger_page(message_or_cq, state, 0); return
    for trigger_obj in triggers_on_page:
        display_text = trigger_obj['trigger_text'][:25]
        callback_data = f"{DELETE_CALLBACK_PREFIX}{trigger_obj['trigger_text']}"
        builder.button(text=f"❌ {display_text}", callback_data=callback_data)
    nav_buttons = []
    if page > 0: nav_buttons.append(InlineKeyboardButton(text=locales.get("button_prev_page"), callback_data=f"{DELETE_PAGE_CALLBACK_PREFIX}{page-1}"))
    nav_buttons.append(InlineKeyboardButton(text=locales.get("button_page_info").format(current_page=current_page_display, total_pages=total_pages), callback_data="noop_page_display"))
    if end_index < total_items: nav_buttons.append(InlineKeyboardButton(text=locales.get("button_next_page"), callback_data=f"{DELETE_PAGE_CALLBACK_PREFIX}{page+1}"))
    if nav_buttons: builder.row(*nav_buttons)
    builder.adjust(1)
    text_to_send = locales.get("delete_trigger_select").format(current_page=current_page_display, total_pages=total_pages)
    if isinstance(message_or_cq, CallbackQuery):
        try: await message_or_cq.message.edit_text(text_to_send, reply_markup=builder.as_markup())
        except Exception as e: logging.info(f"Failed to edit msg for delete page: {e}"); await message_or_cq.answer()
    else: await message_or_cq.answer(text_to_send, reply_markup=builder.as_markup())

@router.message(Command("deletetrigger"))
async def cmd_delete_trigger_start(message: Message, state: FSMContext):
    await state.clear(); await _send_delete_trigger_page(message, state, page=0)

@router.callback_query(F.data.startswith(DELETE_PAGE_CALLBACK_PREFIX))
async def process_delete_trigger_page_nav(callback_query: CallbackQuery, state: FSMContext):
    page = int(callback_query.data[len(DELETE_PAGE_CALLBACK_PREFIX):])
    await _send_delete_trigger_page(callback_query, state, page); await callback_query.answer()

@router.callback_query(F.data == "noop_page_display")
async def noop_callback(callback_query: CallbackQuery): await callback_query.answer()

@router.callback_query(F.data.startswith(DELETE_CALLBACK_PREFIX))
async def process_delete_trigger_selection(callback_query: CallbackQuery, state: FSMContext):
    user_lang = callback_query.from_user.language_code if callback_query.from_user else 'en'
    locales = load_locale(user_lang)
    if not await is_admin(callback_query.from_user.id): # Sudah benar dengan await
        await callback_query.answer(locales.get("permission_denied_delete"), show_alert=True); return
    trigger_text_to_delete = callback_query.data[len(DELETE_CALLBACK_PREFIX):]
    logging.info(f"Admin {callback_query.from_user.id} selected '{trigger_text_to_delete}' for deletion.")
    await state.update_data(trigger_to_delete=trigger_text_to_delete, current_delete_page=0)
    builder = InlineKeyboardBuilder()
    builder.button(text=locales.get("confirm_yes"), callback_data="confirm_delete_yes")
    builder.button(text=locales.get("confirm_no"), callback_data="confirm_delete_no")
    try:
        await callback_query.message.edit_text(locales.get("delete_trigger_confirm_prompt").format(trigger_text=trigger_text_to_delete), reply_markup=builder.as_markup())
    except Exception as e:
        logging.warning(f"Could not edit msg for delete confirm: {e}", exc_info=True)
        await callback_query.message.answer(locales.get("delete_trigger_confirm_prompt").format(trigger_text=trigger_text_to_delete), reply_markup=builder.as_markup())
    await callback_query.answer()

@router.callback_query(F.data == "confirm_delete_yes")
async def process_confirm_delete_yes(callback_query: CallbackQuery, state: FSMContext):
    user_lang = callback_query.from_user.language_code if callback_query.from_user else 'en'
    locales = load_locale(user_lang)
    if not await is_admin(callback_query.from_user.id): # Sudah benar dengan await
        await callback_query.answer(locales.get("permission_denied_delete"), show_alert=True); await state.clear(); return
    fsm_data = await state.get_data(); trigger_text_to_delete = fsm_data.get("trigger_to_delete")
    logging.info(f"Admin {callback_query.from_user.id} confirmed YES to delete: '{trigger_text_to_delete}'.")
    if not trigger_text_to_delete:
        logging.error(f"trigger_to_delete not in FSM for {callback_query.from_user.id}."); 
        try: await callback_query.message.edit_text("Error: No trigger found to delete. Try /deletetrigger.", reply_markup=None)
        except: await callback_query.message.answer("Error: No trigger found to delete. Try /deletetrigger.")
        await state.clear(); await callback_query.answer(); return
    deleted = await trigger_manager.delete_trigger(trigger_text_to_delete)
    final_text = ""
    if deleted: final_text = locales.get("delete_trigger_successful").format(trigger_text=trigger_text_to_delete); logging.info(f"Deleted '{trigger_text_to_delete}'.")
    else: final_text = locales.get("delete_trigger_not_found_or_failed").format(trigger_text=trigger_text_to_delete); logging.warning(f"Failed to delete '{trigger_text_to_delete}'.")
    try: await callback_query.message.edit_text(final_text, reply_markup=None)
    except Exception as e: logging.warning(f"Could not edit msg post-delete: {e}", exc_info=True); await callback_query.message.answer(final_text)
    await state.clear(); await callback_query.answer()

@router.callback_query(F.data == "confirm_delete_no")
async def process_confirm_delete_no(callback_query: CallbackQuery, state: FSMContext):
    user_lang = callback_query.from_user.language_code if callback_query.from_user else 'en'
    locales = load_locale(user_lang); fsm_data = await state.get_data()
    current_page = fsm_data.get("current_delete_page", 0)
    logging.info(f"Admin {callback_query.from_user.id} confirmed NO to delete. Returning to page {current_page}.")
    await _send_delete_trigger_page(callback_query, state, page=current_page)
    await callback_query.answer()

@router.message(Command("placeholders"))
async def cmd_placeholders(message: Message):
    user_lang = message.from_user.language_code if message.from_user else 'en'
    locales = load_locale(user_lang)

    if not await is_admin(message.from_user.id):
        await message.reply(locales.get("permission_denied_placeholders", "Sorry, only bot admins can view this."))
        return

    header = locales.get("placeholders_command_header", "Available placeholders:")
    placeholders_desc_list = locales.get("placeholders_list", [])

    response_text = header + "\n"
    if placeholders_desc_list:
        for item in placeholders_desc_list:
            parts = item.split(" - ", 1)
            if len(parts) == 2:
                placeholder = parts[0]
                description = parts[1]
                response_text += f"\n`{placeholder}` - {description}"
            else:
                response_text += f"\n{item}" # Fallback if format is unexpected
    else:
        response_text += "\nNo placeholders defined in locale."

    await message.answer(response_text, parse_mode=ParseMode.MARKDOWN)


# --- General Message Handler ---
@router.message(F.text)
async def handle_triggered_messages(message: Message, bot: Bot, state: FSMContext):
    current_state_str = await state.get_state()
    if current_state_str is not None: return
    if not message.text or message.text.startswith('/'): return

    response_data = await trigger_manager.get_response_for_trigger(message.text)
    if response_data:
        response_type = response_data.get("response_type")
        content = response_data.get("response_content")

        if not response_type or not content:
            logging.error(f"Incomplete response_data for '{message.text}': {response_data}")
            return

        try:
            if response_type == "text":
                processed_content = content

                utc_now = datetime.now(ZoneInfo("UTC"))
                wib_now = utc_now.astimezone(ZoneInfo("Asia/Jakarta"))
                
                processed_content = processed_content.replace("{date}", wib_now.strftime("%Y-%m-%d"))
                processed_content = processed_content.replace("{time}", wib_now.strftime("%H:%M:%S"))
                processed_content = processed_content.replace("{datetime}", wib_now.strftime("%Y-%m-%d %H:%M:%S"))

                if message.from_user:
                    user = message.from_user
                    processed_content = processed_content.replace("{firstname}", html.escape(user.first_name))
                    processed_content = processed_content.replace("{lastname}", html.escape(user.last_name or ""))
                    processed_content = processed_content.replace("{fullname}", html.escape(user.full_name))
                    processed_content = processed_content.replace("{username}", html.escape(user.username or ""))
                    processed_content = processed_content.replace("{id}", str(user.id))
                    processed_content = processed_content.replace("{mention}", user.mention_html())

                if message.chat:
                    processed_content = processed_content.replace("{chat_id}", str(message.chat.id))
                    processed_content = processed_content.replace("{chat_title}", html.escape(message.chat.title or ""))

                if bot:
                    bot_user = await bot.get_me()
                    processed_content = processed_content.replace("{bot_firstname}", html.escape(bot_user.first_name))
                    processed_content = processed_content.replace("{bot_username}", html.escape(bot_user.username or ""))

                await message.reply(processed_content)
            elif response_type == "photo":
                await bot.send_photo(message.chat.id, content, reply_to_message_id=message.message_id)
            elif response_type == "animation":
                await bot.send_animation(message.chat.id, content, reply_to_message_id=message.message_id)
            elif response_type == "sticker":
                await bot.send_sticker(message.chat.id, content, reply_to_message_id=message.message_id)
        except Exception as e:
            logging.error(f"Failed to send response for '{message.text}': {e}", exc_info=True)
