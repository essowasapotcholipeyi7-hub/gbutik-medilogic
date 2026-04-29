import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ========== REMPLACE CES INFOS ==========
EMAIL_EXPEDITEUR = "essowasainfo60@gmail.com"      # Ton adresse Gmail
EMAIL_MDP = "ndjocscwtvgwyfhs"            # Mot de passe d'application (sans espaces)
EMAIL_DESTINATAIRE = "essowasainfo60@gmail.com"    # Où tu veux recevoir (ou ton email)
# ========================================

print("📧 Test d'envoi d'email...")
print(f"📤 Expéditeur: {EMAIL_EXPEDITEUR}")
print(f"📥 Destinataire: {EMAIL_DESTINATAIRE}")
print(f"🔑 Mot de passe: {'*' * len(EMAIL_MDP)}")

# Nettoyer le mot de passe (enlever les espaces)
EMAIL_MDP = EMAIL_MDP.replace(" ", "")

try:
    sujet = "✅ Test GBoutik-MediLogic - Email fonctionne !"
    message = """
    Bonjour,
    
    Ceci est un test de configuration email pour GBoutik-MediLogic.
    
    Si vous recevez ce message, l'envoi d'email fonctionne correctement !
    
    Cordialement,
    L'équipe GBoutik-MediLogic
    """
    
    # Créer le message
    msg = MIMEMultipart()
    msg['From'] = EMAIL_EXPEDITEUR
    msg['To'] = EMAIL_DESTINATAIRE
    msg['Subject'] = sujet
    msg.attach(MIMEText(message, 'plain'))
    
    # Connexion et envoi
    print("🔄 Connexion au serveur SMTP Gmail...")
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    
    print("🔐 Tentative de connexion...")
    server.login(EMAIL_EXPEDITEUR, EMAIL_MDP)
    
    print("📧 Envoi du message...")
    server.send_message(msg)
    server.quit()
    
    print("✅ EMAIL ENVOYÉ AVEC SUCCÈS !")
    print(f"📬 Vérifie ta boîte mail : {EMAIL_DESTINATAIRE}")
    
except Exception as e:
    print(f"❌ ERREUR: {e}")
    print("\n💡 Solutions possibles:")
    print("   1. Vérifie que le mot de passe d'application est correct")
    print("   2. Active la double authentification sur ton compte Gmail")
    print("   3. Vérifie que l'expéditeur et le destinataire sont valides")