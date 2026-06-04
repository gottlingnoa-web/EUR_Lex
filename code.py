import streamlit as st
import requests
import pandas as pd
from xml.etree import ElementTree as ET
import time
import json
from datetime import datetime, timedelta

# ── CONFIGURATION STREAMLIT ────────────────────────────────────────────────────
st.set_page_config(page_title="Extracteur Juridique", layout="wide")
st.title("⚖️ Extracteur de données juridiques")

# ── CONSTANTES EUR-LEX ─────────────────────────────────────────────────────────
URL_EURLEX = "https://eur-lex.europa.eu/EURLexWebService"
METADATA_MAP = {
    "CELEX (identifiant unique)": ["ID_CELEX"],
    "N° document interne": ["WORK_ID_DOCUMENT"],
    "N° au Journal Officiel UE": ["WORK_ID_DOCUMENT_JO"],
    "Titre complet": ["EXPRESSION_TITLE"],
    "Titre abrégé": ["EXPRESSION_TITLE_SHORT"],
    "Type d'acte (code)": ["FM_CODED"],
    "Type de document (libellé)": ["TYPE_OF_DOCUMENT"],
    "Institution auteur": ["WORK_IS_CREATED_BY_AGENT"],
    "Rôle de l'auteur": ["ROLE_QUALIFIER"],
    "Langue authentique": ["AUTHENTIC_LANGUAGE"],
    "Langues disponibles": ["WORK_HAS_EXPRESSION"],
    "Destinataire": ["ADDRESSEE"],
    "État membre (MNE)": ["NATIONAL_IMPLEMENTING_MEASURE_COUNTRY"],
    "ECLI (jurisprudence)": ["ECLI"],
    "Collection / Série": ["WORK_PART_OF_COLLECTION"],
    "Date du document": ["WORK_DATE_DOCUMENT"],
    "Date publication JO": ["DATE_PUBLICATION"],
    "Date entrée en vigueur": ["WORK_DATE_ENTRY_INTO_FORCE"],
    "Date fin de validité": ["DATE_END_OF_VALIDITY"],
    "Date transposition (DIR)": ["DATE_TRANSPOSITION"],
    "Date d'effet": ["DATE_EFFECT"],
    "Date de signature": ["DATE_SIGNATURE"],
    "Date de notification": ["DATE_NOTIFICATION"],
    "Date limite (échéance)": ["DATE_DEADLINE"],
    "Date création dans la base": ["WORK_DATE_CREATION"],
    "Date du corrigendum": ["WORK_DATE_CORRIGENDUM"],
    "Matière / Sujet": ["SUBJECT_MATTER"],
    "Descripteurs Eurovoc": ["EUROVOC"],
    "Code répertoire légis.": ["DIRECTORY_CODE"],
    "Base légale (article Traité)": ["LEGAL_BASIS"],
    "Base légale (code)": ["LEGAL_BASIS_CODED"],
    "Traité de référence": ["TREATY_CODE"],
    "Secteur": ["SECTOR"],
    "Forme de l'acte": ["FORM_ORIG"],
    "Statut (en vigueur / abrogé)": ["STATUS_FORCE"],
    "Version consolidée actuelle": ["CURRENT_CONSOLIDATED_VERSION"],
    "Lien vers consolidation": ["WORK_HAS_CONSOLIDATION"],
    "Nombre de pages": ["NUMBER_OF_PAGES"],
    "Juridiction (CJUE)": ["WORK_EXAMPLES_JURISDICTION"],
    "Formation de jugement": ["CASE_LAW_FORMATION"],
    "Issue / dispositif": ["CASE_LAW_OUTCOME"],
    "N° procédure interinstitutionnel": ["INTERINSTITUTIONAL_FILE_NUMBER"],
    "Type de procédure": ["PROCEDURE_TYPE"],
    "Série JO (L / C)": ["OJ_NO_SERIES"],
    "Numéro JO": ["OJ_NO_NUMBER"],
    "Page début JO": ["OJ_NO_PAGE_FIRST"],
    "Page fin JO": ["OJ_NO_PAGE_LAST"],
    "Actes fondateurs (basé sur)": ["WORK_BASED_ON"],
    "Actes d'exécution": ["WORK_IMPLEMENTED_BY"],
    "Amendé par": ["WORK_AMENDED_BY"],
    "Amende (lien amont)": ["WORK_AMENDS"],
    "Abrogé par": ["WORK_REPEALED_BY"],
    "Concept EuroVoc lié": ["WORK_IS_ABOUT_CONCEPT"],
    "Cité dans affaire CJUE": ["WORK_CITED_IN_CASE"],
    "Transposé depuis (DIR)": ["WORK_TRANSPOSES"]
}

# ── CONSTANTES LÉGIFRANCE ──────────────────────────────────────────────────────
TOKEN_URL = "https://oauth.piste.gouv.fr/api/oauth/token"
API_BASE = "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app"
FIELDS_TO_EXTRACT = ["cid", "id", "nor", "num", "title", "shortTitle", "nature", "fond", "signatureDate", "publicationDate", "dateDebut", "dateFin", "etat", "ministere", "autorite", "jorfPage", "jorfNum", "numParution", "texteHtml", "textePdf", "lienLegifrance", "codeAffecte", "articleAffecte", "visas", "nota", "observatoire"]

# ── FONCTIONS EUR-LEX ──────────────────────────────────────────────────────────
def soap_request_eurlex(username, password, query, search_language, page, rows_per_req):
    envelope = f"""<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
               xmlns:sear="http://eur-lex.europa.eu/search">
  <soap:Header>
    <wsse:Security soap:mustUnderstand="true"
        xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">
      <wsse:UsernameToken xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">
        <wsse:Username>{username}</wsse:Username>
        <wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordText">{password}</wsse:Password>
      </wsse:UsernameToken>
    </wsse:Security>
  </soap:Header>
  <soap:Body>
    <sear:searchRequest>
      <sear:expertQuery><![CDATA[{query}]]></sear:expertQuery>
      <sear:page>{page}</sear:page>
      <sear:pageSize>{rows_per_req}</sear:pageSize>
      <sear:searchLanguage>{search_language}</sear:searchLanguage>
    </sear:searchRequest>
  </soap:Body>
</soap:Envelope>"""
    try:
        resp = requests.post(
            URL_EURLEX,
            data=envelope.encode("utf-8"),
            headers={"Content-Type": "application/soap+xml; charset=utf-8"},
            timeout=60
        )
        resp.raise_for_status()
        return resp
    except Exception as e:
        st.error(f"Erreur réseau page {page}: {e}")
        return None

def extract_meta_eurlex(node, tags):
    for tag in tags:
        for elem in node.iter():
            if elem.tag.split("}")[-1] == tag:
                for child in elem.iter():
                    if child.tag.split("}")[-1] == "IDENTIFIER" and child.text:
                        val = child.text.replace("AG//", "").replace("CT//", "").strip()
                        if val and not val.startswith("http"): return val
                for child in elem.iter():
                    if child.tag.split("}")[-1] == "VALUE" and child.text:
                        val = child.text.strip()
                        if val and not val.startswith("http"): return val
                raw = " ".join(t.strip() for t in elem.itertext() if t.strip())
                clean = " ".join(w for w in raw.split() if not w.startswith("http"))
                if clean: return clean
    return "Non renseigné"

def parse_documents_eurlex(root):
    docs = []
    for elem in root.iter():
        if elem.tag.split("}")[-1] in ("document", "result"):
            row = {label: extract_meta_eurlex(elem, tags) for label, tags in METADATA_MAP.items()}
            docs.append(row)
    return docs

# ── CLASSE & FONCTIONS LÉGIFRANCE ──────────────────────────────────────────────
class PisteAuth:
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self._token = None
        self._expires_at = datetime.min

    def get_token(self):
        if datetime.now() < self._expires_at:
            return self._token
        try:
            resp = requests.post(TOKEN_URL, data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "openid"
            }, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            self._token = data["access_token"]
            self._expires_at = datetime.now() + timedelta(seconds=data.get("expires_in", 3600) - 30)
            return self._token
        except Exception as e:
            st.error(f"Erreur d'authentification PISTE : {e}")
            return None

    def headers(self):
        token = self.get_token()
        if not token: return None
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

def build_payload_legifrance(page, page_size, fond, champ, valeur, operateur, nor, num_texte, sort):
    criteres = []
    if valeur:
        criteres.append({"valeur": valeur, "operateur": operateur})

    champs = []
    if criteres:
        champs.append({"typeChamp": champ, "criteres": criteres})

    if nor:
        champs.append({"typeChamp": "NOR", "criteres": [{"valeur": nor, "operateur": "EXACTE"}]})
    if num_texte:
        champs.append({"typeChamp": "NUM", "criteres": [{"valeur": num_texte, "operateur": "EXACTE"}]})

    payload = {
        "recherche": {"champs": champs or [{"typeChamp": "ALL", "criteres": []}]},
        "fond": fond,
        "pageNumber": page,
        "pageSize": page_size,
        "sort": sort
    }
    return payload

def extract_result_legifrance(res):
    row = {}
    for field in FIELDS_TO_EXTRACT:
        val = res.get(field)
        if isinstance(val, list):
            row[field] = " | ".join(str(v) for v in val)
        elif val is None:
            row[field] = "N/A"
        else:
            row[field] = str(val)
    return row

# ── INTERFACE UTILISATEUR ──────────────────────────────────────────────────────
tab1, tab2 = st.tabs(["🇪🇺 EUR-Lex", "🇫🇷 Légifrance"])

# --- ONGLET EUR-LEX ---
with tab1:
    st.header("Extraction depuis EUR-Lex")
    
    col1, col2 = st.columns(2)
    with col1:
        eur_username = st.text_input("Nom d'utilisateur EUR-Lex", key="eur_user")
        eur_password = st.text_input("Mot de passe EUR-Lex", type="password", key="eur_pass")
    with col2:
        eur_max_req = st.number_input("Nombre de requêtes maximum", min_value=1, max_value=100, value=5)
        eur_rows = st.number_input("Lignes par requête", min_value=1, max_value=100, value=10)
        eur_lang = st.selectbox("Langue de recherche", ["fr", "en", "de", "es", "it"], index=0)

    eur_query = st.text_area("Requête experte", value="DTS_SUBDOM=LEGISLATION", height=100)

    if st.button("Lancer l'extraction EUR-Lex", type="primary"):
        if not eur_username or not eur_password:
            st.warning("Veuillez renseigner vos identifiants EUR-Lex.")
        else:
            all_docs = []
            progress_bar = st.progress(0)
            status_text = st.empty()

            for i in range(eur_max_req):
                page = i + 1
                status_text.text(f"Requête {page}/{eur_max_req} en cours...")
                
                resp = soap_request_eurlex(eur_username, eur_password, eur_query, eur_lang, page, eur_rows)
                if resp is None:
                    break

                try:
                    root = ET.fromstring(resp.content)
                except ET.ParseError as e:
                    st.error(f"Erreur XML page {page}: {e}")
                    break

                docs = parse_documents_eurlex(root)
                if not docs:
                    status_text.text(f"Fin de pagination à la page {page}.")
                    break

                all_docs.extend(docs)
                progress_bar.progress((i + 1) / eur_max_req)
                time.sleep(1)

            if not all_docs:
                st.warning("Aucun document trouvé ou erreur de requête.")
            else:
                st.success(f"Extraction terminée : {len(all_docs)} documents récupérés.")
                df_eur = pd.DataFrame(all_docs)
                st.dataframe(df_eur)

                csv_eur = df_eur.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")
                json_eur = json.dumps(all_docs, ensure_ascii=False, indent=2).encode("utf-8")

                dl_col1, dl_col2 = st.columns(2)
                dl_col1.download_button("Télécharger CSV", data=csv_eur, file_name="eurlex_resultats.csv", mime="text/csv")
                dl_col2.download_button("Télécharger JSON", data=json_eur, file_name="eurlex_resultats.json", mime="application/json")


# --- ONGLET LÉGIFRANCE ---
with tab2:
    st.header("Extraction depuis Légifrance (API PISTE)")
    
    col3, col4 = st.columns(2)
    with col3:
        lf_client_id = st.text_input("Client ID Piste", key="lf_id")
        lf_client_secret = st.text_input("Client Secret Piste", type="password", key="lf_secret")
    with col4:
        lf_max_pages = st.number_input("Nombre de pages maximum", min_value=1, max_value=100, value=5)
        lf_page_size = st.number_input("Résultats par page", min_value=10, max_value=100, value=25)

    st.subheader("Critères de recherche")
    col5, col6 = st.columns(2)
    with col5:
        lf_fond = st.selectbox("Fonds", ["ALL", "KALI", "CNIL", "CONSTIT", "JURI", "LEGI"], index=0)
        lf_champ = st.selectbox("Champ de recherche", ["ALL", "TITLE", "NUM"], index=0)
        lf_valeur = st.text_input("Valeur recherchée")
        lf_operateur = st.selectbox("Opérateur", ["ET", "OU", "EXACTE"], index=0)
    with col6:
        lf_nor = st.text_input("Numéro NOR (optionnel)")
        lf_num = st.text_input("Numéro du texte (optionnel)")
        lf_sort = st.selectbox("Tri", ["PERTINENCE", "SIGNATURE_DATE_DESC", "SIGNATURE_DATE_ASC"], index=0)

    if st.button("Lancer l'extraction Légifrance", type="primary"):
        if not lf_client_id or not lf_client_secret:
            st.warning("Veuillez renseigner vos identifiants PISTE (Client ID / Secret).")
        else:
            auth = PisteAuth(lf_client_id, lf_client_secret)
            headers = auth.headers()
            
            if headers:
                all_docs_lf = []
                progress_bar_lf = st.progress(0)
                status_text_lf = st.empty()

                for page in range(1, lf_max_pages + 1):
                    status_text_lf.text(f"Requête page {page}/{lf_max_pages} en cours...")
                    
                    try:
                        resp = requests.post(
                            f"{API_BASE}/search",
                            headers=headers,
                            json=build_payload_legifrance(page, lf_page_size, lf_fond, lf_champ, lf_valeur, lf_operateur, lf_nor, lf_num, lf_sort),
                            timeout=30
                        )
                        resp.raise_for_status()
                    except Exception as e:
                        st.error(f"Erreur API : {e}")
                        break

                    data = resp.json()
                    results = data.get("results", [])
                    total = data.get("totalResultNumber", 0)

                    if not results:
                        status_text_lf.text(f"Fin de pagination à la page {page} (Total API : {total}).")
                        break

                    extracted = [extract_result_legifrance(r) for r in results]
                    all_docs_lf.extend(extracted)
                    progress_bar_lf.progress(page / lf_max_pages)

                    if len(all_docs_lf) >= total:
                        break
                    
                    time.sleep(0.5)

                if not all_docs_lf:
                    st.warning("Aucun document trouvé.")
                else:
                    st.success(f"Extraction terminée : {len(all_docs_lf)} documents récupérés.")
                    df_lf = pd.DataFrame(all_docs_lf)
                    st.dataframe(df_lf)

                    csv_lf = df_lf.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")
                    json_lf = json.dumps(all_docs_lf, ensure_ascii=False, indent=2).encode("utf-8")

                    dl_col3, dl_col4 = st.columns(2)
                    dl_col3.download_button("Télécharger CSV", data=csv_lf, file_name="legifrance_resultats.csv", mime="text/csv", key="dl_csv_lf")
                    dl_col4.download_button("Télécharger JSON", data=json_lf, file_name="legifrance_resultats.json", mime="application/json", key="dl_json_lf")