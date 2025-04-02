from supabase import create_client, Client

# Reemplaza estos valores con los tuyos de Supabase
url = "https://pgolwcphlsvwkqwpxmdy.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBnb2x3Y3BobHN2d2txd3B4bWR5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDM1NDk3NzUsImV4cCI6MjA1OTEyNTc3NX0.AyDyAakQhWQCJLSEI6jGCbHRkoBeWeNTX02wCzGDO6o"

# Crear cliente de Supabase
supabase: Client = create_client(url, key)

# Verifica la conexión imprimiendo el cliente
print(supabase)
