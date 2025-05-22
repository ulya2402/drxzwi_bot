import logging
import asyncio
from supabase import create_client, Client
from postgrest.exceptions import APIError 
from config import SUPABASE_URL, SUPABASE_KEY 

supabase: Client = None

def init_supabase_client():
    global supabase
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            logging.info("Supabase client initialized successfully.")
        except Exception as e:
            logging.error(f"Failed to initialize Supabase client: {e}", exc_info=True)
            supabase = None
    else:
        logging.error("Supabase URL or Key not found in .env file. Database functionality will be disabled.")
        supabase = None

async def add_trigger_to_db(trigger_text: str, response_type: str, response_content: str, creator_id: int):
    if not supabase:
        logging.error("Supabase client not initialized. Cannot add trigger.")
        return None

    trigger_text_lower = trigger_text.lower()
    logging.info(f"[DB_OP] Attempting to insert trigger: {trigger_text_lower} by creator: {creator_id}")

    db_operation = lambda: supabase.table('learned_triggers').insert({
        'trigger_text': trigger_text_lower,
        'response_type': response_type,
        'response_content': response_content,
        'creator_id': creator_id 
    }).execute()

    try:
        response = await asyncio.to_thread(db_operation)
        logging.info(f"[DB_OP_RESULT] Insert for '{trigger_text_lower}': data_count={len(response.data) if response.data else 0}")

        if response.data and len(response.data) > 0:
            logging.info(f"Trigger '{trigger_text_lower}' added successfully to DB.")
            return response.data[0]
        logging.warning(f"No data returned after insert for '{trigger_text_lower}', though no APIError was raised.")
        return None 
    except APIError as e:
        logging.error(f"[DB_API_ERROR] During add_trigger_to_db for '{trigger_text_lower}': code={e.code}, message={e.message}, details={e.details}, hint={e.hint}")
        if str(e.code) == '23505': 
            logging.warning(f"Trigger '{trigger_text_lower}' already exists in DB (unique violation).")
            return "exists"
        return None
    except Exception as e:
        logging.error(f"[DB_EXCEPTION] During add_trigger_to_db for '{trigger_text_lower}': {e}", exc_info=True)
        return None

async def get_response_from_db(trigger_text: str):
    if not supabase:
        logging.error("Supabase client not initialized. Cannot get response.")
        return None
    trigger_text_lower = trigger_text.lower()
    logging.info(f"[DB_OP] Attempting to fetch response for trigger: {trigger_text_lower}")
    db_operation = lambda: supabase.table('learned_triggers') \
        .select('response_type, response_content') \
        .eq('trigger_text', trigger_text_lower) \
        .limit(1) \
        .execute()
    try:
        response = await asyncio.to_thread(db_operation)
        logging.info(f"[DB_OP_RESULT] Fetch for '{trigger_text_lower}': data_count={len(response.data) if response.data else 0}")
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None
    except APIError as e:
        logging.error(f"[DB_API_ERROR] During get_response_from_db for '{trigger_text_lower}': code={e.code}, message={e.message}, details={e.details}")
        return None
    except Exception as e:
        logging.error(f"[DB_EXCEPTION] During get_response_from_db for '{trigger_text_lower}': {e}", exc_info=True)
        return None

async def check_trigger_exists_in_db(trigger_text: str):
    if not supabase:
        logging.error("Supabase client not initialized. Cannot check trigger.")
        return False
    trigger_text_lower = trigger_text.lower()
    logging.info(f"[DB_OP] Attempting to check existence for trigger: {trigger_text_lower}")
    db_operation = lambda: supabase.table('learned_triggers') \
        .select('id', count='exact') \
        .eq('trigger_text', trigger_text_lower) \
        .limit(1) \
        .execute()
    try:
        response = await asyncio.to_thread(db_operation)
        logging.info(f"[DB_OP_RESULT] Existence check for '{trigger_text_lower}': count={response.count}")
        return response.count is not None and response.count > 0
    except APIError as e:
        logging.error(f"[DB_API_ERROR] During check_trigger_exists_in_db for '{trigger_text_lower}': code={e.code}, message={e.message}, details={e.details}")
        return False
    except Exception as e:
        logging.error(f"[DB_EXCEPTION] During check_trigger_exists_in_db for '{trigger_text_lower}': {e}", exc_info=True)
        return False

async def get_all_triggers_from_db(): 
    if not supabase:
        logging.error("Supabase client not initialized. Cannot get all triggers.")
        return []
    logging.info(f"[DB_OP] Attempting to fetch all triggers from DB.")
    db_operation = lambda: supabase.table('learned_triggers') \
        .select('id, trigger_text, response_type, creator_id') \
        .order('created_at', desc=False) \
        .execute()
    try:
        response = await asyncio.to_thread(db_operation)
        logging.info(f"[DB_OP_RESULT] Fetch all triggers: data_count={len(response.data) if response.data else 0}")
        return response.data if response.data else []
    except APIError as e:
        logging.error(f"[DB_API_ERROR] During get_all_triggers_from_db: code={e.code}, message={e.message}, details={e.details}")
        return []
    except Exception as e:
        logging.error(f"[DB_EXCEPTION] During get_all_triggers_from_db: {e}", exc_info=True)
        return []

async def delete_trigger_from_db(trigger_text: str): 
    if not supabase:
        logging.error("Supabase client not initialized. Cannot delete trigger.")
        return False
    trigger_text_lower = trigger_text.lower()
    logging.info(f"[DB_OP] Attempting to delete trigger: {trigger_text_lower} (any admin can delete)")
    db_operation = lambda: supabase.table('learned_triggers') \
        .delete() \
        .eq('trigger_text', trigger_text_lower) \
        .execute()
    try:
        response = await asyncio.to_thread(db_operation)
        deleted_count = len(response.data) if response.data else 0
        logging.info(f"[DB_OP_RESULT] Delete for '{trigger_text_lower}': {deleted_count} row(s) affected.")
        return bool(deleted_count > 0)
    except APIError as e:
        logging.error(f"[DB_API_ERROR] During delete_trigger_from_db for '{trigger_text_lower}': code={e.code}, message={e.message}, details={e.details}")
        return False
    except Exception as e:
        logging.error(f"[DB_EXCEPTION] During delete_trigger_from_db for '{trigger_text_lower}': {e}", exc_info=True)
        return False

async def add_admin_to_db(user_id_to_add: int, added_by_user_id: int) -> bool:
    if not supabase:
        logging.error("Supabase client not initialized. Cannot add admin.")
        return False
    try:
        logging.info(f"[DB_OP_ADMIN] Attempting to add admin: {user_id_to_add} by {added_by_user_id}")
        operation = lambda: supabase.table('bot_admins').insert({
            'user_id': user_id_to_add,
            'added_by': added_by_user_id
        }).execute()
        response = await asyncio.to_thread(operation)

        
        if response.data and len(response.data) > 0:
            logging.info(f"[DB_OP_ADMIN_RESULT] Admin {user_id_to_add} added to DB.")
            return True
        
        logging.warning(f"[DB_OP_ADMIN_RESULT] No data returned after admin insert for {user_id_to_add}, though no APIError.")
        return False 
    except APIError as e:
        if str(e.code) == '23505': 
            logging.warning(f"[DB_API_ERROR] Admin {user_id_to_add} already exists in DB.")
            return True 
        logging.error(f"[DB_API_ERROR] Adding admin {user_id_to_add}: code={e.code}, message={e.message}, details={e.details}")
        return False
    except Exception as e:
        logging.error(f"[DB_EXCEPTION] Adding admin {user_id_to_add}: {e}", exc_info=True)
        return False

async def remove_admin_from_db(user_id_to_remove: int) -> bool:
    if not supabase:
        logging.error("Supabase client not initialized. Cannot remove admin.")
        return False
    try:
        logging.info(f"[DB_OP_ADMIN] Attempting to remove admin: {user_id_to_remove}")
        operation = lambda: supabase.table('bot_admins').delete().eq('user_id', user_id_to_remove).execute()
        response = await asyncio.to_thread(operation)

        
        if response.data and len(response.data) > 0:
            logging.info(f"[DB_OP_ADMIN_RESULT] Admin {user_id_to_remove} removed from DB.")
            return True
        logging.warning(f"[DB_OP_ADMIN_RESULT] Admin {user_id_to_remove} not found or not deleted, no data returned.")
        return False 
    except APIError as e:
        logging.error(f"[DB_API_ERROR] Removing admin {user_id_to_remove}: code={e.code}, message={e.message}, details={e.details}")
        return False
    except Exception as e:
        logging.error(f"[DB_EXCEPTION] Removing admin {user_id_to_remove}: {e}", exc_info=True)
        return False

async def get_all_admins_from_db() -> list:
    if not supabase:
        logging.error("Supabase client not initialized. Cannot get admins.")
        return []
    try:
        logging.info(f"[DB_OP_ADMIN] Attempting to fetch all admins from DB.")
        operation = lambda: supabase.table('bot_admins').select('user_id, added_by, added_at').execute()
        response = await asyncio.to_thread(operation)

        logging.info(f"[DB_OP_ADMIN_RESULT] Fetched {len(response.data) if response.data else 0} admins.")
        return response.data if response.data else []
    except APIError as e:
        logging.error(f"[DB_API_ERROR] Fetching all admins: code={e.code}, message={e.message}, details={e.details}")
        return []
    except Exception as e:
        logging.error(f"[DB_EXCEPTION] Fetching all admins: {e}", exc_info=True)
        return []

init_supabase_client()
