import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time

SPREADSHEET_ID = "1TEluEvR3o-cWtVCQkueZFucHkLQzbhgtplmw7ZfVZLU"

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
client = gspread.authorize(creds)
spreadsheet = client.open_by_key(SPREADSHEET_ID)

types_onglets = ['catalogue', 'ventes', 'stock', 'journal', 'vendeurs']

print("=" * 60)
print("🧹 NETTOYAGE LENT (pour éviter les limites API)")
print("=" * 60)

for boutique_id in range(1, 31):
    for onglet_type in types_onglets:
        nom_onglet = f"boutique{boutique_id}_{onglet_type}"
        try:
            sheet = spreadsheet.worksheet(nom_onglet)
            
            # Lire le nombre de lignes
            all_data = sheet.get_all_values()
            nb_lignes = len(all_data)
            
            if nb_lignes > 1:
                # Supprimer une par une (plus lent mais plus sûr)
                for i in range(nb_lignes, 1, -1):
                    sheet.delete_rows(i)
                    time.sleep(0.2)
                print(f"✅ {nom_onglet}: {nb_lignes - 1} lignes supprimées")
            else:
                print(f"⚠️ {nom_onglet}: déjà vide")
                
            time.sleep(1)  # Pause entre chaque feuille
            
        except Exception as e:
            print(f"❌ {nom_onglet}: {e}")
            time.sleep(5)  # Pause plus longue en cas d'erreur

print("\n" + "=" * 60)
print("🎉 NETTOYAGE TERMINÉ !")
print("=" * 60)