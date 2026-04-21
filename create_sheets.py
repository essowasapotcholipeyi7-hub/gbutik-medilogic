import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os

# Votre ID Google Sheets
SPREADSHEET_ID = "1TEluEvR3o-cWtVCQkueZFucHkLQzbhgtplmw7ZfVZLU"

# Configuration des onglets pour 10 boutiques
NOMBRE_BOUTIQUES = 10

# Liste des types d'onglets par boutique
TYPES_ONGLETS = ['catalogue', 'vente', 'stock', 'vendeurs', 'historique', 'journal']

# En-têtes pour chaque type d'onglet
HEADERS = {
    'catalogue': ['id', 'code', 'nom', 'prix_achat', 'prix_vente', 'stock', 'description', 'categorie', 'date_ajout'],
    'vente': ['id', 'date', 'client_nom', 'client_tel', 'produits', 'quantites', 'total', 'mode_paiement', 'statut', 'vendeur'],
    'stock': ['id_produit', 'nom_produit', 'quantite_initiale', 'entrees', 'sorties', 'stock_actuel', 'seuil_alerte', 'dernier_mouvement'],
    'vendeurs': ['id', 'nom', 'prenom', 'email', 'telephone', 'mot_de_passe', 'role', 'date_embauche', 'actif'],
    'historique': ['id', 'date', 'type_action', 'produit', 'quantite', 'client', 'total', 'vendeur'],
    'journal': ['id', 'date', 'heure', 'utilisateur', 'action', 'details', 'ip_address']
}

print("🚀 Création de la structure multi-boutiques...")
print(f"📊 Spreadsheet ID: {SPREADSHEET_ID}")
print(f"🏪 Nombre de boutiques: {NOMBRE_BOUTIQUES}")
print("=" * 50)

# Instructions pour l'authentification
print("\n🔑 Configuration requise :")
print("1. Allez sur https://console.cloud.google.com")
print("2. Créez un projet 'GBoutik-MediLogic'")
print("3. Activez Google Sheets API et Drive API")
print("4. Créez un compte de service et téléchargez credentials.json")
print("5. Placez credentials.json dans ce dossier")
print("6. Partagez votre feuille avec l'email du compte de service")

# Code pour créer les onglets (à décommenter quand credentials.json est prêt)
"""
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
client = gspread.authorize(creds)

# Ouvrir la feuille
sheet = client.open_by_key(SPREADSHEET_ID)
print(f"\n✅ Connecté à: {sheet.title}")

# Créer les onglets pour chaque boutique
for boutique_num in range(1, NOMBRE_BOUTIQUES + 1):
    for type_onglet in TYPES_ONGLETS:
        nom_onglet = f"{type_onglet}{boutique_num}"
        
        try:
            # Vérifier si l'onglet existe
            try:
                worksheet = sheet.worksheet(nom_onglet)
                print(f"⚠️ {nom_onglet} existe déjà")
            except:
                # Créer l'onglet
                worksheet = sheet.add_worksheet(title=nom_onglet, rows=1000, cols=20)
                # Ajouter les en-têtes
                headers = HEADERS[type_onglet]
                worksheet.append_row(headers)
                # Formater
                worksheet.format('A1:Z1', {'textFormat': {'bold': True}})
                print(f"✅ {nom_onglet} créé")
        except Exception as e:
            print(f"❌ Erreur pour {nom_onglet}: {e}")

print("\n🎉 STRUCTURE COMPLÈTE CRÉÉE !")
print(f"📁 {NOMBRE_BOUTIQUES} boutiques x {len(TYPES_ONGLETS)} onglets = {NOMBRE_BOUTIQUES * len(TYPES_ONGLETS)} onglets")
"""