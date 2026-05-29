import streamlit as st
import requests
import pandas as pd
from xml.etree import ElementTree as ET
import time

# --- CONFIGURATION DE L'INTERFACE STREAMLIT ---
st.set_page_config(page_title="EUR-Lex Extractor Pro", page_icon="🇪🇺", layout="wide")

st.title("🇪🇺 Extracteur EUR-Lex Interactif")
st.markdown("Extraction sécurisée avec lecture XML profonde (Deep Parse).")

# --- DICTIONNAIRES DE CONFIGURATION ---
DOC_TYPES = {
    "Tous les types": None,
    "Directives": "DIR",
    "Règlements": "REG",
    "Décisions": "DEC",
    "Mesures Nationales d'Exécution (MNE)": "MNE",
    "Jurisprudence": "EU_CASE_LAW"
}

# On ajoute les vraies étiquettes XML renvoyées par le serveur (comme WORK_DATE_DOCUMENT)
METADATA_FALLBACKS = {
    "CELEX (Identifiant)": ["ID_CELEX", "CELEX"],
    "Titre du document": ["EXPRESSION_TITLE", "TITLE", "TITLE_OF_DOCUMENT"],
    "Date du document": ["WORK_DATE_DOCUMENT", "DATE_DOCUMENT", "DATE"], # <- Correction ici
    "Type de document": ["TYPE_OF_DOCUMENT", "FM_CODED", "ACT_TYPE"],
    "Auteur (Institution)": ["WORK_IS_CREATED_BY_AGENT", "AUTHOR"],
    "Pays concerné": ["NATIONAL_IMPLEMENTING_MEASURE_COUNTRY", "COUNTRY"], # <- Correction ici
    "Numéro du document": ["DOC_NUM", "DOCUMENT_NUMBER"],
    "Date de publication (JO)": ["DATE_PUBLICATION", "PUBLICATION_DATE"]
}

# --- INITIALISATION DE LA MÉMOIRE (SESSION STATE) ---
if 'documents' not in st.session_state:
    st.session_state.documents = []
if 'extraction_status' not in st.session_state:
    st.session_state.extraction_status = "En attente"

# --- BARRE LATÉRALE : PARAMÈTRES ---
with st.sidebar:
    st.header("🔑 Identifiants")
    username = st.text_input("Nom d'utilisateur", value="XXXXXX")
    password = st.text_input("Mot de passe", value="XXXXXX", type="password")
    
    st.header("🔍 Critères de recherche")
    search_mode = st.radio("Mode :", ["Générateur (Facile)", "Requête Experte"])
    
    final_query = ""
    if search_mode == "Générateur (Facile)":
        txt_integral = st.text_input("Mots dans le texte intégral :")
        doc_type = st.selectbox("Type d'acte :", list(DOC_TYPES.keys()))
        annee = st.text_input("Année (ex: 2023) :", max_chars=4)
        
        query_parts = []
        
        # --- LE CORRECTIF EST ICI : On change de tiroir selon le type de document ---
        if doc_type in ["Directives", "Règlements", "Décisions", "Tous les types"]:
            query_parts.append("DTS_SUBDOM=LEGISLATION")
            if DOC_TYPES[doc_type]: 
                query_parts.append(f'FM_CODED={DOC_TYPES[doc_type]}')
                
        elif doc_type == "Mesures Nationales d'Exécution (MNE)":
            query_parts.append("DTS_SUBDOM=MNE") # Tiroir des lois nationales
            
        elif doc_type == "Jurisprudence":
            query_parts.append("DTS_SUBDOM=EU_CASE_LAW") # Tiroir des tribunaux
            
        # On ajoute les mots-clés et l'année s'ils sont remplis
        if txt_integral: query_parts.append(f'TE~"{txt_integral.strip()}"')
        if annee: query_parts.append(f'DD_YEAR={annee}')
            
        final_query = " AND ".join(query_parts)
        st.info(f"Requête générée : `{final_query}`")

    st.header("📊 Métadonnées à extraire")
    selected_metadata = st.multiselect(
        "Colonnes du futur fichier :",
        list(METADATA_FALLBACKS.keys()),
        # On met à jour les choix par défaut ici :
        default=["CELEX (Identifiant)", "Titre du document", "Date du document", "Auteur (Institution)", "Pays concerné"] 
    )
    
    st.header("⏱️ Pagination & Limites")
    rows_per_request = st.number_input("Documents par requête", min_value=1, max_value=100, value=10)
    max_requests = st.number_input("Nombre de requêtes maximum", min_value=1, max_value=2000, value=5)
    delay = st.slider("Délai (secondes)", min_value=0, max_value=15, value=0)

URL = "https://eur-lex.europa.eu/EURLexWebService"

def send_soap_request(page, safe_query, log_container):
    soap_query = f"""<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" xmlns:sear="http://eur-lex.europa.eu/search">
   <soap:Header>
      <wsse:Security soap:mustUnderstand="true" xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">
         <wsse:UsernameToken wsu:Id="UsernameToken-1" xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">
            <wsse:Username>{username}</wsse:Username>
            <wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordText">{password}</wsse:Password>
         </wsse:UsernameToken>
      </wsse:Security>
   </soap:Header>
   <soap:Body>
        <sear:searchRequest>
            <sear:expertQuery><![CDATA[{safe_query}]]></sear:expertQuery>
            <sear:page>{page}</sear:page>
            <sear:pageSize>{rows_per_request}</sear:pageSize>
            <sear:searchLanguage>fr</sear:searchLanguage>
        </sear:searchRequest>
   </soap:Body>
</soap:Envelope>"""

    headers = {'Content-Type': 'application/soap+xml; charset=utf-8'}
    try:
        response = requests.post(URL, data=soap_query.encode('utf-8'), headers=headers, timeout=60)
        return response
    except requests.exceptions.RequestException as e:
        log_container.error(f"⚠️ Erreur de connexion : {e}")
        return None

# NOUVELLE FONCTION XML INTELLIGENTE : Cible précisément la bonne donnée
def get_xml_value(parent_node, tag_names):
    for tag in tag_names:
        for elem in parent_node.iter():
            if elem.tag.split('}')[-1] == tag:
                
                # Stratégie 1 : Chercher une sous-balise <VALUE> (Idéal pour Dates et Titres propres)
                for child in elem.iter():
                    if child.tag.split('}')[-1] == 'VALUE' and child.text:
                        return child.text.strip()
                        
                # Stratégie 2 : Chercher une sous-balise <IDENTIFIER> (Idéal pour Auteurs et Pays)
                for child in elem.iter():
                    if child.tag.split('}')[-1] == 'IDENTIFIER' and child.text:
                        # Nettoyage des préfixes internes d'EUR-Lex (ex: "AG//COM" devient "COM")
                        return child.text.replace('AG//', '').replace('CT//', '').strip()

                # Stratégie 3 : Prendre le texte direct s'il y en a un
                if elem.text and elem.text.strip():
                    return elem.text.strip()
                    
    return "Non renseigné"

# --- CONTRÔLES PRINCIPAUX ---
col1, col2 = st.columns(2)
start_btn = col1.button("🚀 Lancer l'extraction", type="primary")
stop_btn = col2.button("⏹️ Arrêter et sauvegarder", type="secondary")

# Gestion de l'interruption
if stop_btn:
    st.session_state.extraction_status = "Arrêtée"
    st.warning("⚠️ L'extraction a été interrompue. Les données récoltées ont été conservées.")

# Lancement de l'extraction
if start_btn:
    safe_query = final_query.strip()
    
    if username == "XXXXXX" or not safe_query or not selected_metadata:
        st.error("⚠️ Identifiants manquants, requête vide ou métadonnées non sélectionnées.")
    else:
        st.session_state.documents = [] 
        st.session_state.extraction_status = "En cours"
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        log_container = st.container()

        for i in range(max_requests):
            page = i + 1 
            status_text.text(f"🔍 Requête {page}/{max_requests} en cours...")
            
            response = send_soap_request(page, safe_query, log_container)
            
            if response is None or response.status_code != 200:
                log_container.error(f"❌ Échec de la requête (HTTP {response.status_code if response else 'Inconnu'}).")
                break 

            try:
                root = ET.fromstring(response.content)
                docs = []
                for elem in root.iter():
                    if elem.tag.split('}')[-1] in ['document', 'result']:
                        docs.append(elem)
                
                if not docs:
                    log_container.info(f"✅ Fin de la pagination atteinte à la page {page}.")
                    break

                for doc in docs:
                    doc_data = {}
                    
                    # Remplissage dynamique des colonnes via notre nouvelle fonction
                    for label in selected_metadata:
                        tags_to_search = METADATA_FALLBACKS[label]
                        doc_data[label] = get_xml_value(doc, tags_to_search)

                    # Ajout au cache
                    st.session_state.documents.append(doc_data)

                log_container.success(f"Page {page} : documents récupérés.")
                
            except ET.ParseError:
                log_container.error(f"⚠️ Erreur de lecture XML à la page {page}.")
                break 

            progress_bar.progress((i + 1) / max_requests)
            time.sleep(delay)
            
        st.session_state.extraction_status = "Terminée"

# --- AFFICHAGE ET EXPORT SANS DÉPENDANCES SUPPLÉMENTAIRES ---
if st.session_state.documents and st.session_state.extraction_status in ["Terminée", "Arrêtée"]:
    st.success(f"🎉 {len(st.session_state.documents)} documents récupérés avec succès !")
    
    df = pd.DataFrame(st.session_state.documents)
    st.dataframe(df)
    
    # Export en CSV optimisé pour Excel (utf-8-sig + séparateur ;)
    # Ne plante jamais, même sur des serveurs légers.
    csv_data = df.to_csv(index=False, sep=';').encode('utf-8-sig')
    
    st.download_button(
        label="📥 Télécharger le fichier compatible Excel",
        data=csv_data,
        file_name="eurlex_donnees.csv",
        mime="text/csv",
        type="primary"
    )
elif st.session_state.extraction_status == "Terminée" and not st.session_state.documents:
    st.warning("Aucun résultat trouvé pour cette recherche.")