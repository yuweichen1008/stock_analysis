import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)


#create a table
supabase.table("users").insert({"name": "John Doe"}).execute()

#read a table
users = supabase.table("users").select("*").execute()
print(users)

#update a table
supabase.table("users").update({"name": "John Doe", "age": 30, "email": "john.doe@example.com"}).execute()

#delete a table
# supabase.table("users").delete().execute()

#sign out
supabase.auth.sign_out()