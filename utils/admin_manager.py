import logging
from . import database 
from config import SUPER_ADMIN_ID

admin_ids_cache = set()

async def load_admins_to_cache():
    """Memuat semua admin dari DB ke cache, termasuk SUPER_ADMIN_ID."""
    global admin_ids_cache
    db_admin_records = await database.get_all_admins_from_db() 
    current_admins = {record['user_id'] for record in db_admin_records}

    if SUPER_ADMIN_ID:
        current_admins.add(SUPER_ADMIN_ID)
        

    admin_ids_cache = current_admins
    logging.info(f"Admin cache loaded: {admin_ids_cache}")
    return True 

async def is_user_admin(user_id: int) -> bool:
    """Memeriksa apakah user_id adalah admin (dari cache atau SUPER_ADMIN_ID)."""
    if not admin_ids_cache and SUPER_ADMIN_ID is not None: 
        logging.info("Admin cache is empty, attempting to load...")
        await load_admins_to_cache()
        

    if user_id == SUPER_ADMIN_ID:
        return True
    return user_id in admin_ids_cache

async def add_admin(user_id_to_add: int, added_by_user_id: int) -> bool:
    """Menambahkan admin baru ke DB dan memperbarui cache."""
    if await database.add_admin_to_db(user_id_to_add, added_by_user_id):
        admin_ids_cache.add(user_id_to_add)
        logging.info(f"Admin {user_id_to_add} added to cache by {added_by_user_id}.")
        return True
    return False

async def remove_admin(user_id_to_remove: int) -> bool:
    """Menghapus admin dari DB dan memperbarui cache."""
    if user_id_to_remove == SUPER_ADMIN_ID:
        logging.warning(f"Attempt to remove SUPER_ADMIN_ID ({SUPER_ADMIN_ID}) was blocked.")
        return False 

    if await database.remove_admin_from_db(user_id_to_remove):
        if user_id_to_remove in admin_ids_cache:
            admin_ids_cache.remove(user_id_to_remove)
        logging.info(f"Admin {user_id_to_remove} removed from cache.")
        return True
    return False

async def get_cached_admins() -> set:
    """Mengembalikan set ID admin dari cache."""
    if not admin_ids_cache and SUPER_ADMIN_ID is not None: 
        await load_admins_to_cache()
    return admin_ids_cache.copy() 
