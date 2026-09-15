import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import hashlib
import os
import json
import traceback
import threading
import random
import webauthn_service

# ========== CONFIGURATION EMAIL ==========
EMAIL_EXPEDITEUR = os.environ.get('EMAIL_EXPEDITEUR', '')
EMAIL_MDP = os.environ.get('EMAIL_PASSWORD', '')
EMAIL_DESTINATAIRE = os.environ.get('EMAIL_DESTINATAIRE', '')

app = Flask(__name__)
app.secret_key = 'gbutik_multi_secret_2024'

SPREADSHEET_ID = "1TEluEvR3o-cWtVCQkueZFucHkLQzbhgtplmw7ZfVZLU"

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

if os.path.exists('credentials.json'):
    creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
else:
    creds_dict = json.loads(os.environ.get('GOOGLE_CREDENTIALS', '{}'))
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
spreadsheet = client.open_by_key(SPREADSHEET_ID)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_sheet(boutique_id, sheet_type):
    sheet_name = f"boutique{boutique_id}_{sheet_type}"
    try:
        return spreadsheet.worksheet(sheet_name)
    except:
        return None

def get_boutique_by_email(email):
    try:
        sheet = spreadsheet.worksheet("BOUTIQUES")
        data = sheet.get_all_values()
        for i in range(1, len(data)):
            if len(data[i]) > 2 and data[i][2] == email:
                return {
                    'id': int(data[i][0]),
                    'nom_boutique': data[i][1],
                    'email': data[i][2],
                    'password': data[i][3],
                    'telephone': data[i][4] if len(data[i]) > 4 else '',
                    'adresse': data[i][5] if len(data[i]) > 5 else '',
                    'actif': data[i][7] if len(data[i]) > 7 else 'oui'
                }
    except:
        pass
    return None


def get_boutique_by_id(boutique_id):
    try:
        sheet = spreadsheet.worksheet("BOUTIQUES")
        data = sheet.get_all_values()
        for i in range(1, len(data)):
            if len(data[i]) > 0 and str(data[i][0]) == str(boutique_id):
                return {
                    'id': int(data[i][0]),
                    'nom_boutique': data[i][1],
                    'email': data[i][2] if len(data[i]) > 2 else '',
                    'actif': data[i][7] if len(data[i]) > 7 else 'oui'
                }
    except:
        pass
    return None


# ========== CHARGES / CRÉANCES / DEMANDES DE VALIDATION ==========
# Une charge (dépense) ou un encaissement de créance saisi par un vendeur
# n'a d'effet sur la caisse qu'une fois validé par le gérant. Chaque
# saisie crée donc une ligne "EN_ATTENTE" dans sa feuille dédiée, plus une
# ligne dans la feuille "demandes" (file d'attente générique) qui
# alimente le badge de notification du gérant — voir /api/traiter_demande,
# seul endroit qui exécute réellement l'effet caisse.

CHARGES_HEADERS = ['id', 'date', 'heure', 'categorie', 'montant', 'motif', 'demandeur', 'statut', 'valide_par', 'date_validation', 'motif_refus']
CREANCES_HEADERS = ['id', 'date', 'heure', 'client_nom', 'client_telephone', 'montant_total', 'montant_paye', 'montant_restant', 'statut', 'vendeur', 'reference_vente']
CREANCES_PAIEMENTS_HEADERS = ['id', 'creance_id', 'date', 'heure', 'montant', 'demandeur', 'statut', 'valide_par', 'date_validation', 'motif_refus']
DEMANDES_HEADERS = ['id', 'date', 'heure', 'type', 'reference_id', 'resume', 'demandeur', 'statut', 'traite_par', 'date_traitement', 'motif_refus']


def get_or_create_sheet(boutique_id, sheet_type, headers):
    sheet_name = f"boutique{boutique_id}_{sheet_type}"
    try:
        return spreadsheet.worksheet(sheet_name)
    except:
        sheet = spreadsheet.add_worksheet(title=sheet_name, rows=2000, cols=max(20, len(headers)))
        sheet.append_row(headers)
        return sheet


def generer_id(prefixe):
    return f"{prefixe}_{int(datetime.now().timestamp() * 1000)}_{random.randint(100, 999)}"


def est_gerant():
    return 'boutique_id' in session and session.get('user_role') != 'vendeur'


def to_float_sur(val, defaut=0):
    try:
        if val in (None, ''):
            return defaut
        return float(val)
    except (TypeError, ValueError):
        return defaut


def _creer_demande(boutique_id, type_demande, reference_id, resume, demandeur):
    sheet = get_or_create_sheet(boutique_id, 'demandes', DEMANDES_HEADERS)
    now = datetime.now()
    sheet.append_row([
        generer_id('DEM'), now.strftime('%d/%m/%Y'), now.strftime('%H:%M:%S'),
        type_demande, reference_id, resume, demandeur, 'EN_ATTENTE', '', '', ''
    ])


def _executer_validation_charge(boutique_id, charge_id, action, traite_par, motif_refus):
    sheet = get_sheet(boutique_id, 'charges')
    if not sheet:
        return False, 'Charge introuvable'
    data = sheet.get_all_values()
    for i in range(1, len(data)):
        row = data[i]
        if len(row) > 0 and row[0] == charge_id:
            if len(row) > 7 and row[7] != 'EN_ATTENTE':
                return False, 'Cette charge a déjà été traitée'
            now = datetime.now()
            nouveau_statut = 'VALIDEE' if action == 'valider' else 'REFUSEE'
            sheet.update_cell(i + 1, 8, nouveau_statut)
            sheet.update_cell(i + 1, 9, traite_par)
            sheet.update_cell(i + 1, 10, now.strftime('%d/%m/%Y %H:%M:%S'))
            if motif_refus:
                sheet.update_cell(i + 1, 11, motif_refus)

            montant = to_float_sur(row[4])
            if action == 'valider':
                journal_sheet = get_sheet(boutique_id, 'journal')
                if journal_sheet:
                    journal_sheet.append_row([
                        now.strftime('%d/%m/%Y'), now.strftime('%H:%M:%S'),
                        'CHARGE_VALIDEE', row[3], 1, 0, 0, traite_par,
                        f"{row[5]} | -{montant:,.0f} FCFA (caisse)".replace(',', ' ')
                    ])
                return True, f"Charge validée : -{montant:,.0f} FCFA sur la caisse".replace(',', ' ')
            return True, 'Charge refusée'
    return False, 'Charge introuvable'


def _executer_validation_paiement_creance(boutique_id, paiement_id, action, traite_par, motif_refus):
    paiements_sheet = get_sheet(boutique_id, 'creances_paiements')
    creances_sheet = get_sheet(boutique_id, 'creances')
    if not paiements_sheet:
        return False, 'Paiement introuvable'
    data = paiements_sheet.get_all_values()
    for i in range(1, len(data)):
        row = data[i]
        if len(row) > 0 and row[0] == paiement_id:
            if len(row) > 6 and row[6] != 'EN_ATTENTE':
                return False, 'Ce paiement a déjà été traité'
            now = datetime.now()
            nouveau_statut = 'VALIDEE' if action == 'valider' else 'REFUSEE'
            paiements_sheet.update_cell(i + 1, 7, nouveau_statut)
            paiements_sheet.update_cell(i + 1, 8, traite_par)
            paiements_sheet.update_cell(i + 1, 9, now.strftime('%d/%m/%Y %H:%M:%S'))
            if motif_refus:
                paiements_sheet.update_cell(i + 1, 10, motif_refus)

            if action != 'valider':
                return True, 'Paiement refusé'

            creance_id = row[1]
            montant_paiement = to_float_sur(row[4])
            if creances_sheet:
                creances_data = creances_sheet.get_all_values()
                for j in range(1, len(creances_data)):
                    crow = creances_data[j]
                    if len(crow) > 0 and crow[0] == creance_id:
                        montant_total = to_float_sur(crow[5]) if len(crow) > 5 else 0
                        montant_paye_actuel = to_float_sur(crow[6]) if len(crow) > 6 else 0
                        nouveau_paye = montant_paye_actuel + montant_paiement
                        nouveau_restant = max(montant_total - nouveau_paye, 0)
                        creances_sheet.update_cell(j + 1, 7, nouveau_paye)
                        creances_sheet.update_cell(j + 1, 8, nouveau_restant)
                        creances_sheet.update_cell(j + 1, 9, 'SOLDEE' if nouveau_restant <= 0.01 else 'PARTIELLE')
                        break
            journal_sheet = get_sheet(boutique_id, 'journal')
            if journal_sheet:
                journal_sheet.append_row([
                    now.strftime('%d/%m/%Y'), now.strftime('%H:%M:%S'),
                    'PAIEMENT_CREANCE_VALIDE', creance_id, 1, 0, 0, traite_par,
                    f"Encaissement créance : +{montant_paiement:,.0f} FCFA".replace(',', ' ')
                ])
            return True, f"Paiement validé : +{montant_paiement:,.0f} FCFA sur la caisse".replace(',', ' ')
    return False, 'Paiement introuvable'


def envoyer_notification_boutique_async(nom_boutique, email_gerant, telephone, adresse, proprietaire):
    """Version asynchrone - à appeler dans un thread"""
    try:
        sujet = f"🆕 DEMANDE VALIDATION - Nouvelle boutique: {nom_boutique}"
        
        message_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #1e3a8a; color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ padding: 20px; }}
                .info {{ background: #f5f5f5; padding: 15px; border-radius: 10px; margin: 10px 0; }}
                .button {{ background: #28a745; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; display: inline-block; }}
                .footer {{ text-align: center; color: #666; font-size: 12px; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>NOUVELLE DEMANDE D'INSCRIPTION</h2>
                </div>
                <div class="content">
                    <div class="info">
                        <p><strong>Date :</strong> {datetime.now().strftime('%d/%m/%Y à %H:%M:%S')}</p>
                        <p><strong>Nom :</strong> {nom_boutique}</p>
                        <p><strong>Propriétaire :</strong> {proprietaire}</p>
                        <p><strong>Email :</strong> {email_gerant}</p>
                        <p><strong>Téléphone :</strong> {telephone if telephone else 'Non renseigné'}</p>
                        <p><strong>Adresse :</strong> {adresse if adresse else 'Non renseignée'}</p>
                    </div>
                    <p style="text-align: center;">
                        <a href="https://gbutik-medilogic.onrender.com/admin_global" class="button">Aller à l'Admin Global</a>
                    </p>
                    <p>Connecte-toi à l'Admin Global pour <strong>activer</strong> ou <strong>refuser</strong> cette boutique.</p>
                </div>
                <div class="footer">
                    <p>GBoutik-MediLogic - Système de gestion multi-boutiques</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        msg = MIMEMultipart()
        msg['From'] = EMAIL_EXPEDITEUR
        msg['To'] = EMAIL_DESTINATAIRE
        msg['Subject'] = sujet
        msg.attach(MIMEText(message_html, 'html'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_EXPEDITEUR, EMAIL_MDP)
        server.send_message(msg)
        server.quit()
        
        print(f"Email de validation envoyé pour {nom_boutique}")
        return True
    except Exception as e:
        print(f"Erreur envoi email: {e}")
        return False

# Garde ta fonction originale comme wrapper synchrone (optionnel)
def envoyer_notification_boutique(nom_boutique, email_gerant, telephone, adresse, proprietaire):
    """Version synchrone - appelle la version async dans un thread"""
    thread = threading.Thread(
        target=envoyer_notification_boutique_async,
        args=(nom_boutique, email_gerant, telephone, adresse, proprietaire)
    )
    thread.start()
    print(f"Envoi email en arrière-plan pour {nom_boutique}")
    return True  # On retourne immédiatement


def creer_boutique(nom, email, password, telephone, adresse, proprietaire_nom, proprietaire_prenom):
    try:
        sheet = spreadsheet.worksheet("BOUTIQUES")
        data = sheet.get_all_values()
        new_id = len(data)
        
        proprietaire_complet = f"{proprietaire_nom} {proprietaire_prenom}".strip()
        row = [
            new_id, nom, email, hash_password(password), 
            telephone, adresse, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 
            'non', proprietaire_complet
        ]
        sheet.append_row(row)
        
        # EMAIL ASYNC - ne bloque pas la réponse !
        threading.Thread(
            target=envoyer_notification_boutique,
            args=(nom, email, telephone, adresse, proprietaire_complet)
        ).start()
        
        print(f"Boutique {nom} créée (ID: {new_id}) - Email en cours d'envoi...")
        
        return {'success': True, 'id': new_id, 'message': 'Demande envoyée. En attente de validation par l\'administrateur.'}
        
    except Exception as e:
        print(f"Erreur: {e}")
        traceback.print_exc()
        return {'success': False, 'error': str(e)}

# ========== ROUTES PAGES HTML ==========
@app.route('/')
def index():
    return redirect(url_for('login_page'))

@app.route('/inscription')
def inscription():
    return render_template('inscription.html')

@app.route('/login_page')
def login_page():
    return render_template('login_page.html')

@app.route('/dashboard_boutique')
def dashboard_boutique():
    if 'boutique_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('dashboard_boutique.html', boutique=session.get('boutique_nom'))

@app.route('/catalogue_boutique')
def catalogue_boutique():
    if 'boutique_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('catalogue_multi.html')

@app.route('/vente_boutique')
def vente_boutique():
    if 'boutique_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('vente_multi.html', user_role=session.get('user_role', 'gerant'))

@app.route('/stock_boutique')
def stock_boutique():
    if 'boutique_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('stock_multi.html')

@app.route('/journal_mouvements')
def journal_mouvements():
    if 'boutique_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('journal_mouvements.html')

@app.route('/historique_ventes')
def historique_ventes():
    if 'boutique_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('historique_ventes.html')

@app.route('/caisse_journaliere')
def caisse_journaliere():
    if 'boutique_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('caisse_journaliere.html', user_role=session.get('user_role', 'gerant'))

@app.route('/gestion_vendeurs')
def gestion_vendeurs():
    if 'boutique_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('gestion_vendeurs.html')

@app.route('/approvisionnement')
def approvisionnement():
    if 'boutique_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('approvisionnement.html')

@app.route('/statistiques')
def statistiques():
    if 'boutique_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('statistiques.html')

@app.route('/corrections')
def corrections():
    if 'boutique_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('corrections.html')

@app.route('/charges')
def charges_page():
    if 'boutique_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('charges.html', user_role=session.get('user_role', 'gerant'))

@app.route('/creances')
def creances_page():
    if 'boutique_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('creances.html', user_role=session.get('user_role', 'gerant'))

@app.route('/demandes')
def demandes_page():
    if 'boutique_id' not in session:
        return redirect(url_for('login_page'))
    if session.get('user_role') == 'vendeur':
        return redirect(url_for('dashboard_vendeur'))
    return render_template('demandes.html')

@app.route('/deconnexion')
def deconnexion():
    session.clear()
    return redirect(url_for('login_page'))

# ========== API ROUTES ==========
@app.route('/api/inscrire_boutique', methods=['POST'])
def api_inscrire():
    data = request.get_json()
    result = creer_boutique(
        data.get('nom_boutique'),
        data.get('email'),
        data.get('password'),
        data.get('telephone', ''),
        data.get('adresse', ''),
        data.get('proprietaire_nom', ''),
        data.get('proprietaire_prenom', '')
    )
    return jsonify(result)

@app.route('/api/connexion_boutique', methods=['POST'])
def api_connexion():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    
    boutique = get_boutique_by_email(email)
    if boutique and boutique['password'] == hash_password(password):
        if boutique['actif'] != 'oui':
            return jsonify({'success': False, 'error': 'Boutique en attente de validation. Contactez l\'administrateur.'})
        session['boutique_id'] = boutique['id']
        session['boutique_nom'] = boutique['nom_boutique']
        session['email'] = boutique['email']
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'Email ou mot de passe incorrect'})

@app.route('/api/get_produits')
def api_get_produits():
    if 'boutique_id' not in session:
        return jsonify([])
    
    boutique_id = session['boutique_id']
    
    # Lire le catalogue pour les infos produit (prix, nom, etc.)
    catalogue_sheet = get_sheet(boutique_id, 'catalogue')
    if not catalogue_sheet:
        return jsonify([])
    
    # Lire le stock pour la quantité actuelle
    stock_sheet = get_sheet(boutique_id, 'stock')
    
    cat_data = catalogue_sheet.get_all_values()
    
    # Créer un dictionnaire des stocks
    stock_dict = {}
    if stock_sheet:
        stock_data = stock_sheet.get_all_values()
        for i in range(1, len(stock_data)):
            row = stock_data[i]
            if len(row) > 2:
                produit_nom = row[1] if len(row) > 1 else ''
                stock_actuel = int(row[2]) if row[2] else 0
                stock_dict[produit_nom] = stock_actuel
    
    produits = []
    for i in range(1, len(cat_data)):
        row = cat_data[i]
        if row and len(row) > 0 and row[0]:
            produit_nom = row[1] if len(row) > 1 else ''
            
            # Prendre le stock depuis stock_dict, sinon 0
            stock_actuel = stock_dict.get(produit_nom, 0)
            
            produits.append({
                'id': row[0],
                'nom': produit_nom,
                'categorie': row[2] if len(row) > 2 else '',
                'prixAchat': float(row[3]) if len(row) > 3 and row[3] else 0,
                'prixVente': float(row[4]) if len(row) > 4 and row[4] else 0,
                'stock': stock_actuel,  # ← Maintenant depuis la feuille STOCK
                'seuil': int(row[6]) if len(row) > 6 and row[6] else 10
            })
    return jsonify(produits)

@app.route('/api/ajouter_produit', methods=['POST'])
def api_ajouter_produit():
    if 'boutique_id' not in session:
        return jsonify({'error': 'Non connecté'})
    
    data = request.get_json()
    boutique_id = session['boutique_id']
    
    # 1. Ajouter au catalogue
    catalogue_sheet = get_sheet(boutique_id, 'catalogue')
    if not catalogue_sheet:
        return jsonify({'error': 'Erreur catalogue'})
    
    new_id = f"PROD_{int(datetime.now().timestamp())}"
    row_catalogue = [
        new_id, 
        data.get('nom'), 
        data.get('categorie'), 
        data.get('prixAchat'), 
        data.get('prixVente'), 
        data.get('stock'), 
        data.get('seuil')
    ]
    catalogue_sheet.append_row(row_catalogue)
    
    # 2. Ajouter au stock
    stock_sheet = get_sheet(boutique_id, 'stock')
    if stock_sheet:
        row_stock = [
            new_id, 
            data.get('nom'), 
            data.get('stock'), 
            data.get('seuil'), 
            ''
        ]
        stock_sheet.append_row(row_stock)
    
    # 3. ENREGISTRER DANS LE JOURNAL
    journal_sheet = get_sheet(boutique_id, 'journal')
    if journal_sheet:
        journal_row = [
            datetime.now().strftime('%d/%m/%Y'),
            datetime.now().strftime('%H:%M:%S'),
            'AJOUT_CATALOGUE',
            data.get('nom'),
            data.get('stock'),
            0,
            data.get('stock'),
            session.get('user_nom', 'Gérant'),
            f"Ajout produit: {data.get('nom')} | Prix: {data.get('prixVente')} FCFA"
        ]
        journal_sheet.append_row(journal_row)
        print(f"Journal: Ajout produit {data.get('nom')}")
    
    return jsonify({'success': True, 'message': 'Produit ajouté au catalogue et au stock'})


@app.route('/api/valider_vente', methods=['POST'])
def api_valider_vente():
    if 'boutique_id' not in session:
        return jsonify({'success': False, 'error': 'Non connecté'})
    
    data = request.get_json()
    boutique_id = session['boutique_id']
    produit_nom = data.get('produit')
    quantite = int(data.get('quantite'))
    prixVente = data.get('prixVente')
    remise = data.get('remise')
    total = data.get('total')
    client_nom = (data.get('clientNom') or '').strip()
    client_telephone = (data.get('clientTelephone') or '').strip()
    montant_paye = to_float_sur(data.get('montantPaye'), total)
    montant_paye = max(0, min(montant_paye, total))
    montant_du = total - montant_paye

    if montant_du > 0.01 and not client_nom:
        return jsonify({'success': False, 'error': 'Nom du client requis pour enregistrer une créance'})

    print(f"Vente unique de {produit_nom} x{quantite}")

    try:
        stock_sheet = get_sheet(boutique_id, 'stock')

        # VÉRIFICATION DU STOCK
        if stock_sheet:
            stock_data = stock_sheet.get_all_values()
            stock_actuel = 0
            for i in range(1, len(stock_data)):
                if len(stock_data[i]) > 1 and stock_data[i][1] == produit_nom:
                    stock_actuel = int(stock_data[i][2]) if stock_data[i][2] else 0
                    break

            if stock_actuel < quantite:
                return jsonify({'success': False, 'error': f'Stock insuffisant ! Stock disponible: {stock_actuel}, Demandé: {quantite}'})

        # Si stock suffisant, on continue
        ventes_sheet = get_sheet(boutique_id, 'ventes')
        journal_sheet = get_sheet(boutique_id, 'journal')

        vente_id = f"VENTE_{int(datetime.now().timestamp())}_{produit_nom.replace(' ', '_')}"

        # Récupérer le stock avant (à nouveau pour avoir la valeur)
        ancien_stock = 0
        if stock_sheet:
            stock_data = stock_sheet.get_all_values()
            for i in range(1, len(stock_data)):
                if len(stock_data[i]) > 1 and stock_data[i][1] == produit_nom:
                    ancien_stock = int(stock_data[i][2]) if stock_data[i][2] else 0
                    break

        # Créance éventuelle (client n'a pas tout payé)
        creance_id = ''
        if montant_du > 0.01:
            creances_sheet = get_or_create_sheet(boutique_id, 'creances', CREANCES_HEADERS)
            creance_id = generer_id('CREANCE')
            now = datetime.now()
            creances_sheet.append_row([
                creance_id, now.strftime('%d/%m/%Y'), now.strftime('%H:%M:%S'),
                client_nom, client_telephone, total, montant_paye, montant_du,
                'PARTIELLE' if montant_paye > 0 else 'OUVERTE',
                session.get('user_nom', 'Gérant'), vente_id
            ])

        # Enregistrer la vente (colonnes J/K/L réservées à l'annulation, voir traiter_correction_vente)
        # table_range='A1' est OBLIGATOIRE ici : avec les colonnes J/K/L vides
        # entre "vendeur" et "montant_encaisse", l'auto-détection de tableau de
        # l'API Sheets peut confondre M/N pour un second tableau et décaler les
        # appends suivants de plusieurs colonnes (bug constaté en production).
        ventes_sheet.append_row([
            vente_id,
            datetime.now().strftime('%d/%m/%Y'),
            datetime.now().strftime('%H:%M:%S'),
            produit_nom,
            quantite,
            prixVente,
            remise,
            total,
            session.get('user_nom', 'Gérant'),
            '', '', '',
            montant_paye,
            creance_id
        ], table_range='A1')
        
        # Mettre à jour le stock
        nouveau_stock = ancien_stock - quantite
        if stock_sheet:
            stock_data = stock_sheet.get_all_values()
            for i in range(1, len(stock_data)):
                if len(stock_data[i]) > 1 and stock_data[i][1] == produit_nom:
                    stock_sheet.update_cell(i+1, 3, nouveau_stock)
                    print(f"Stock {produit_nom}: {ancien_stock} → {nouveau_stock}")
                    break
        
        # Journal
        if journal_sheet:
            journal_sheet.append_row([
                datetime.now().strftime('%d/%m/%Y'),
                datetime.now().strftime('%H:%M:%S'),
                'VENTE',
                produit_nom,
                quantite,
                ancien_stock,
                nouveau_stock,
                session.get('user_nom', 'Gérant'),
                f"Total: {total} FCFA"
            ])
        
        message = f'Vente enregistrée ! Stock: {ancien_stock} → {nouveau_stock}'
        if creance_id:
            message += f' | Créance de {montant_du:,.0f} FCFA enregistrée pour {client_nom}'.replace(',', ' ')
        return jsonify({'success': True, 'message': message})

    except Exception as e:
        print(f"Erreur: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/valider_panier', methods=['POST'])
def api_valider_panier():
    if 'boutique_id' not in session:
        return jsonify({'success': False, 'error': 'Non connecté'})
    
    data = request.get_json()
    boutique_id = session['boutique_id']
    panier = data.get('panier', [])
    remiseGlobale = data.get('remiseGlobale', 0)
    totalFinal = data.get('totalFinal', 0)
    client_nom = (data.get('clientNom') or '').strip()
    client_telephone = (data.get('clientTelephone') or '').strip()
    montant_paye_panier = to_float_sur(data.get('montantPaye'), totalFinal)
    montant_paye_panier = max(0, min(montant_paye_panier, totalFinal))
    montant_du_panier = totalFinal - montant_paye_panier
    ratio_encaisse = (montant_paye_panier / totalFinal) if totalFinal > 0 else 1

    if montant_du_panier > 0.01 and not client_nom:
        return jsonify({'success': False, 'error': 'Nom du client requis pour enregistrer une créance'})

    print(f"Validation panier - {len(panier)} articles")

    try:
        stock_sheet = get_sheet(boutique_id, 'stock')
        
        # ========== VÉRIFICATION DU STOCK POUR TOUS LES ARTICLES ==========
        if stock_sheet:
            stock_data = stock_sheet.get_all_values()
            
            for item in panier:
                produit_nom = item['produit']
                quantite = item['quantite']
                stock_actuel = 0
                
                for i in range(1, len(stock_data)):
                    if len(stock_data[i]) > 1 and stock_data[i][1] == produit_nom:
                        stock_actuel = int(stock_data[i][2]) if stock_data[i][2] else 0
                        break
                
                if stock_actuel < quantite:
                    return jsonify({'success': False, 'error': f'Stock insuffisant pour {produit_nom} ! Stock: {stock_actuel}, Demandé: {quantite}'})
        
        # Si tout le stock est suffisant, on continue
        ventes_sheet = get_sheet(boutique_id, 'ventes')
        journal_sheet = get_sheet(boutique_id, 'journal')
        
        total_brut = sum(item['total'] for item in panier)
        timestamp_base = int(datetime.now().timestamp())

        # Créance éventuelle (client n'a pas tout payé) - une ligne pour tout le panier
        creance_id = ''
        if montant_du_panier > 0.01:
            creances_sheet = get_or_create_sheet(boutique_id, 'creances', CREANCES_HEADERS)
            creance_id = generer_id('CREANCE')
            now = datetime.now()
            creances_sheet.append_row([
                creance_id, now.strftime('%d/%m/%Y'), now.strftime('%H:%M:%S'),
                client_nom, client_telephone, totalFinal, montant_paye_panier, montant_du_panier,
                'PARTIELLE' if montant_paye_panier > 0 else 'OUVERTE',
                session.get('user_nom', 'Gérant'), f"VENTE_{timestamp_base}"
            ])

        for idx, item in enumerate(panier):
            vente_id = f"VENTE_{timestamp_base}_{idx}_{item['produit'].replace(' ', '_')}"
            
            proportion = item['total'] / total_brut if total_brut > 0 else 0
            remise_article = round(remiseGlobale * proportion)
            total_article = item['total'] - remise_article
            if total_article < 0:
                total_article = 0
            
            print(f"Article {idx+1}: {item['produit']} - ID: {vente_id}")
            
            # Récupérer le stock avant
            ancien_stock = 0
            if stock_sheet:
                stock_data = stock_sheet.get_all_values()
                for i in range(1, len(stock_data)):
                    if len(stock_data[i]) > 1 and stock_data[i][1] == item['produit']:
                        ancien_stock = int(stock_data[i][2]) if stock_data[i][2] else 0
                        break
            
            # Enregistrer la vente (colonnes J/K/L réservées à l'annulation, voir traiter_correction_vente)
            # table_range='A1' : voir le commentaire équivalent dans api_valider_vente.
            montant_encaisse_article = round(total_article * ratio_encaisse)
            ventes_sheet.append_row([
                vente_id,
                datetime.now().strftime('%d/%m/%Y'),
                datetime.now().strftime('%H:%M:%S'),
                item['produit'],
                item['quantite'],
                item['prix'],
                remise_article,
                total_article,
                session.get('user_nom', 'Gérant'),
                '', '', '',
                montant_encaisse_article,
                creance_id
            ], table_range='A1')
            
            # Mettre à jour le stock
            nouveau_stock = ancien_stock - item['quantite']
            if stock_sheet:
                stock_data = stock_sheet.get_all_values()
                for i in range(1, len(stock_data)):
                    if len(stock_data[i]) > 1 and stock_data[i][1] == item['produit']:
                        stock_sheet.update_cell(i+1, 3, nouveau_stock)
                        print(f"Stock {item['produit']}: {ancien_stock} → {nouveau_stock}")
                        break
            
            # Journal
            if journal_sheet:
                journal_sheet.append_row([
                    datetime.now().strftime('%d/%m/%Y'),
                    datetime.now().strftime('%H:%M:%S'),
                    'VENTE_PANIER',
                    item['produit'],
                    item['quantite'],
                    ancien_stock,
                    nouveau_stock,
                    session.get('user_nom', 'Gérant'),
                    f"Prix: {item['prix']} FCFA | Total: {total_article} FCFA"
                ])
        
        print(f"Panier validé - Total: {totalFinal} FCFA")
        message = f'Panier validé ! Total: {totalFinal} FCFA'
        if creance_id:
            message += f' | Créance de {montant_du_panier:,.0f} FCFA enregistrée pour {client_nom}'.replace(',', ' ')
        return jsonify({'success': True, 'message': message})
        
    except Exception as e:
        print(f"Erreur: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get_journal')
def api_get_journal():
    if 'boutique_id' not in session:
        return jsonify([])
    
    sheet = get_sheet(session['boutique_id'], 'journal')
    if not sheet:
        return jsonify([])
    
    data = sheet.get_all_values()
    journal = []
    for i in range(1, len(data)):
        row = data[i]
        if row and len(row) > 0 and row[0]:
            journal.append({
                'date': row[0] if len(row) > 0 else '',
                'heure': row[1] if len(row) > 1 else '',
                'type': row[2] if len(row) > 2 else '',
                'produit': row[3] if len(row) > 3 else '',
                'quantite': row[4] if len(row) > 4 else '',
                'stockAvant': row[5] if len(row) > 5 else 0,
                'stockApres': row[6] if len(row) > 6 else 0,
                'utilisateur': row[7] if len(row) > 7 else ''
            })
    return jsonify(journal[::-1])

@app.route('/api/get_historique_ventes')
def api_get_historique_ventes():
    if 'boutique_id' not in session:
        return jsonify([])
    
    boutique_id = session['boutique_id']
    
    # Lire les ventes
    ventes_sheet = get_sheet(boutique_id, 'ventes')
    if not ventes_sheet:
        return jsonify([])
    
    # Lire le catalogue pour avoir les prix unitaires (colonne E)
    catalogue_sheet = get_sheet(boutique_id, 'catalogue')
    prix_catalogue = {}
    if catalogue_sheet:
        cat_data = catalogue_sheet.get_all_values()
        for i in range(1, len(cat_data)):
            row = cat_data[i]
            if len(row) > 4:
                produit_nom = row[1] if len(row) > 1 else ''
                prix_vente = float(row[4]) if row[4] else 0
                prix_catalogue[produit_nom] = prix_vente
    
    data = ventes_sheet.get_all_values()
    ventes = []
    
    for i in range(1, len(data)):
        row = data[i]
        if not row or len(row) < 4:
            continue
        
        if not row[0] or not str(row[0]).startswith('VENTE_'):
            continue
        
        # Vérifier si la vente est annulée (colonne J = index 9)
        est_annulee = False
        try:
            if len(row) > 9 and row[9] == '1':
                est_annulee = True
        except:
            est_annulee = False
        
        if est_annulee:
            continue
        
        try:
            produit_nom = str(row[3]) if len(row) > 3 else ''
            
            # Prix unitaire depuis le catalogue (colonne E)
            prix_unitaire = prix_catalogue.get(produit_nom, 0)
            
            ventes.append({
                'id': str(row[0]),
                'date': str(row[1]) if len(row) > 1 else '',
                'heure': str(row[2]) if len(row) > 2 else '',
                'produit': produit_nom,
                'quantite': int(float(row[4])) if len(row) > 4 and row[4] else 0,
                'prix_unitaire': prix_unitaire,  # ← NOUVEAU : prix conseillé du catalogue
                'prix_vendu': float(row[5]) if len(row) > 5 and row[5] else 0,
                'total': float(row[7]) if len(row) > 7 and row[7] else 0,
                'vendeur': str(row[8]) if len(row) > 8 else ''
            })
        except Exception as e:
            continue
    
    return jsonify(ventes[::-1])

@app.route('/api/get_caisse_jour')
def api_get_caisse_jour():
    if 'boutique_id' not in session:
        return jsonify({'totalVentes': 0, 'nbVentes': 0, 'nbProduitsVendus': 0, 'remiseTotale': 0, 'date': '', 'ventes': []})
    
    sheet = get_sheet(session['boutique_id'], 'ventes')
    if not sheet:
        return jsonify({'totalVentes': 0, 'nbVentes': 0, 'nbProduitsVendus': 0, 'remiseTotale': 0, 'date': '', 'ventes': []})
    
    aujourd_hui = datetime.now().strftime('%d/%m/%Y')
    data = sheet.get_all_values()
    ventes_jour = []
    total = 0
    total_encaisse = 0
    nb_ventes = 0
    nb_produits = 0
    remises = 0

    for i in range(1, len(data)):
        row = data[i]
        if len(row) > 1 and row[1] == aujourd_hui:

            # VÉRIFICATION : Ignorer les ventes annulées (colonne J = index 9)
            est_annulee = False
            try:
                if len(row) > 9 and row[9] == '1':
                    est_annulee = True
            except:
                pass

            if est_annulee:
                continue  # ← On saute cette vente, elle ne sera pas comptée

            try:
                def to_float(val):
                    try:
                        return float(val) if val and str(val).replace('.', '').replace('-', '').isdigit() else 0
                    except:
                        return 0

                def to_int(val):
                    try:
                        return int(val) if val and str(val).isdigit() else 0
                    except:
                        return 0

                qte = to_int(row[4]) if len(row) > 4 else 0
                prix_vendu = to_float(row[5]) if len(row) > 5 else 0
                remise = to_float(row[6]) if len(row) > 6 else 0
                total_net = to_float(row[7]) if len(row) > 7 else 0
                # Montant réellement encaissé (colonne M) : si vente à crédit
                # partielle, sinon égal au total net (rétro-compatible avec
                # les ventes enregistrées avant l'ajout des créances).
                montant_encaisse = to_float(row[12]) if len(row) > 12 and row[12] not in ('', None) else total_net
                creance_liee = str(row[13]) if len(row) > 13 else ''

                ventes_jour.append({
                    'heure': str(row[2]) if len(row) > 2 else '',
                    'produit': str(row[3]) if len(row) > 3 else '',
                    'quantite': qte,
                    'prixVendu': prix_vendu,
                    'remise': remise,
                    'totalNet': total_net,
                    'montantEncaisse': montant_encaisse,
                    'creance': bool(creance_liee),
                    'vendeur': str(row[8]) if len(row) > 8 else ''
                })
                total += total_net
                total_encaisse += montant_encaisse
                nb_ventes += 1
                nb_produits += qte
                remises += remise
            except:
                pass

    # Charges validées aujourd'hui : diminuent la caisse
    charges_validees = 0
    charges_sheet = get_sheet(session['boutique_id'], 'charges')
    if charges_sheet:
        for row in charges_sheet.get_all_values()[1:]:
            if len(row) > 9 and row[7] == 'VALIDEE' and str(row[9]).startswith(aujourd_hui):
                charges_validees += to_float_sur(row[4])

    # Paiements de créances validés aujourd'hui : augmentent la caisse
    paiements_creances = 0
    paiements_sheet = get_sheet(session['boutique_id'], 'creances_paiements')
    if paiements_sheet:
        for row in paiements_sheet.get_all_values()[1:]:
            if len(row) > 8 and row[6] == 'VALIDEE' and str(row[8]).startswith(aujourd_hui):
                paiements_creances += to_float_sur(row[4])

    caisse_nette = total_encaisse + paiements_creances - charges_validees

    return jsonify({
        'totalVentes': total,
        'totalEncaisse': total_encaisse,
        'chargesValidees': charges_validees,
        'paiementsCreances': paiements_creances,
        'caisseNette': caisse_nette,
        'nbVentes': nb_ventes,
        'nbProduitsVendus': nb_produits,
        'remiseTotale': remises,
        'date': aujourd_hui,
        'ventes': ventes_jour
    })

@app.route('/api/demander_charge', methods=['POST'])
def api_demander_charge():
    if 'boutique_id' not in session:
        return jsonify({'success': False, 'error': 'Non connecté'})

    data = request.get_json()
    boutique_id = session['boutique_id']
    categorie = (data.get('categorie') or 'Autre').strip()
    motif = (data.get('motif') or '').strip()
    montant = to_float_sur(data.get('montant'))

    if montant <= 0:
        return jsonify({'success': False, 'error': 'Montant invalide'})

    charges_sheet = get_or_create_sheet(boutique_id, 'charges', CHARGES_HEADERS)
    charge_id = generer_id('CHARGE')
    now = datetime.now()
    demandeur = session.get('user_nom', 'Gérant')
    charges_sheet.append_row([
        charge_id, now.strftime('%d/%m/%Y'), now.strftime('%H:%M:%S'),
        categorie, montant, motif, demandeur, 'EN_ATTENTE', '', '', ''
    ])
    resume = f"Charge « {categorie} » de {montant:,.0f} FCFA demandée par {demandeur}".replace(',', ' ')
    _creer_demande(boutique_id, 'charge', charge_id, resume, demandeur)

    return jsonify({'success': True, 'message': 'Charge enregistrée, en attente de validation du gérant'})


@app.route('/api/get_charges')
def api_get_charges():
    if 'boutique_id' not in session:
        return jsonify([])

    boutique_id = session['boutique_id']
    statut_filtre = request.args.get('statut')
    sheet = get_sheet(boutique_id, 'charges')
    if not sheet:
        return jsonify([])

    data = sheet.get_all_values()
    charges = []
    for i in range(1, len(data)):
        row = data[i]
        if len(row) < 8:
            continue
        statut = row[7]
        if statut_filtre and statut != statut_filtre:
            continue
        charges.append({
            'id': row[0], 'date': row[1], 'heure': row[2], 'categorie': row[3],
            'montant': to_float_sur(row[4]), 'motif': row[5], 'demandeur': row[6],
            'statut': statut,
            'validePar': row[8] if len(row) > 8 else '',
            'dateValidation': row[9] if len(row) > 9 else '',
            'motifRefus': row[10] if len(row) > 10 else ''
        })
    return jsonify(charges[::-1])


@app.route('/api/get_creances')
def api_get_creances():
    if 'boutique_id' not in session:
        return jsonify([])

    boutique_id = session['boutique_id']
    statut_filtre = request.args.get('statut')  # 'OUVERTES' = restant > 0
    sheet = get_sheet(boutique_id, 'creances')
    if not sheet:
        return jsonify([])

    data = sheet.get_all_values()
    creances = []
    for i in range(1, len(data)):
        row = data[i]
        if len(row) < 9:
            continue
        statut = row[8]
        if statut_filtre == 'OUVERTES' and statut == 'SOLDEE':
            continue
        creances.append({
            'id': row[0], 'date': row[1], 'heure': row[2],
            'clientNom': row[3], 'clientTelephone': row[4],
            'montantTotal': to_float_sur(row[5]),
            'montantPaye': to_float_sur(row[6]),
            'montantRestant': to_float_sur(row[7]),
            'statut': statut,
            'vendeur': row[9] if len(row) > 9 else ''
        })
    return jsonify(creances[::-1])


@app.route('/api/enregistrer_paiement_creance', methods=['POST'])
def api_enregistrer_paiement_creance():
    if 'boutique_id' not in session:
        return jsonify({'success': False, 'error': 'Non connecté'})

    data = request.get_json()
    boutique_id = session['boutique_id']
    creance_id = data.get('creanceId')
    montant = to_float_sur(data.get('montant'))

    if montant <= 0:
        return jsonify({'success': False, 'error': 'Montant invalide'})

    creances_sheet = get_sheet(boutique_id, 'creances')
    if not creances_sheet:
        return jsonify({'success': False, 'error': 'Créance introuvable'})

    creances_data = creances_sheet.get_all_values()
    creance = None
    for row in creances_data[1:]:
        if len(row) > 0 and row[0] == creance_id:
            creance = row
            break
    if not creance:
        return jsonify({'success': False, 'error': 'Créance introuvable'})

    montant_restant = to_float_sur(creance[7]) if len(creance) > 7 else 0
    if montant > montant_restant + 0.01:
        return jsonify({'success': False, 'error': f'Le montant dépasse le restant dû ({montant_restant:,.0f} FCFA)'.replace(',', ' ')})

    paiements_sheet = get_or_create_sheet(boutique_id, 'creances_paiements', CREANCES_PAIEMENTS_HEADERS)
    paiement_id = generer_id('PAYCR')
    now = datetime.now()
    demandeur = session.get('user_nom', 'Gérant')
    paiements_sheet.append_row([
        paiement_id, creance_id, now.strftime('%d/%m/%Y'), now.strftime('%H:%M:%S'),
        montant, demandeur, 'EN_ATTENTE', '', '', ''
    ])
    resume = f"Paiement créance de {creance[3]} : {montant:,.0f} FCFA enregistré par {demandeur}".replace(',', ' ')
    _creer_demande(boutique_id, 'paiement_creance', paiement_id, resume, demandeur)

    return jsonify({'success': True, 'message': 'Paiement enregistré, en attente de validation du gérant'})


@app.route('/api/get_demandes')
def api_get_demandes():
    if 'boutique_id' not in session:
        return jsonify([])

    boutique_id = session['boutique_id']
    statut_filtre = request.args.get('statut', 'EN_ATTENTE')
    demandeur_filtre = None if est_gerant() else session.get('user_nom')
    sheet = get_sheet(boutique_id, 'demandes')
    if not sheet:
        return jsonify([])

    data = sheet.get_all_values()
    demandes = []
    for i in range(1, len(data)):
        row = data[i]
        if len(row) < 8:
            continue
        if statut_filtre != 'TOUTES' and row[7] != statut_filtre:
            continue
        if demandeur_filtre and row[6] != demandeur_filtre:
            continue
        demandes.append({
            'id': row[0], 'date': row[1], 'heure': row[2], 'type': row[3],
            'referenceId': row[4], 'resume': row[5], 'demandeur': row[6],
            'statut': row[7],
            'traitePar': row[8] if len(row) > 8 else '',
            'dateTraitement': row[9] if len(row) > 9 else '',
            'motifRefus': row[10] if len(row) > 10 else ''
        })
    return jsonify(demandes[::-1])


@app.route('/api/get_demandes_count')
def api_get_demandes_count():
    if not est_gerant():
        return jsonify({'count': 0})

    sheet = get_sheet(session['boutique_id'], 'demandes')
    if not sheet:
        return jsonify({'count': 0})

    data = sheet.get_all_values()
    count = sum(1 for i in range(1, len(data)) if len(data[i]) > 7 and data[i][7] == 'EN_ATTENTE')
    return jsonify({'count': count})


@app.route('/api/traiter_demande', methods=['POST'])
def api_traiter_demande():
    if 'boutique_id' not in session:
        return jsonify({'success': False, 'error': 'Non connecté'})
    if not est_gerant():
        return jsonify({'success': False, 'error': 'Réservé au gérant'})

    data = request.get_json()
    boutique_id = session['boutique_id']
    demande_id = data.get('id')
    type_in = data.get('type')
    reference_id_in = data.get('referenceId')
    action = data.get('action')  # 'valider' | 'refuser'
    motif_refus = (data.get('motifRefus') or '').strip()
    traite_par = session.get('user_nom', 'Gérant')

    if action not in ('valider', 'refuser'):
        return jsonify({'success': False, 'error': 'Action inconnue'})

    sheet = get_sheet(boutique_id, 'demandes')
    if not sheet:
        return jsonify({'success': False, 'error': 'Demande introuvable'})

    # Identification soit par l'id de la demande (page "Demandes"), soit par
    # son type + la référence de l'objet concerné (validation directe depuis
    # la page Charges ou Créances, sans connaître l'id de la demande).
    rows = sheet.get_all_values()
    ligne, idx = None, None
    for i in range(1, len(rows)):
        row = rows[i]
        if len(row) < 8:
            continue
        if demande_id and row[0] == demande_id:
            ligne, idx = row, i
            break
        if not demande_id and type_in and row[3] == type_in and str(row[4]) == str(reference_id_in) and row[7] == 'EN_ATTENTE':
            ligne, idx = row, i
            break
    if not ligne:
        return jsonify({'success': False, 'error': 'Demande introuvable'})
    if len(ligne) > 7 and ligne[7] != 'EN_ATTENTE':
        return jsonify({'success': False, 'error': 'Cette demande a déjà été traitée'})

    type_demande = ligne[3]
    reference_id = ligne[4]

    if type_demande == 'charge':
        ok, message = _executer_validation_charge(boutique_id, reference_id, action, traite_par, motif_refus)
    elif type_demande == 'paiement_creance':
        ok, message = _executer_validation_paiement_creance(boutique_id, reference_id, action, traite_par, motif_refus)
    else:
        return jsonify({'success': False, 'error': f'Type de demande inconnu: {type_demande}'})

    if not ok:
        return jsonify({'success': False, 'error': message})

    nouveau_statut = 'VALIDEE' if action == 'valider' else 'REFUSEE'
    now = datetime.now()
    sheet.update_cell(idx + 1, 8, nouveau_statut)
    sheet.update_cell(idx + 1, 9, traite_par)
    sheet.update_cell(idx + 1, 10, now.strftime('%d/%m/%Y %H:%M:%S'))
    if motif_refus:
        sheet.update_cell(idx + 1, 11, motif_refus)

    return jsonify({'success': True, 'message': message})


@app.route('/api/get_vendeurs')
def api_get_vendeurs():
    if 'boutique_id' not in session:
        return jsonify([])
    
    sheet = get_sheet(session['boutique_id'], 'vendeurs')
    if not sheet:
        return jsonify([])
    
    data = sheet.get_all_values()
    vendeurs = []
    for i in range(1, len(data)):
        row = data[i]
        if row and len(row) > 0 and row[0]:
            vendeurs.append({
                'id': row[0],
                'username': row[1] if len(row) > 1 else '',
                'nom': row[3] if len(row) > 3 else '',
                'actif': row[4] == 'oui' if len(row) > 4 else True
            })
    return jsonify(vendeurs)

@app.route('/api/ajouter_vendeur', methods=['POST'])
def api_ajouter_vendeur():
    if 'boutique_id' not in session:
        return jsonify({'success': False, 'error': 'Non connecté'})
    
    data = request.get_json()
    sheet = get_sheet(session['boutique_id'], 'vendeurs')
    if not sheet:
        return jsonify({'success': False, 'error': 'Erreur'})
    
    password_hash = hashlib.sha256(data.get('password').encode()).hexdigest()
    existing = sheet.get_all_values()
    new_id = len(existing)
    
    row = [new_id, data.get('username'), password_hash, data.get('nom'), 'oui']
    sheet.append_row(row)
    return jsonify({'success': True, 'message': 'Vendeur ajouté'})

@app.route('/api/toggle_vendeur', methods=['POST'])
def api_toggle_vendeur():
    if 'boutique_id' not in session:
        return jsonify({'success': False})
    
    data = request.get_json()
    sheet = get_sheet(session['boutique_id'], 'vendeurs')
    if not sheet:
        return jsonify({'success': False})
    
    all_data = sheet.get_all_values()
    for i in range(1, len(all_data)):
        if len(all_data[i]) > 0 and str(all_data[i][0]) == str(data.get('id')):
            new_status = 'inactif' if data.get('actif') else 'oui'
            sheet.update_cell(i+1, 5, new_status)
            break
    
    return jsonify({'success': True})

@app.route('/api/approvisionner', methods=['POST'])
def api_approvisionner():
    if 'boutique_id' not in session:
        return jsonify({'success': False, 'error': 'Non connecté'})
    
    data = request.get_json()
    boutique_id = session['boutique_id']
    
    stock_sheet = get_sheet(boutique_id, 'stock')
    if not stock_sheet:
        return jsonify({'success': False, 'error': 'Erreur stock'})
    
    stock_data = stock_sheet.get_all_values()
    produit_trouve = False
    for i in range(1, len(stock_data)):
        if len(stock_data[i]) > 1 and stock_data[i][1] == data.get('produit'):
            ancien_stock = int(stock_data[i][2]) if len(stock_data[i]) > 2 else 0
            nouveau_stock = ancien_stock + data.get('quantite')
            stock_sheet.update_cell(i+1, 3, nouveau_stock)
            produit_trouve = True
            break
    
    if not produit_trouve:
        return jsonify({'success': False, 'error': 'Produit non trouvé'})
    
    journal_sheet = get_sheet(boutique_id, 'journal')
    if journal_sheet:
        journal_row = [
            datetime.now().strftime('%d/%m/%Y'),
            datetime.now().strftime('%H:%M:%S'),
            'APPROVISIONNEMENT',
            data.get('produit'),
            data.get('quantite'),
            ancien_stock,
            nouveau_stock,
            session.get('user_nom', 'Gérant'),
            data.get('fournisseur', '')
        ]
        journal_sheet.append_row(journal_row)
    
    return jsonify({'success': True, 'message': f'Ajout de {data.get("quantite")} {data.get("produit")} au stock'})

@app.route('/api/get_approvisionnements')
def api_get_approvisionnements():
    if 'boutique_id' not in session:
        return jsonify([])
    
    sheet = get_sheet(session['boutique_id'], 'journal')
    if not sheet:
        return jsonify([])
    
    data = sheet.get_all_values()
    appros = []
    for i in range(1, len(data)):
        row = data[i]
        if len(row) > 2 and row[2] == 'APPROVISIONNEMENT':
            appros.append({
                'date': row[0] if len(row) > 0 else '',
                'heure': row[1] if len(row) > 1 else '',
                'produit': row[3] if len(row) > 3 else '',
                'quantite': row[4] if len(row) > 4 else '',
                'fournisseur': row[8] if len(row) > 8 else ''
            })
    return jsonify(appros[::-1])

@app.route('/api/get_statistiques')
def api_get_statistiques():
    STATS_VIDES = {
        'chiffreAffaire': 0, 'encaisse': 0, 'charges': 0, 'caisseNette': 0,
        'nbVentes': 0, 'nbProduitsVendus': 0, 'ticketMoyen': 0,
        'topProduits': [], 'topVendeurs': []
    }
    if 'boutique_id' not in session:
        return jsonify(STATS_VIDES)

    boutique_id = session['boutique_id']
    periode = request.args.get('periode', 'jour')
    date_debut = request.args.get('date_debut', '')
    date_fin = request.args.get('date_fin', '')

    sheet = get_sheet(boutique_id, 'ventes')
    if not sheet:
        return jsonify(STATS_VIDES)

    data = sheet.get_all_values()
    
    # Obtenir les dates aujourd'hui
    aujourd_hui = datetime.now()
    
    # Début de semaine (lundi)
    debut_semaine = aujourd_hui - timedelta(days=aujourd_hui.weekday())
    debut_semaine = debut_semaine.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Début du mois
    debut_mois = aujourd_hui.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Début de l'année
    debut_annee = aujourd_hui.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Fonction pour parser une date au format DD/MM/YYYY
    def parser_date(date_str):
        try:
            jour, mois, annee = date_str.split('/')
            return datetime(int(annee), int(mois), int(jour))
        except:
            return None
    
    # Fonction pour vérifier si une date est dans la période
    def est_dans_periode(date_vente):
        if not date_vente:
            return False
        
        date_obj = parser_date(date_vente)
        if not date_obj:
            return False
        
        if periode == 'jour':
            return date_obj.date() == aujourd_hui.date()
        elif periode == 'semaine':
            return date_obj >= debut_semaine
        elif periode == 'mois':
            return date_obj >= debut_mois
        elif periode == 'annee':
            return date_obj >= debut_annee
        elif periode == 'personnalise' and date_debut and date_fin:
            debut = datetime.strptime(date_debut, '%Y-%m-%d')
            fin = datetime.strptime(date_fin, '%Y-%m-%d')
            fin = fin.replace(hour=23, minute=59, second=59)
            return debut <= date_obj <= fin
        return True
    
    # Filtrer les ventes
    ventes = []
    for i in range(1, len(data)):
        row = data[i]
        if len(row) > 7 and row[0] and row[0].startswith('VENTE'):
            try:
                # VÉRIFIER SI LA VENTE EST ANNULÉE (colonne J = index 9)
                est_annulee = False
                try:
                    if len(row) > 9 and row[9] == '1':
                        est_annulee = True
                except:
                    pass
                
                if est_annulee:
                    continue  # ← On ignore cette vente
                
                date_vente = row[1] if len(row) > 1 else ''
                if est_dans_periode(date_vente):
                    # Déterminer la colonne du total (colonne H = index 7)
                    total = float(row[7]) if len(row) > 7 and row[7] else 0
                    # Montant réellement encaissé (colonne M) : si vente à
                    # crédit partielle, sinon égal au total (rétro-compatible
                    # avec les ventes enregistrées avant l'ajout des créances).
                    montant_encaisse = to_float_sur(row[12]) if len(row) > 12 and row[12] not in ('', None) else total
                    ventes.append({
                        'produit': row[3] if len(row) > 3 else '',
                        'quantite': int(float(row[4])) if len(row) > 4 and row[4] else 0,
                        'total': total,
                        'montantEncaisse': montant_encaisse,
                        'vendeur': row[8] if len(row) > 8 else ''
                    })
            except Exception as e:
                print(f"Erreur lecture vente: {e}")
    
    # Calcul des stats
    chiffreAffaire = sum(v['total'] for v in ventes)
    nbVentes = len(ventes)
    nbProduitsVendus = sum(v['quantite'] for v in ventes)
    ticketMoyen = chiffreAffaire / nbVentes if nbVentes > 0 else 0

    # Encaissé sur les ventes (hors part encore due sur les créances)
    encaisse_ventes = sum(v['montantEncaisse'] for v in ventes)

    # Paiements de créances validés sur la période : ce cash arrive à la
    # date de VALIDATION, pas à la date de la vente d'origine.
    paiements_creances = 0
    paiements_sheet = get_sheet(boutique_id, 'creances_paiements')
    if paiements_sheet:
        for row in paiements_sheet.get_all_values()[1:]:
            if len(row) > 8 and row[6] == 'VALIDEE':
                date_validation = str(row[8]).split(' ')[0]
                if est_dans_periode(date_validation):
                    paiements_creances += to_float_sur(row[4])

    # Charges validées sur la période : déduites de la caisse à la date de
    # VALIDATION (voir /api/get_caisse_jour pour la même logique au jour).
    charges_validees = 0
    charges_sheet = get_sheet(boutique_id, 'charges')
    if charges_sheet:
        for row in charges_sheet.get_all_values()[1:]:
            if len(row) > 9 and row[7] == 'VALIDEE':
                date_validation = str(row[9]).split(' ')[0]
                if est_dans_periode(date_validation):
                    charges_validees += to_float_sur(row[4])

    encaisse = encaisse_ventes + paiements_creances
    caisseNette = encaisse - charges_validees
    
    # Top produits
    produits_stats = {}
    for v in ventes:
        if v['produit'] not in produits_stats:
            produits_stats[v['produit']] = {'quantite': 0, 'chiffre': 0}
        produits_stats[v['produit']]['quantite'] += v['quantite']
        produits_stats[v['produit']]['chiffre'] += v['total']
    
    topProduits = sorted([{'produit': p, 'quantite': d['quantite'], 'chiffreAffaire': d['chiffre']} for p, d in produits_stats.items() if p], key=lambda x: x['quantite'], reverse=True)[:5]
    
    # Top vendeurs
    vendeurs_stats = {}
    for v in ventes:
        if v['vendeur'] not in vendeurs_stats:
            vendeurs_stats[v['vendeur']] = {'nbVentes': 0, 'chiffre': 0}
        vendeurs_stats[v['vendeur']]['nbVentes'] += 1
        vendeurs_stats[v['vendeur']]['chiffre'] += v['total']
    
    topVendeurs = sorted([{'vendeur': v, 'nbVentes': d['nbVentes'], 'chiffreAffaire': d['chiffre']} for v, d in vendeurs_stats.items() if v], key=lambda x: x['chiffreAffaire'], reverse=True)[:5]
    
    return jsonify({
        'chiffreAffaire': chiffreAffaire,
        'encaisse': encaisse,
        'charges': charges_validees,
        'caisseNette': caisseNette,
        'nbVentes': nbVentes,
        'nbProduitsVendus': nbProduitsVendus,
        'ticketMoyen': ticketMoyen,
        'topProduits': topProduits,
        'topVendeurs': topVendeurs
    })

@app.route('/api/annuler_vente', methods=['POST'])
def api_annuler_vente():
    if 'boutique_id' not in session:
        return jsonify({'success': False, 'error': 'Non connecté'})
    
    data = request.get_json()
    boutique_id = session['boutique_id']
    
    stock_sheet = get_sheet(boutique_id, 'stock')
    if stock_sheet:
        stock_data = stock_sheet.get_all_values()
        for i in range(1, len(stock_data)):
            if len(stock_data[i]) > 1 and stock_data[i][1] == data.get('produit'):
                ancien_stock = int(stock_data[i][2]) if len(stock_data[i]) > 2 else 0
                nouveau_stock = ancien_stock + data.get('quantite')
                stock_sheet.update_cell(i+1, 3, nouveau_stock)
                break
    
    journal_sheet = get_sheet(boutique_id, 'journal')
    if journal_sheet:
        journal_row = [
            datetime.now().strftime('%d/%m/%Y'),
            datetime.now().strftime('%H:%M:%S'),
            'ANNULATION_VENTE',
            data.get('produit'),
            data.get('quantite'),
            0, 0,
            session.get('user_nom', 'Gérant'),
            f"Annulation vente {data.get('id')}"
        ]
        journal_sheet.append_row(journal_row)
    
    return jsonify({'success': True, 'message': f'Vente de {data.get("produit")} annulée et stock restauré'})
# Ajoutez ces routes dans app_multi.py (avant le if __name__ == '__main__':)

@app.route('/dashboard_multi')
def dashboard_multi():
    if 'boutique_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('dashboard_multi.html', boutique=session.get('boutique_nom'))

@app.route('/api/get_dashboard_stats')
def api_get_dashboard_stats():
    if 'boutique_id' not in session:
        return jsonify({'ca_jour': 0, 'ca_mois': 0, 'nb_produits': 0, 'alertes': 0, 'produits_critiques': []})
    
    boutique_id = session['boutique_id']
    
    # 1. Chiffre d'affaires depuis les ventes (en excluant les annulées)
    ventes_sheet = get_sheet(boutique_id, 'ventes')
    ca_jour = 0
    ca_mois = 0
    
    if ventes_sheet:
        data = ventes_sheet.get_all_values()
        aujourd_hui = datetime.now().strftime('%d/%m/%Y')
        mois_actuel = datetime.now().month
        annee_actuelle = datetime.now().year
        
        for i in range(1, len(data)):
            row = data[i]
            if len(row) > 7:  # Au moins 8 colonnes
                try:
                    # VÉRIFIER SI LA VENTE EST ANNULÉE (colonne J = index 9)
                    est_annulee = False
                    try:
                        if len(row) > 9 and row[9] == '1':
                            est_annulee = True
                    except:
                        pass
                    
                    if est_annulee:
                        continue  # ← On ignore cette vente
                    
                    # La colonne total est à l'index 7 (colonne H)
                    total = float(row[7]) if row[7] and str(row[7]).replace('.', '').isdigit() else 0
                    date_vente = row[1] if len(row) > 1 else ''
                    
                    if date_vente == aujourd_hui:
                        ca_jour += total
                    
                    # Vérifier si dans le mois
                    if '/' in date_vente:
                        parts = date_vente.split('/')
                        if len(parts) == 3:
                            if int(parts[1]) == mois_actuel and int(parts[2]) == annee_actuelle:
                                ca_mois += total
                except Exception as e:
                    print(f"Erreur lecture vente: {e}")
    
    # 2. Nombre de produits
    catalogue_sheet = get_sheet(boutique_id, 'catalogue')
    nb_produits = 0
    if catalogue_sheet:
        cat_data = catalogue_sheet.get_all_values()
        nb_produits = len(cat_data) - 1 if len(cat_data) > 1 else 0
    
    # 3. Alertes stock
    stock_sheet = get_sheet(boutique_id, 'stock')
    alertes = 0
    produits_critiques = []
    
    if stock_sheet:
        stock_data = stock_sheet.get_all_values()
        for i in range(1, len(stock_data)):
            row = stock_data[i]
            if len(row) > 2:
                try:
                    stock = int(float(row[2])) if row[2] else 0
                    seuil = int(float(row[3])) if len(row) > 3 and row[3] else 10
                    if stock <= seuil:
                        alertes += 1
                        produits_critiques.append({
                            'produit_nom': row[1] if len(row) > 1 else 'Inconnu',
                            'stock_restant': stock,
                            'seuil_alerte': seuil
                        })
                except:
                    pass
    
    # Demandes en attente (charges / paiements de créance) - gérant uniquement
    demandes_en_attente = 0
    if est_gerant():
        demandes_sheet = get_sheet(boutique_id, 'demandes')
        if demandes_sheet:
            demandes_data = demandes_sheet.get_all_values()
            demandes_en_attente = sum(1 for i in range(1, len(demandes_data)) if len(demandes_data[i]) > 7 and demandes_data[i][7] == 'EN_ATTENTE')

    print(f"DEBUG - CA Jour: {ca_jour}, CA Mois: {ca_mois}, Produits: {nb_produits}, Alertes: {alertes}")

    return jsonify({
        'ca_jour': ca_jour,
        'ca_mois': ca_mois,
        'nb_produits': nb_produits,
        'alertes': alertes,
        'produits_critiques': produits_critiques,
        'demandes_en_attente': demandes_en_attente
    })
@app.route('/api/test_dashboard')
def test_dashboard():
    if 'boutique_id' not in session:
        return jsonify({'error': 'Non connecté'})
    
    sheet = get_sheet(session['boutique_id'], 'ventes')
    if not sheet:
        return jsonify({'error': 'Feuille non trouvée'})
    
    data = sheet.get_all_values()
    total = 0
    for i in range(1, len(data)):
        row = data[i]
        if len(row) > 8:
            try:
                val = str(row[8]).strip().replace(',', '.')
                if val and (val.replace('.', '').isdigit() or val.isdigit()):
                    total += float(val)
            except:
                pass
    
    return jsonify({'total_ventes': total, 'nb_lignes': len(data)-1})
@app.route('/api/get_messages_gerant')
def get_messages_gerant():
    boutique_id = request.args.get('boutique_id')
    
    sheet_name = f"boutique{boutique_id}_messages"
    try:
        sheet = spreadsheet.worksheet(sheet_name)
    except:
        return jsonify([])
    
    data = sheet.get_all_values()
    messages = []
    for i in range(1, len(data)):
        row = data[i]
        if len(row) > 3:
            messages.append({
                'id': row[0],
                'date': row[1],
                'heure': row[2],
                'expediteur': row[3],
                'message': row[4],
                'lu': row[5] if len(row) > 5 else 'NON'
            })
    return jsonify(messages[::-1])

@app.route('/api/marquer_message_lu', methods=['POST'])
def marquer_message_lu():
    data = request.get_json()
    message_id = data.get('id')
    boutique_id = data.get('boutique_id')
    
    sheet_name = f"boutique{boutique_id}_messages"
    try:
        sheet = spreadsheet.worksheet(sheet_name)
    except:
        return jsonify({'success': False})
    
    all_data = sheet.get_all_values()
    for i in range(1, len(all_data)):
        if len(all_data[i]) > 0 and str(all_data[i][0]) == str(message_id):
            now = datetime.now()
            date_lu = now.strftime('%d/%m/%Y')
            heure_lu = now.strftime('%H:%M:%S')
            sheet.update_cell(i+1, 6, 'OUI')
            sheet.update_cell(i+1, 7, f"{date_lu} {heure_lu}")
            break
    
    return jsonify({'success': True})

@app.route('/api/repondre_message', methods=['POST'])
def repondre_message():
    data = request.get_json()
    message_id = data.get('id')
    boutique_id = data.get('boutique_id')
    destinataire = data.get('destinataire')
    reponse = data.get('reponse')
    
    # Ajouter la réponse comme un nouveau message
    sheet_name = f"boutique{boutique_id}_messages"
    try:
        sheet = spreadsheet.worksheet(sheet_name)
    except:
        sheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=20)
        sheet.append_row(['id', 'date', 'heure', 'expediteur', 'message', 'lu', 'lu_le', 'reponse', 'repondu_le'])
    
    import random
    new_id = random.randint(1, 999999)
    now = datetime.now()
    date = now.strftime('%d/%m/%Y')
    heure = now.strftime('%H:%M:%S')
    
    sheet.append_row([new_id, date, heure, 'Gérant', reponse, 'NON', '', '', ''])
    
    # Mettre à jour le message original avec la réponse
    all_data = sheet.get_all_values()
    for i in range(1, len(all_data)):
        if len(all_data[i]) > 0 and str(all_data[i][0]) == str(message_id):
            sheet.update_cell(i+1, 9, f"{date} {heure}")
            break
    
    return jsonify({'success': True, 'message': 'Réponse envoyée'})
@app.route('/messages_gerant')
def messages_gerant():
    if 'boutique_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('messages_gerant.html')
@app.route('/api/envoyer_message_vendeur', methods=['POST'])
def envoyer_message_vendeur():
    data = request.get_json()
    boutique_id = data.get('boutique_id')
    expediteur = data.get('expediteur')
    message = data.get('message')
    
    sheet_name = f"boutique{boutique_id}_messages"
    try:
        sheet = spreadsheet.worksheet(sheet_name)
    except:
        sheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=20)
        sheet.append_row(['id', 'date', 'heure', 'expediteur', 'message', 'lu', 'lu_le', 'reponse', 'repondu_le'])
    
    import random
    new_id = random.randint(1, 999999)
    now = datetime.now()
    date = now.strftime('%d/%m/%Y')
    heure = now.strftime('%H:%M:%S')
    
    sheet.append_row([new_id, date, heure, expediteur, message, 'NON', '', '', ''])
    return jsonify({'success': True, 'message': 'Message envoyé'})

@app.route('/api/get_messages_vendeur')
def get_messages_vendeur():
    boutique_id = request.args.get('boutique_id')
    vendeur = request.args.get('vendeur')
    
    sheet_name = f"boutique{boutique_id}_messages"
    try:
        sheet = spreadsheet.worksheet(sheet_name)
    except:
        return jsonify([])
    
    data = sheet.get_all_values()
    messages = []
    for i in range(1, len(data)):
        row = data[i]
        if len(row) > 3 and (row[3] == vendeur or row[3] == 'Gérant'):
            messages.append({
                'id': row[0],
                'date': row[1],
                'heure': row[2],
                'expediteur': row[3],
                'message': row[4],
                'lu': row[5] if len(row) > 5 else 'NON'
            })
    return jsonify(messages[::-1])

@app.route('/dashboard_vendeur')
def dashboard_vendeur():
    if 'boutique_id' not in session or session.get('user_role') != 'vendeur':
        return redirect(url_for('login_page'))
    return render_template('dashboard_vendeur.html')

@app.route('/messages_vendeur')
def messages_vendeur():
    if 'boutique_id' not in session or session.get('user_role') != 'vendeur':
        return redirect(url_for('login_page'))
    return render_template('messages_vendeur.html')

@app.route('/api/connexion_vendeur', methods=['POST'])
def api_connexion_vendeur():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    print(f"Tentative connexion vendeur: {username}")
    
    password_hash = hash_password(password)
    print(f"Hash du mot de passe: {password_hash}")
    
    # Parcourir toutes les boutiques (1 à 30)
    for boutique_id in range(1, 31):
        sheet = get_sheet(boutique_id, 'vendeurs')
        if not sheet:
            continue
        
        vendeurs = sheet.get_all_values()
        print(f"Boutique {boutique_id}: {len(vendeurs)} vendeurs trouvés")
        
        for i in range(1, len(vendeurs)):
            row = vendeurs[i]
            if len(row) > 1:
                print(f"  Vérification: {row[1]} vs {username}")
                if row[1] == username and row[2] == password_hash and row[4] == 'oui':
                    print(f"Vendeur trouvé dans boutique {boutique_id}")
                    session['boutique_id'] = boutique_id
                    session['user_role'] = 'vendeur'
                    session['user_nom'] = row[3] if len(row) > 3 else username
                    session['vendeur_id'] = row[0]
                    return jsonify({'success': True, 'role': 'vendeur'})
    
    print("Vendeur non trouvé")
    return jsonify({'success': False, 'error': 'Identifiants incorrects'})


# ========== CONNEXION PAR BIOMÉTRIE (Face ID / Windows Hello / empreinte) ==========
# Auto-enregistrement uniquement : un compte (gérant ou vendeur) ne peut
# enregistrer que SON PROPRE appareil, une fois déjà connecté par mot de
# passe. Ensuite, cet appareil permet de se reconnecter sans mot de passe.

@app.route('/api/webauthn/inscription/options', methods=['POST'])
def api_webauthn_inscription_options():
    if 'boutique_id' not in session:
        return jsonify({'success': False, 'error': 'Non connecté'}), 401

    type_compte = 'vendeur' if session.get('user_role') == 'vendeur' else 'gerant'
    options_json, challenge = webauthn_service.options_inscription(
        request, spreadsheet, session['boutique_id'], type_compte,
        session.get('vendeur_id'), session.get('user_nom') or session.get('boutique_nom'),
    )
    session['webauthn_challenge'] = challenge
    return jsonify({'success': True, 'options': json.loads(options_json)})


@app.route('/api/webauthn/inscription/verifier', methods=['POST'])
def api_webauthn_inscription_verifier():
    if 'boutique_id' not in session:
        return jsonify({'success': False, 'error': 'Non connecté'}), 401

    data = request.get_json() or {}
    challenge = session.pop('webauthn_challenge', None)
    if not challenge:
        return jsonify({'success': False, 'error': 'Session expirée, recommencez.'}), 400

    type_compte = 'vendeur' if session.get('user_role') == 'vendeur' else 'gerant'
    try:
        webauthn_service.verifier_inscription(
            request, spreadsheet, session['boutique_id'], type_compte,
            session.get('vendeur_id'), session.get('user_nom') or session.get('boutique_nom'),
            data.get('credential'), challenge,
            libelle_appareil=data.get('libelle_appareil'),
        )
        return jsonify({'success': True})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': f"Échec de l'enregistrement : {e}"}), 400


@app.route('/api/webauthn/mes-appareils')
def api_webauthn_mes_appareils():
    if 'boutique_id' not in session:
        return jsonify({'success': False, 'data': []}), 401

    type_compte = 'vendeur' if session.get('user_role') == 'vendeur' else 'gerant'
    appareils = webauthn_service.lister_appareils(spreadsheet, session['boutique_id'], type_compte, session.get('vendeur_id'))
    return jsonify({'success': True, 'data': appareils})


@app.route('/api/webauthn/appareils/<int:ligne>', methods=['DELETE'])
def api_webauthn_revoquer(ligne):
    if 'boutique_id' not in session:
        return jsonify({'success': False, 'error': 'Non connecté'}), 401

    type_compte = 'vendeur' if session.get('user_role') == 'vendeur' else 'gerant'
    ok = webauthn_service.revoquer_appareil(spreadsheet, ligne, session['boutique_id'], type_compte, session.get('vendeur_id'))
    if not ok:
        return jsonify({'success': False, 'error': 'Introuvable'}), 404
    return jsonify({'success': True})


@app.route('/login/webauthn/options', methods=['POST'])
def login_webauthn_options():
    """Public — page de connexion, personne n'est encore authentifié."""
    options_json, challenge = webauthn_service.options_connexion(request)
    session['webauthn_login_challenge'] = challenge
    return jsonify({'success': True, 'options': json.loads(options_json)})


@app.route('/login/webauthn/verifier', methods=['POST'])
def login_webauthn_verifier():
    """Public. Identifie le compte à partir de la clé biométrique elle-même,
    puis pose la session exactement comme pour la connexion par mot de passe."""
    data = request.get_json() or {}
    challenge = session.pop('webauthn_login_challenge', None)
    if not challenge:
        return jsonify({'success': False, 'error': 'Session expirée, recommencez.'}), 400

    try:
        identifiant = webauthn_service.verifier_connexion(request, spreadsheet, data.get('credential'), challenge)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 401
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Échec de la connexion : {e}'}), 400

    boutique_id = int(identifiant['boutique_id'])

    if identifiant['type_compte'] == 'vendeur':
        vendeur_id = identifiant['vendeur_id']
        sheet = get_sheet(boutique_id, 'vendeurs')
        vendeur_row = None
        if sheet:
            for row in sheet.get_all_values()[1:]:
                if len(row) > 0 and row[0] == vendeur_id:
                    vendeur_row = row
                    break
        if not vendeur_row or (len(vendeur_row) > 4 and vendeur_row[4] != 'oui'):
            return jsonify({'success': False, 'error': 'Compte vendeur introuvable ou désactivé'}), 401
        session['boutique_id'] = boutique_id
        session['user_role'] = 'vendeur'
        session['user_nom'] = vendeur_row[3] if len(vendeur_row) > 3 else identifiant['utilisateur_nom']
        session['vendeur_id'] = vendeur_row[0]
        return jsonify({'success': True, 'redirect': url_for('dashboard_vendeur')})

    boutique = get_boutique_by_id(boutique_id)
    if not boutique or boutique['actif'] != 'oui':
        return jsonify({'success': False, 'error': 'Boutique introuvable ou en attente de validation'}), 401
    session['boutique_id'] = boutique['id']
    session['boutique_nom'] = boutique['nom_boutique']
    session['email'] = boutique['email']
    return jsonify({'success': True, 'redirect': url_for('dashboard_boutique')})


# ========== ADMIN GLOBAL (RESERVE AU CONCEPTEUR) ==========

# Mot de passe admin global (change-le)
ADMIN_GLOBAL_PASSWORD = os.environ.get('ADMIN_PASSWORD')

@app.route('/admin_global')
def admin_global():
    # Vérifier si l'admin est connecté
    if session.get('admin_global') != True:
        return redirect(url_for('login_admin_global'))
    return render_template('admin_global.html')

@app.route('/login_admin_global', methods=['GET', 'POST'])
def login_admin_global():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_GLOBAL_PASSWORD:
            session['admin_global'] = True
            return redirect(url_for('admin_global'))
        else:
            return render_template('login_admin_global.html', error="Mot de passe incorrect")
    return render_template('login_admin_global.html')

@app.route('/api/get_toutes_boutiques')
def get_toutes_boutiques():
    if session.get('admin_global') != True:
        return jsonify({'error': 'Non autorisé'})
    
    sheet = spreadsheet.worksheet("BOUTIQUES")
    data = sheet.get_all_values()
    
    boutiques = []
    for i in range(1, len(data)):
        row = data[i]
        if len(row) > 0:
            boutiques.append({
                'id': row[0],
                'nom': row[1] if len(row) > 1 else '',
                'email': row[2] if len(row) > 2 else '',
                'telephone': row[4] if len(row) > 4 else '',
                'adresse': row[5] if len(row) > 5 else '',
                'date': row[6] if len(row) > 6 else '',
                'actif': row[7] if len(row) > 7 else 'oui'
            })
    return jsonify(boutiques)

@app.route('/api/admin_desactiver_boutique', methods=['POST'])
def admin_desactiver_boutique():
    if session.get('admin_global') != True:
        return jsonify({'error': 'Non autorisé'})
    
    data = request.get_json()
    email = data.get('email')
    actif = data.get('actif')
    
    sheet = spreadsheet.worksheet("BOUTIQUES")
    all_data = sheet.get_all_values()
    
    for i in range(1, len(all_data)):
        if len(all_data[i]) > 2 and all_data[i][2] == email:
            nouvelle_valeur = 'oui' if actif else 'non'
            sheet.update_cell(i+1, 8, nouvelle_valeur)
            return jsonify({'success': True, 'message': f'Boutique {all_data[i][1]} mise à jour'})
    
    return jsonify({'success': False, 'error': 'Boutique non trouvée'})

@app.route('/logout_admin')
def logout_admin():
    session.pop('admin_global', None)
    return redirect(url_for('login_admin_global'))

@app.route('/api/admin_valider_boutique', methods=['POST'])
def admin_valider_boutique():
    if session.get('admin_global') != True:
        return jsonify({'error': 'Non autorisé'})
    
    data = request.get_json()
    email = data.get('email')
    action = data.get('action')  # 'activer' ou 'refuser'
    
    sheet = spreadsheet.worksheet("BOUTIQUES")
    all_data = sheet.get_all_values()
    
    for i in range(1, len(all_data)):
        if len(all_data[i]) > 2 and all_data[i][2] == email:
            if action == 'activer':
                sheet.update_cell(i+1, 8, 'oui')
                return jsonify({'success': True, 'message': f'Boutique {all_data[i][1]} activée'})
            elif action == 'refuser':
                sheet.update_cell(i+1, 8, 'refuse')
                return jsonify({'success': True, 'message': f'Boutique {all_data[i][1]} refusée'})
    
    return jsonify({'success': False, 'error': 'Boutique non trouvée'})

@app.route('/api/get_evolution_ventes')
def get_evolution_ventes():
    if 'boutique_id' not in session:
        return jsonify({'labels': [], 'values': []})
    
    sheet = get_sheet(session['boutique_id'], 'ventes')
    if not sheet:
        return jsonify({'labels': [], 'values': []})
    
    data = sheet.get_all_values()
    
    # Regrouper par date (en excluant les ventes annulées)
    ventes_par_jour = {}
    for i in range(1, len(data)):
        row = data[i]
        if len(row) > 7:  # Au moins 8 colonnes
            try:
                # VÉRIFIER SI LA VENTE EST ANNULÉE (colonne J = index 9)
                est_annulee = False
                try:
                    if len(row) > 9 and row[9] == '1':
                        est_annulee = True
                except:
                    pass
                
                if est_annulee:
                    continue  # ← On ignore cette vente
                
                date = row[1] if len(row) > 1 else ''
                total = float(row[7]) if row[7] and str(row[7]).replace('.', '').isdigit() else 0
                if date:
                    ventes_par_jour[date] = ventes_par_jour.get(date, 0) + total
            except:
                pass
    
    # 7 derniers jours
    from datetime import datetime, timedelta
    labels = []
    values = []
    today = datetime.now()
    
    for i in range(6, -1, -1):
        date = (today - timedelta(days=i)).strftime('%d/%m/%Y')
        labels.append(date)
        values.append(ventes_par_jour.get(date, 0))
    
    print(f"DEBUG Evolution - Labels: {labels}")
    print(f"DEBUG Evolution - Values: {values}")
    
    return jsonify({'labels': labels, 'values': values})

@app.route('/api/traiter_correction_vente', methods=['POST'])
def api_traiter_correction_vente():
    if 'boutique_id' not in session:
        return jsonify({'success': False, 'error': 'Non connecté'})
    
    data = request.get_json()
    boutique_id = session['boutique_id']
    action = data.get('action')
    
    try:
        ventes_sheet = get_sheet(boutique_id, 'ventes')
        stock_sheet = get_sheet(boutique_id, 'stock')
        journal_sheet = get_sheet(boutique_id, 'journal')
        
        if not ventes_sheet:
            return jsonify({'success': False, 'error': 'Feuille ventes non trouvée'})
        
        # ========== ANNULATION ==========
        if action == 'annulation':
            # Marquer la vente comme annulée (colonne J)
            ventes_data = ventes_sheet.get_all_values()
            for i in range(1, len(ventes_data)):
                if len(ventes_data[i]) > 0 and ventes_data[i][0] == data.get('id'):
                    # S'assurer qu'il y a assez de colonnes (jusqu'à la colonne L = index 11)
                    while len(ventes_data[i]) < 12:
                        ventes_data[i].append('')
                    
                    # Marquer comme annulée (colonne J = index 9)
                    ventes_sheet.update_cell(i+1, 10, '1')
                    
                    # Enregistrer le motif (colonne K = index 10)
                    motif = data.get('motif', 'Annulation')
                    ventes_sheet.update_cell(i+1, 11, motif)
                    
                    # Enregistrer la date d'annulation (colonne L = index 11)
                    date_annulation = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
                    ventes_sheet.update_cell(i+1, 12, date_annulation)
                    break
            
            # Restaurer le stock
            if stock_sheet:
                stock_data = stock_sheet.get_all_values()
                for i in range(1, len(stock_data)):
                    if len(stock_data[i]) > 1 and stock_data[i][1] == data.get('produit'):
                        ancien_stock = int(stock_data[i][2]) if len(stock_data[i]) > 2 else 0
                        nouveau_stock = ancien_stock + data.get('quantite')
                        stock_sheet.update_cell(i+1, 3, nouveau_stock)
                        break
            
            # Journal
            if journal_sheet:
                journal_sheet.append_row([
                    datetime.now().strftime('%d/%m/%Y'),
                    datetime.now().strftime('%H:%M:%S'),
                    'ANNULATION_VENTE',
                    data.get('produit'),
                    data.get('quantite'),
                    0, 0,
                    session.get('user_nom', 'Gérant'),
                    data.get('motif', 'Annulation')
                ])
            
            return jsonify({'success': True, 'message': f'Vente de {data.get("produit")} annulée'})
        
        # ========== CORRECTION PRIX ==========
        elif action == 'correctionPrix':
            nouveau_prix = data.get('nouveauPrix')
            ancien_prix = data.get('prix_vendu')
            quantite = data.get('quantite')
            motif = data.get('motif', 'Correction prix')
            
            # Calculer le nouveau total
            nouveau_total = quantite * nouveau_prix
            
            # Mettre à jour la vente dans la feuille
            ventes_data = ventes_sheet.get_all_values()
            for i in range(1, len(ventes_data)):
                if len(ventes_data[i]) > 0 and ventes_data[i][0] == data.get('id'):
                    # Mettre à jour le prix (colonne F = index 5)
                    ventes_sheet.update_cell(i+1, 6, nouveau_prix)
                    # Mettre à jour le total (colonne H = index 7)
                    ventes_sheet.update_cell(i+1, 8, nouveau_total)
                    break
            
            # Journal
            if journal_sheet:
                journal_sheet.append_row([
                    datetime.now().strftime('%d/%m/%Y'),
                    datetime.now().strftime('%H:%M:%S'),
                    'CORRECTION_PRIX',
                    data.get('produit'),
                    quantite,
                    ancien_prix,
                    nouveau_prix,
                    session.get('user_nom', 'Gérant'),
                    f"{motif} | Ancien: {ancien_prix} → Nouveau: {nouveau_prix}"
                ])
            
            return jsonify({'success': True, 'message': f'Prix corrigé: {ancien_prix} → {nouveau_prix} FCFA'})
        
        # ========== CORRECTION QUANTITÉ ==========
        elif action == 'correctionQuantite':
            nouvelle_quantite = data.get('nouvelleQuantite')
            ancienne_quantite = data.get('quantite')
            prix = data.get('prix_vendu')
            motif = data.get('motif', 'Correction quantité')
            
            # Calculer le nouveau total
            nouveau_total = nouvelle_quantite * prix
            
            # Mettre à jour la vente dans la feuille
            ventes_data = ventes_sheet.get_all_values()
            for i in range(1, len(ventes_data)):
                if len(ventes_data[i]) > 0 and ventes_data[i][0] == data.get('id'):
                    # Mettre à jour la quantité (colonne E = index 4)
                    ventes_sheet.update_cell(i+1, 5, nouvelle_quantite)
                    # Mettre à jour le total (colonne H = index 7)
                    ventes_sheet.update_cell(i+1, 8, nouveau_total)
                    break
            
            # Ajuster le stock (différence de quantité)
            diff_quantite = nouvelle_quantite - ancienne_quantite
            if stock_sheet:
                stock_data = stock_sheet.get_all_values()
                for i in range(1, len(stock_data)):
                    if len(stock_data[i]) > 1 and stock_data[i][1] == data.get('produit'):
                        ancien_stock = int(stock_data[i][2]) if len(stock_data[i]) > 2 else 0
                        nouveau_stock = ancien_stock - diff_quantite  # Si + de quantité, - de stock
                        stock_sheet.update_cell(i+1, 3, nouveau_stock)
                        break
            
            # Journal
            if journal_sheet:
                journal_sheet.append_row([
                    datetime.now().strftime('%d/%m/%Y'),
                    datetime.now().strftime('%H:%M:%S'),
                    'CORRECTION_QUANTITE',
                    data.get('produit'),
                    f"{ancienne_quantite}→{nouvelle_quantite}",
                    0, 0,
                    session.get('user_nom', 'Gérant'),
                    f"{motif} | Stock ajusté: {diff_quantite:+d}"
                ])
            
            return jsonify({'success': True, 'message': f'Quantité corrigée: {ancienne_quantite} → {nouvelle_quantite}'})
        
        # ========== REMBOURSEMENT PARTIEL ==========
        elif action == 'remboursement':
            montant_rembourse = data.get('montantRemboursement')
            total_original = data.get('total')
            motif = data.get('motif', 'Remboursement partiel')
            
            # Calculer le nouveau total
            nouveau_total = total_original - montant_rembourse
            
            # Mettre à jour la vente dans la feuille
            ventes_data = ventes_sheet.get_all_values()
            for i in range(1, len(ventes_data)):
                if len(ventes_data[i]) > 0 and ventes_data[i][0] == data.get('id'):
                    # Mettre à jour le total (colonne H = index 7)
                    ventes_sheet.update_cell(i+1, 8, nouveau_total)
                    # Ajouter une note dans la colonne remise ou ailleurs
                    if len(ventes_data[i]) <= 9:
                        for _ in range(len(ventes_data[i]), 10):
                            ventes_sheet.update_cell(i+1, _+1, '')
                    ventes_sheet.update_cell(i+1, 10, f"Remboursé: {montant_rembourse}")
                    break
            
            # Journal
            if journal_sheet:
                journal_sheet.append_row([
                    datetime.now().strftime('%d/%m/%Y'),
                    datetime.now().strftime('%H:%M:%S'),
                    'REMBOURSEMENT',
                    data.get('produit'),
                    data.get('quantite'),
                    total_original,
                    nouveau_total,
                    session.get('user_nom', 'Gérant'),
                    f"{motif} | Remboursé: {montant_rembourse} FCFA"
                ])
            
            return jsonify({'success': True, 'message': f'Remboursement de {montant_rembourse} FCFA effectué'})
        
        return jsonify({'success': False, 'error': 'Action non reconnue'})
        
    except Exception as e:
        print(f"Erreur: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get_stock_complet')
def api_get_stock_complet():
    if 'boutique_id' not in session:
        return jsonify({'stock': [], 'nbProduits': 0, 'valeurStock': 0, 'alertes': 0, 'ruptures': 0})
    
    boutique_id = session['boutique_id']
    
    # Lire depuis la feuille STOCK directement
    stock_sheet = get_sheet(boutique_id, 'stock')
    if not stock_sheet:
        return jsonify({'stock': [], 'nbProduits': 0, 'valeurStock': 0, 'alertes': 0, 'ruptures': 0})
    
    # Lire le catalogue pour les prix
    catalogue_sheet = get_sheet(boutique_id, 'catalogue')
    prix_dict = {}
    if catalogue_sheet:
        cat_data = catalogue_sheet.get_all_values()
        for i in range(1, len(cat_data)):
            row = cat_data[i]
            if len(row) > 4:
                produit_nom = row[1] if len(row) > 1 else ''
                prix_vente = float(row[4]) if row[4] else 0
                prix_dict[produit_nom] = prix_vente
    
    stock_data = stock_sheet.get_all_values()
    stock_list = []
    nb_produits = 0
    valeur_stock = 0
    alertes = 0
    ruptures = 0
    
    for i in range(1, len(stock_data)):
        row = stock_data[i]
        if len(row) > 2 and row[1]:
            produit_nom = row[1]
            stock_actuel = int(row[2]) if row[2] else 0
            seuil = int(row[3]) if len(row) > 3 and row[3] else 10
            prix_vente = prix_dict.get(produit_nom, 0)
            
            nb_produits += 1
            valeur_stock += stock_actuel * prix_vente
            
            if stock_actuel <= 0:
                ruptures += 1
            elif stock_actuel <= seuil:
                alertes += 1
            
            stock_list.append({
                'id': row[0] if len(row) > 0 else '',
                'produit': produit_nom,
                'stockActuel': stock_actuel,
                'seuil': seuil,
                'prixVente': prix_vente
            })
    
    return jsonify({
        'stock': stock_list,
        'nbProduits': nb_produits,
        'valeurStock': valeur_stock,
        'alertes': alertes,
        'ruptures': ruptures
    })

@app.route('/api/supprimer_produit', methods=['POST'])
def api_supprimer_produit():
    if 'boutique_id' not in session:
        return jsonify({'success': False, 'error': 'Non connecté'})
    
    data = request.get_json()
    produit_nom = data.get('nom')
    boutique_id = session['boutique_id']
    
    try:
        # Supprimer du catalogue
        catalogue_sheet = get_sheet(boutique_id, 'catalogue')
        if not catalogue_sheet:
            return jsonify({'success': False, 'error': 'Feuille catalogue non trouvée'})
        
        cat_data = catalogue_sheet.get_all_values()
        ligne_trouvee = -1
        
        for i in range(1, len(cat_data)):
            if len(cat_data[i]) > 1 and cat_data[i][1] == produit_nom:
                ligne_trouvee = i + 1  # Google Sheets est 1-indexé
                break
        
        if ligne_trouvee != -1:
            catalogue_sheet.delete_rows(ligne_trouvee)  # ← delete_rows (pluriel)
        else:
            return jsonify({'success': False, 'error': 'Produit non trouvé dans le catalogue'})
        
        # Supprimer aussi du stock
        stock_sheet = get_sheet(boutique_id, 'stock')
        if stock_sheet:
            stock_data = stock_sheet.get_all_values()
            for i in range(1, len(stock_data)):
                if len(stock_data[i]) > 1 and stock_data[i][1] == produit_nom:
                    stock_sheet.delete_rows(i + 1)  # ← delete_rows (pluriel)
                    break
        
        # Journal
        journal_sheet = get_sheet(boutique_id, 'journal')
        if journal_sheet:
            from datetime import datetime
            journal_sheet.append_row([
                datetime.now().strftime('%d/%m/%Y'),
                datetime.now().strftime('%H:%M:%S'),
                'SUPPRESSION_PRODUIT',
                produit_nom,
                0, 0, 0,
                session.get('user_nom', 'Gérant'),
                'Produit supprimé du catalogue'
            ])
        
        return jsonify({'success': True, 'message': f'Produit "{produit_nom}" supprimé avec succès'})
        
    except Exception as e:
        print(f"Erreur suppression: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/admin_reset_password', methods=['POST'])
def admin_reset_password():
    if session.get('admin_global') != True:
        return jsonify({'error': 'Non autorisé'})
    
    data = request.get_json()
    email = data.get('email')
    role = data.get('role', 'boutique')  # 'boutique' ou 'vendeur'
    nouveau_mdp = data.get('nouveau_mdp')
    
    if not email or not nouveau_mdp:
        return jsonify({'success': False, 'error': 'Email et nouveau mot de passe requis'})
    
    if len(nouveau_mdp) < 4:
        return jsonify({'success': False, 'error': 'Le mot de passe doit contenir au moins 4 caractères'})
    
    if role == 'boutique':
        # Réinitialiser mot de passe d'une boutique
        sheet = spreadsheet.worksheet("BOUTIQUES")
        all_data = sheet.get_all_values()
        
        for i in range(1, len(all_data)):
            if len(all_data[i]) > 2 and all_data[i][2] == email:
                sheet.update_cell(i+1, 4, hash_password(nouveau_mdp))
                return jsonify({'success': True, 'message': f'Mot de passe de la boutique "{all_data[i][1]}" réinitialisé à: {nouveau_mdp}'})
        
        return jsonify({'success': False, 'error': 'Boutique non trouvée'})
    
    elif role == 'vendeur':
        # Réinitialiser mot de passe d'un vendeur (dans toutes les boutiques)
        for boutique_id in range(1, 31):
            sheet = get_sheet(boutique_id, 'vendeurs')
            if sheet:
                all_data = sheet.get_all_values()
                for i in range(1, len(all_data)):
                    if len(all_data[i]) > 2 and all_data[i][1] == email:
                        sheet.update_cell(i+1, 3, hash_password(nouveau_mdp))
                        return jsonify({'success': True, 'message': f'Mot de passe du vendeur "{all_data[i][3]}" réinitialisé à: {nouveau_mdp}'})
        
        return jsonify({'success': False, 'error': 'Vendeur non trouvé'})
    
    return jsonify({'success': False, 'error': 'Rôle invalide'})

@app.route('/api/modifier_produit', methods=['POST'])
def api_modifier_produit():
    if 'boutique_id' not in session:
        return jsonify({'success': False, 'error': 'Non connecté'})
    
    data = request.get_json()
    boutique_id = session['boutique_id']
    produit_id = data.get('id')
    
    try:
        # 1. Modifier dans le catalogue
        catalogue_sheet = get_sheet(boutique_id, 'catalogue')
        if not catalogue_sheet:
            return jsonify({'success': False, 'error': 'Feuille catalogue non trouvée'})
        
        cat_data = catalogue_sheet.get_all_values()
        ligne_trouvee = -1
        
        for i in range(1, len(cat_data)):
            if len(cat_data[i]) > 0 and cat_data[i][0] == produit_id:
                ligne_trouvee = i + 1
                break
        
        if ligne_trouvee == -1:
            return jsonify({'success': False, 'error': 'Produit non trouvé dans le catalogue'})
        
        # Mettre à jour le catalogue
        catalogue_sheet.update_cell(ligne_trouvee, 2, data.get('nom'))
        catalogue_sheet.update_cell(ligne_trouvee, 3, data.get('categorie', ''))
        catalogue_sheet.update_cell(ligne_trouvee, 4, data.get('prixAchat', 0))
        catalogue_sheet.update_cell(ligne_trouvee, 5, data.get('prixVente', 0))
        catalogue_sheet.update_cell(ligne_trouvee, 6, data.get('stock', 0))
        catalogue_sheet.update_cell(ligne_trouvee, 7, data.get('seuil', 10))
        
        # 2. Modifier dans le stock
        stock_sheet = get_sheet(boutique_id, 'stock')
        if stock_sheet:
            stock_data = stock_sheet.get_all_values()
            for i in range(1, len(stock_data)):
                if len(stock_data[i]) > 0 and stock_data[i][0] == produit_id:
                    stock_sheet.update_cell(i+1, 2, data.get('nom'))
                    stock_sheet.update_cell(i+1, 3, data.get('stock', 0))
                    stock_sheet.update_cell(i+1, 4, data.get('seuil', 10))
                    break
        
        # 3. Journal
        journal_sheet = get_sheet(boutique_id, 'journal')
        if journal_sheet:
            journal_sheet.append_row([
                datetime.now().strftime('%d/%m/%Y'),
                datetime.now().strftime('%H:%M:%S'),
                'MODIFICATION_PRODUIT',
                data.get('nom'),
                0, 0, 0,
                session.get('user_nom', 'Gérant'),
                f"Produit modifié: {data.get('nom')}"
            ])
        
        return jsonify({'success': True, 'message': f'Produit "{data.get("nom")}" modifié avec succès'})
        
    except Exception as e:
        print(f"Erreur modification: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/ventes_annulees')
def ventes_annulees():
    if 'boutique_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('ventes_annulees.html')

@app.route('/api/get_ventes_annulees')
def api_get_ventes_annulees():
    if 'boutique_id' not in session:
        return jsonify([])
    
    boutique_id = session['boutique_id']
    
    ventes_sheet = get_sheet(boutique_id, 'ventes')
    if not ventes_sheet:
        return jsonify([])
    
    data = ventes_sheet.get_all_values()
    ventes_annulees = []
    
    for i in range(1, len(data)):
        row = data[i]
        if len(row) < 4:
            continue
        
        if not row[0] or not str(row[0]).startswith('VENTE_'):
            continue
        
        # VÉRIFIER SI LA VENTE EST ANNULÉE (colonne J = index 9)
        est_annulee = False
        try:
            if len(row) > 9 and row[9] == '1':
                est_annulee = True
        except:
            pass
        
        if not est_annulee:
            continue  # ← On garde uniquement les annulées
        
        try:
            # Récupérer le motif d'annulation (colonne K = index 10)
            motif = ''
            try:
                if len(row) > 10 and row[10]:
                    motif = row[10]
            except:
                pass
            
            # Récupérer la date d'annulation (colonne L = index 11)
            date_annulation = ''
            try:
                if len(row) > 11 and row[11]:
                    date_annulation = row[11]
            except:
                pass
            
            ventes_annulees.append({
                'id': str(row[0]),
                'date': str(row[1]) if len(row) > 1 else '',
                'heure': str(row[2]) if len(row) > 2 else '',
                'produit': str(row[3]) if len(row) > 3 else '',
                'quantite': int(float(row[4])) if len(row) > 4 and row[4] else 0,
                'prix_vendu': float(row[5]) if len(row) > 5 and row[5] else 0,
                'total': float(row[7]) if len(row) > 7 and row[7] else 0,
                'vendeur': str(row[8]) if len(row) > 8 else '',
                'motif': motif,
                'date_annulation': date_annulation
            })
        except Exception as e:
            print(f"Erreur lecture vente annulée: {e}")
            continue
    
    return jsonify(ventes_annulees[::-1])  # Du plus récent au plus ancien

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)