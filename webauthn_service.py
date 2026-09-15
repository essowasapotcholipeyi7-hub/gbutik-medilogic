# webauthn_service.py
"""
Connexion par biométrie de l'appareil (Face ID / Windows Hello / empreinte),
via WebAuthn — même principe que dans GHP (services/webauthn_login_service.py),
adapté ici au stockage Google Sheets de GBoutik-MediLogic au lieu de SQLAlchemy.

Les identifiants biométriques sont stockés dans une feuille globale unique
"WEBAUTHN_CREDENTIALS" (et non par boutique), car au moment de la connexion
on ne sait pas encore à quelle boutique/compte l'appareil appartient : c'est
justement le credential_id qui permet de le retrouver.

Deux cérémonies :
  - Inscription (un compte déjà connecté enregistre CET appareil) :
    options_inscription() puis verifier_inscription().
  - Connexion (à la place du mot de passe), via clé résidente
    ("discoverable credential") : options_connexion() puis
    verifier_connexion(), qui identifie directement le compte à partir de
    la clé biométrique, sans email/identifiant saisi au préalable.

Important : WebAuthn n'est autorisé par les navigateurs que sur
"localhost" ou en HTTPS — pas sur une adresse IP locale en http:// simple.
"""

import base64
from datetime import datetime

import webauthn
from webauthn.helpers.structs import (
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

RP_NAME = "GBoutik-MediLogic"
WEBAUTHN_HEADERS = [
    'credential_id', 'public_key', 'sign_count', 'boutique_id', 'type_compte',
    'vendeur_id', 'utilisateur_nom', 'libelle_appareil', 'date_creation',
    'derniere_utilisation', 'actif'
]


def _rp_id_et_origin(request):
    rp_id = request.host.split(':')[0]
    est_local = rp_id in ('localhost', '127.0.0.1', '::1')
    scheme = request.scheme if est_local else 'https'
    origin = f"{scheme}://{request.host}"
    return rp_id, origin


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode('ascii')


def _unb64(s: str) -> bytes:
    return base64.b64decode(s.encode('ascii'))


def _handle_compte(boutique_id, type_compte, vendeur_id) -> bytes:
    """Identifiant interne (<=64 octets) encodé dans la clé résidente par
    l'authentificateur ; le compte est en fait retrouvé via credential_id
    (voir verifier_connexion), ceci ne sert qu'à satisfaire l'API."""
    return f"{type_compte}:{boutique_id}:{vendeur_id or ''}".encode('utf-8')


def _get_or_create_sheet(spreadsheet):
    try:
        return spreadsheet.worksheet("WEBAUTHN_CREDENTIALS")
    except Exception:
        sheet = spreadsheet.add_worksheet(title="WEBAUTHN_CREDENTIALS", rows=2000, cols=len(WEBAUTHN_HEADERS))
        sheet.append_row(WEBAUTHN_HEADERS)
        return sheet


# ----------------------------------------------------------------------
# Inscription d'un appareil (compte déjà connecté)
# ----------------------------------------------------------------------

def options_inscription(request, spreadsheet, boutique_id, type_compte, vendeur_id, utilisateur_nom):
    rp_id, _ = _rp_id_et_origin(request)
    sheet = _get_or_create_sheet(spreadsheet)

    existants = []
    for row in sheet.get_all_values()[1:]:
        if len(row) < 11:
            continue
        if (str(row[3]) == str(boutique_id) and row[4] == type_compte
                and str(row[5]) == str(vendeur_id or '') and row[10] == 'oui'):
            existants.append(row[0])
    exclude = [PublicKeyCredentialDescriptor(id=_unb64(cid)) for cid in existants]

    options = webauthn.generate_registration_options(
        rp_id=rp_id,
        rp_name=RP_NAME,
        user_id=_handle_compte(boutique_id, type_compte, vendeur_id),
        user_name=utilisateur_nom or f"compte-{boutique_id}",
        user_display_name=utilisateur_nom or f"compte-{boutique_id}",
        authenticator_selection=AuthenticatorSelectionCriteria(
            # PLATFORM : force le capteur intégré (Face ID/Windows
            # Hello/empreinte), pas une clé de sécurité USB externe.
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            # REQUIRED : la clé doit être "résidente"/découvrable pour que
            # la page de connexion puisse la proposer sans connaître le
            # compte à l'avance.
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=exclude,
    )
    challenge_b64 = _b64(options.challenge)
    return webauthn.options_to_json(options), challenge_b64


def verifier_inscription(request, spreadsheet, boutique_id, type_compte, vendeur_id, utilisateur_nom,
                          credential_json, challenge_b64, libelle_appareil=None):
    rp_id, origin = _rp_id_et_origin(request)

    verification = webauthn.verify_registration_response(
        credential=credential_json,
        expected_challenge=_unb64(challenge_b64),
        expected_rp_id=rp_id,
        expected_origin=origin,
        require_user_verification=True,
    )

    sheet = _get_or_create_sheet(spreadsheet)
    now = datetime.now()
    sheet.append_row([
        _b64(verification.credential_id),
        _b64(verification.credential_public_key),
        verification.sign_count,
        boutique_id,
        type_compte,
        vendeur_id or '',
        utilisateur_nom or '',
        libelle_appareil or request.host,
        now.strftime('%d/%m/%Y %H:%M:%S'),
        '',
        'oui'
    ])


def lister_appareils(spreadsheet, boutique_id, type_compte, vendeur_id):
    sheet = _get_or_create_sheet(spreadsheet)
    appareils = []
    for i, row in enumerate(sheet.get_all_values()[1:], start=2):
        if len(row) < 11:
            continue
        if (str(row[3]) == str(boutique_id) and row[4] == type_compte
                and str(row[5]) == str(vendeur_id or '') and row[10] == 'oui'):
            appareils.append({
                'ligne': i,
                'libelle_appareil': row[7],
                'date_creation': row[8],
                'derniere_utilisation': row[9],
            })
    return appareils


def revoquer_appareil(spreadsheet, ligne, boutique_id, type_compte, vendeur_id):
    sheet = _get_or_create_sheet(spreadsheet)
    data = sheet.get_all_values()
    if ligne < 2 or ligne > len(data):
        return False
    row = data[ligne - 1]
    if len(row) < 11:
        return False
    if not (str(row[3]) == str(boutique_id) and row[4] == type_compte and str(row[5]) == str(vendeur_id or '')):
        return False
    sheet.update_cell(ligne, 11, 'non')
    return True


# ----------------------------------------------------------------------
# Connexion (identification par la clé biométrique elle-même)
# ----------------------------------------------------------------------

def options_connexion(request):
    """Pas de allow_credentials : c'est le principe d'une clé résidente —
    le navigateur retrouve tout seul les clés déjà enregistrées sur cet
    appareil pour ce site (Face ID/Windows Hello affiche son sélecteur)."""
    rp_id, _ = _rp_id_et_origin(request)
    options = webauthn.generate_authentication_options(
        rp_id=rp_id,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    challenge_b64 = _b64(options.challenge)
    return webauthn.options_to_json(options), challenge_b64


def verifier_connexion(request, spreadsheet, credential_json, challenge_b64):
    """Vérifie la clé biométrique et identifie le compte. Retourne un dict
    {boutique_id, type_compte, vendeur_id, utilisateur_nom, ligne} - c'est
    à l'appelant (app_multi.py) de résoudre le compte dans Google Sheets et
    de poser la session. Lève ValueError avec un message utilisateur en cas
    d'échec."""
    import json
    rp_id, origin = _rp_id_et_origin(request)

    cred_dict = json.loads(credential_json) if isinstance(credential_json, str) else credential_json
    credential_id_b64url = cred_dict.get('id') or cred_dict.get('rawId')
    if not credential_id_b64url:
        raise ValueError("Réponse de l'appareil incomplète.")

    raw_id = webauthn.base64url_to_bytes(credential_id_b64url)
    credential_id_b64 = _b64(raw_id)

    sheet = _get_or_create_sheet(spreadsheet)
    data = sheet.get_all_values()
    ligne_idx, row = None, None
    for i in range(1, len(data)):
        r = data[i]
        if len(r) > 10 and r[0] == credential_id_b64 and r[10] == 'oui':
            ligne_idx, row = i, r
            break
    if not row:
        raise ValueError("Cet appareil n'est associé à aucun compte (ou a été révoqué).")

    verification = webauthn.verify_authentication_response(
        credential=credential_json,
        expected_challenge=_unb64(challenge_b64),
        expected_rp_id=rp_id,
        expected_origin=origin,
        credential_public_key=_unb64(row[1]),
        credential_current_sign_count=int(row[2]) if row[2] else 0,
        require_user_verification=True,
    )

    now = datetime.now()
    sheet.update_cell(ligne_idx + 1, 3, verification.new_sign_count)
    sheet.update_cell(ligne_idx + 1, 10, now.strftime('%d/%m/%Y %H:%M:%S'))

    return {
        'boutique_id': row[3],
        'type_compte': row[4],
        'vendeur_id': row[5],
        'utilisateur_nom': row[6],
    }
