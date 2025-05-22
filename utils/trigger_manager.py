import logging
from . import database 

async def add_trigger(trigger_text: str, response_type: str, response_content: str, creator_id: int):
    logging.info(f"TriggerManager: Attempting to add trigger to DB: {trigger_text} by creator_id {creator_id}")
    result = await database.add_trigger_to_db(trigger_text, response_type, response_content, creator_id)
    if result == "exists":
        return "exists"
    return result is not None

async def get_response_for_trigger(text: str):
    return await database.get_response_from_db(text)

async def trigger_exists(trigger_text: str):
    return await database.check_trigger_exists_in_db(trigger_text)

async def get_all_triggers_for_admins(): 
    return await database.get_all_triggers_from_db()

async def delete_trigger(trigger_text: str): 
    logging.info(f"TriggerManager: Attempting to delete trigger from DB: {trigger_text}")
    return await database.delete_trigger_from_db(trigger_text)
