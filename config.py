import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

super_admin_id_str = os.getenv("SUPER_ADMIN_ID")
SUPER_ADMIN_ID = None
if super_admin_id_str and super_admin_id_str.isdigit():
    SUPER_ADMIN_ID = int(super_admin_id_str)
else:
    pass
