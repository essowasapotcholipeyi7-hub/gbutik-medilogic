import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time

SPREADSHEET_ID = "1TEluEvR3o-cWtVCQkueZFucHkLQzbhgtplmw7ZfVZLU"

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
client = gspread.authorize(creds)
spreadsheet = client.open_by_key(SPREADSHEET_ID)

# Types d'onglets à nettoyer
types_onglets = ['catalogue', 'ventes', 'stock', 'journal', 'vendeurs', 'config']

print("=" * 60)
print("🧹 NETTOYAGE DES FEUILLES")
print("=" * 60)

for boutique_id in range(1, 31):
    for onglet_type in types_onglets:
        nom_onglet = f"boutique{boutique_id}_{onglet_type}"
        try:
            sheet = spreadsheet.worksheet(nom_onglet)
            
            # Compter le nombre de lignes
            nb_lignes = len(sheet.get_all_values())
            
            if nb_lignes > 1:
                # Supprimer les lignes 2 à nb_lignes
                # Note: delete_rows prend la ligne de début et le nombre de lignes à supprimer
                sheet.delete_rows(2, nb_lignes - 1)
                print(f"✅ {nom_onglet}: {nb_lignes - 1} lignes supprimées")
            else:
                print(f"⚠️ {nom_onglet}: déjà vide")
                
            time.sleep(0.3)  # Petite pause pour éviter les limites API
            
        except Exception as e:
            print(f"❌ {nom_onglet}: {e}")

print("\n" + "=" * 60)
print("🎉 NETTOYAGE TERMINÉ !")
print("=" * 60)