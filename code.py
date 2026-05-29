import streamlit as st
import requests
import pandas as pd
from xml.etree import ElementTree as ET
import time

# --- CONFIGURATION DE L'INTERFACE STREAMLIT ---
st.set_page_config(page_title="EUR-Lex Extractor Pro", page_icon="🇪🇺", layout="wide")

st.title("🇪🇺 Extracteur EUR-Lex Interactif")
st.markdown("Extraction totale des métadonnées avec affichage sur mesure.")

# --- DICTIONNAIRES DE CONFIGURATION ---
DOC_TYPES = {
    "Tous les types": None,
    "Directives": "DIR",
    "Règlements": "REG",
    "Décisions": "DEC",
    "Mesures Nationales d'Exécution (MNE)": "MNE",
    "Jurisprudence": "EU_CASE_LAW"
}

# Dictionnaire exhaustif : L'extracteur récupérera TOUT ça en arrière-plan
METADATA_FALLBACKS = {
    "CELEX (Identifiant)": ["ID_CELEX", "CELEX"],
    "Titre du document": ["EXPRESSION_TITLE", "TITLE", "TITLE_OF_DOCUMENT"],
    "Type de document": ["TYPE_OF_DOCUMENT", "FM_CODED", "ACT_TYPE"],
    "Auteur (Institution)": ["WORK_IS_CREATED_BY_AGENT", "AUTHOR", "CREATED_BY", "AGENT_NAME"], 
    "Pays concerné": ["NATIONAL_IMPLEMENTING_MEASURE_COUNTRY", "COUNTRY", "MEMBER_STATE"],
    "Date du document": ["WORK_DATE_DOCUMENT", "DATE_DOCUMENT", "DATE"],
    "Date de publication (JO)": ["DATE_PUBLICATION", "PUBLICATION_DATE"],
    "Date d'entrée en vigueur": ["DATE_ENTRY_INTO_FORCE", "ENTRY_INTO_FORCE_DATE"],
    "Date de fin de validité": ["DATE_END_OF_VALIDITY", "END_OF_VALIDITY_DATE"],
    "Base légale": ["LEGAL_BASIS", "TREATY", "BASE_LEGALE"],
    "Matière / Sujet": ["SUBJECT_MATTER", "SUBJECT"],
    "Descripteurs Eurovoc": ["EUROVOC", "EUROVOC_DESCRIPTOR"],
    "Numéro de procédure": ["PROCEDURE_NUMBER", "INTERINSTITUTIONAL_FILE_NUMBER"],
    "Numéro du document": ["DOC_NUM", "DOCUMENT_NUMBER"],
    "Langue authentique": ["AUTHENTIC_LANGUAGE", "LANGUAGE"],
    "Destinataire": ["ADDRESSEE"],
    "ECLI (Jurisprudence)": ["ECLI"]
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
        
        if doc_type in ["Directives", "Règlements", "Décisions", "Tous les types"]:
            query_parts.append("DTS_SUBDOM=LEGISLATION")
            if DOC_TYPES[doc_type]: 
                query_parts.append(f'FM_CODED={DOC_TYPES[doc_type]}')
                
        elif doc_type == "Mesures Nationales d'Exécution (MNE)":
            query_parts.append("DTS_SUBDOM=MNE")
            
        elif doc_type == "Jurisprudence":
            query_parts.append("DTS_SUBDOM=EU_CASE_LAW") 
            
        if txt_integral: query_parts.append(f'TE~"{txt_integral.strip()}"')
        if annee: query_parts.append(f'DD_YEAR={annee}')
            
        final_query = " AND ".join(query_parts)
        st.info(f"Requête générée : `{final_query}`")
    else:
        final_query = st.text_area("Collez votre formule experte ici :")

    st.header("📊 Filtres d'affichage")
    st.markdown("Colonnes à afficher dans le Tableau / Excel (Le JSON contiendra tout) :")
    
    # On définit les colonnes qui doivent être cochées dès l'ouverture de l'application
    colonnes_par_defaut = [
        "CELEX (Identifiant)", 
        "Titre du document", 
        "Date du document", 
        "Auteur (Institution)", 
        "Pays concerné"
    ]
    
    selected_metadata = []
    
    # On génère une case à cocher pour chaque métadonnée possible
    for label in METADATA_FALLBACKS.keys():
        # La case prend la valeur True (cochée) si elle fait partie de nos colonnes par défaut
        coche = st.checkbox(label, value=(label in colonnes_par_defaut))
        if coche:
            selected_metadata.append(label)
    
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

def get_xml_value(parent_node, tag_names):
    for tag in tag_names:
        for elem in parent_node.iter():
            if elem.tag.split('}')[-1] == tag:
                
                for child in elem.iter():
                    if child.tag.split('}')[-1] == 'IDENTIFIER' and child.text:
                        val = child.text.replace('AG//', '').replace('CT//', '').strip()
                        if val and not val.startswith("http"): 
                            return val
                            
                for child in elem.iter():
                    if child.tag.split('}')[-1] == 'VALUE' and child.text:
                        val = child.text.strip()
                        if val and not val.startswith("http"):
                            return val
                            
                raw_text = " ".join([t.strip() for t in elem.itertext() if t.strip()])
                clean_text = " ".join([word for word in raw_text.split() if not word.startswith("http")])
                
                if clean_text:
                    return clean_text
                    
    return "Non renseigné"

# --- BOUTONS DE CONTRÔLE ---
col1, col2 = st.columns(2)
start_btn = col1.button("🚀 Lancer l'extraction", type="primary")
stop_btn = col2.button("⏹️ Arrêter et sauvegarder", type="secondary")

if stop_btn:
    st.session_state.extraction_status = "Arrêtée"
    st.warning("⚠️ L'extraction a été interrompue. Les données récoltées ont été conservées.")

# --- ZONES D'AFFICHAGE FIXES ---
st.markdown("### 📥 Export et Tableau (En Haut)")
export_slot = st.empty() 
table_slot = st.empty()  

st.divider()

st.markdown("### ⚙️ Journal de progression")
progress_bar_slot = st.empty() 
status_text_slot = st.empty()  
log_container = st.container() 

st.divider()

st.markdown("### 📦 Données brutes complètes (En Bas)")
raw_data_slot = st.empty() 

# --- LOGIQUE D'EXTRACTION ---
if start_btn:
    safe_query = final_query.strip()
    
    if username == "XXXXXX" or not safe_query or not selected_metadata:
        st.error("⚠️ Identifiants manquants, requête vide ou métadonnées non sélectionnées.")
    else:
        st.session_state.documents = [] 
        st.session_state.extraction_status = "En cours"
        
        progress_bar = progress_bar_slot.progress(0)

        for i in range(max_requests):
            page = i + 1 
            status_text_slot.text(f"🔍 Requête {page}/{max_requests} en cours...")
            
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
                    
                    # 1. Extraction EXHAUSTIVE (On boucle sur le dictionnaire entier, pas juste sur la sélection)
                    for label, tags_to_search in METADATA_FALLBACKS.items():
                        doc_data[label] = get_xml_value(doc, tags_to_search)

                    # 2. Post-traitement MNE
                    celex = doc_data.get("CELEX (Identifiant)", "")
                    if celex.startswith("7") and "_" in celex:
                        code_pays = celex.split('_')[0][-3:]
                        if doc_data.get("Pays concerné") == "Non renseigné":
                            doc_data["Pays concerné"] = code_pays
                        if doc_data.get("Auteur (Institution)") == "Non renseigné":
                            doc_data["Auteur (Institution)"] = code_pays

                    # Ajout au cache complet
                    st.session_state.documents.append(doc_data)

                log_container.success(f"Page {page} : documents récupérés.")
                
                # Mise à jour en direct : on filtre le tableau avec [selected_metadata]
                if st.session_state.documents:
                    full_df = pd.DataFrame(st.session_state.documents)
                    table_slot.dataframe(full_df[selected_metadata]) # Tableau filtré
                    raw_data_slot.json(st.session_state.documents)   # JSON intégral
                
            except ET.ParseError:
                log_container.error(f"⚠️ Erreur de lecture XML à la page {page}.")
                break 

            progress_bar.progress((i + 1) / max_requests)
            time.sleep(delay)
            
        st.session_state.extraction_status = "Terminée"

# --- AFFICHAGE FINAL PERMANENT ---
if st.session_state.documents and st.session_state.extraction_status in ["Terminée", "Arrêtée"]:
    # Création du DataFrame complet puis filtré
    full_df = pd.DataFrame(st.session_state.documents)
    filtered_df = full_df[selected_metadata]
    
    with export_slot.container():
        st.success(f"🎉 {len(st.session_state.documents)} documents récupérés avec succès !")
        # L'export CSV ne contient que les colonnes choisies par l'utilisateur
        csv_data = filtered_df.to_csv(index=False, sep=';').encode('utf-8-sig')
        st.download_button(
            label="📥 Télécharger le fichier compatible Excel",
            data=csv_data,
            file_name="eurlex_donnees.csv",
            mime="text/csv",
            type="primary"
        )
        
    # Affichage filtré en haut, JSON intégral en bas
    table_slot.dataframe(filtered_df)
    raw_data_slot.json(st.session_state.documents)