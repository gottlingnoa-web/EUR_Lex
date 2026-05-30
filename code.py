import streamlit as st
import requests
import pandas as pd
from xml.etree import ElementTree as ET
import time
import json

# --- CONFIGURATION DE L'INTERFACE STREAMLIT ---
st.set_page_config(page_title="Extracteur Juridique Pro", page_icon="⚖️", layout="wide")

st.title("⚖️ Extracteur Juridique Interactif")
st.markdown("Extraction totale des métadonnées avec affichage sur mesure pour EUR-Lex et Légifrance.")

# ==========================================
# FONCTIONS COMMUNES / EUR-LEX
# ==========================================
URL_EURLEX = "https://eur-lex.europa.eu/EURLexWebService"

def send_soap_request(page, safe_query, user, pwd, rows_per_req, log_container):
    soap_query = f"""<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" xmlns:sear="http://eur-lex.europa.eu/search">
   <soap:Header>
      <wsse:Security soap:mustUnderstand="true" xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">
         <wsse:UsernameToken wsu:Id="UsernameToken-1" xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">
            <wsse:Username>{user}</wsse:Username>
            <wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordText">{pwd}</wsse:Password>
         </wsse:UsernameToken>
      </wsse:Security>
   </soap:Header>
   <soap:Body>
        <sear:searchRequest>
            <sear:expertQuery><![CDATA[{safe_query}]]></sear:expertQuery>
            <sear:page>{page}</sear:page>
            <sear:pageSize>{rows_per_req}</sear:pageSize>
            <sear:searchLanguage>fr</sear:searchLanguage>
        </sear:searchRequest>
   </soap:Body>
</soap:Envelope>"""

    headers = {'Content-Type': 'application/soap+xml; charset=utf-8'}
    try:
        response = requests.post(URL_EURLEX, data=soap_query.encode('utf-8'), headers=headers, timeout=60)
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
                if clean_text: return clean_text
    return "Non renseigné"

# --- CREATION DES ONGLETS ---
tab_eurlex, tab_legifrance = st.tabs(["🇪🇺 EUR-Lex", "🇫🇷 Légifrance"])

# ==========================================
# ONGLET 1 : EUR-LEX
# ==========================================
with tab_eurlex:
    st.header("Extraction depuis EUR-Lex")
    
    DOC_TYPES = {
        "Tous les types": None,
        "Directives": "DIR",
        "Règlements": "REG",
        "Décisions": "DEC",
        "Mesures Nationales d'Exécution (MNE)": "MNE",
        "Jurisprudence": "EU_CASE_LAW"
    }

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

    if 'documents_eurlex' not in st.session_state:
        st.session_state.documents_eurlex = []

    col_el1, col_el2 = st.columns(2)
    
    with col_el1:
        st.subheader("🔑 Identifiants SOAP")
        username_el = st.text_input("Nom d'utilisateur EUR-Lex", value="")
        password_el = st.text_input("Mot de passe EUR-Lex", value="", type="password")
        
        st.subheader("⏱️ Pagination & Limites")
        rows_per_request = st.number_input("Documents par requête", min_value=1, max_value=100, value=10)
        max_requests = st.number_input("Nombre de requêtes max", min_value=1, max_value=2000, value=2)
        
    with col_el2:
        st.subheader("🔍 Critères de recherche")
        txt_integral = st.text_input("Mots dans le texte intégral :")
        doc_type = st.selectbox("Type d'acte :", list(DOC_TYPES.keys()))
        annee = st.text_input("Année (ex: 2023) :", max_chars=4)
        
        st.subheader("📊 Filtres (Tableau)")
        selected_metadata = st.multiselect(
            "Colonnes à afficher :",
            options=list(METADATA_FALLBACKS.keys()),
            default=["CELEX (Identifiant)", "Titre du document", "Date du document"]
        )

    # --- GENERATION REQUETE EUR-LEX ---
    query_parts = []
    if doc_type in ["Directives", "Règlements", "Décisions", "Tous les types"]:
        query_parts.append("DTS_SUBDOM=LEGISLATION")
        if DOC_TYPES[doc_type]: query_parts.append(f'FM_CODED={DOC_TYPES[doc_type]}')
    elif doc_type == "Mesures Nationales d'Exécution (MNE)":
        query_parts.append("DTS_SUBDOM=MNE")
    elif doc_type == "Jurisprudence":
        query_parts.append("DTS_SUBDOM=EU_CASE_LAW") 
        
    if txt_integral: query_parts.append(f'TE~"{txt_integral.strip()}"')
    if annee: query_parts.append(f'DD_YEAR={annee}')
        
    final_query = " AND ".join(query_parts)
    st.info(f"Requête générée : `{final_query}`")

    # --- ZONES D'AFFICHAGE EUR-LEX ---
    start_btn_el = st.button("🚀 Lancer l'extraction EUR-Lex", type="primary")
    
    export_slot_el = st.empty() 
    table_slot_el = st.empty()  
    st.divider()
    progress_bar_slot = st.empty() 
    status_text_slot = st.empty()  
    log_container = st.container() 
    st.divider()
    raw_data_slot_el = st.empty()

    if start_btn_el:
        safe_query = final_query.strip()
        
        if not username_el or not password_el or not safe_query or not selected_metadata:
            st.error("⚠️ Identifiants manquants, requête vide ou métadonnées non sélectionnées.")
        else:
            st.session_state.documents_eurlex = [] 
            progress_bar = progress_bar_slot.progress(0)

            for i in range(max_requests):
                page = i + 1 
                status_text_slot.text(f"🔍 Requête {page}/{max_requests} en cours...")
                
                response = send_soap_request(page, safe_query, username_el, password_el, rows_per_request, log_container)
                
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
                        for label, tags_to_search in METADATA_FALLBACKS.items():
                            doc_data[label] = get_xml_value(doc, tags_to_search)

                        st.session_state.documents_eurlex.append(doc_data)

                    log_container.success(f"Page {page} : documents récupérés.")
                    
                    if st.session_state.documents_eurlex:
                        full_df = pd.DataFrame(st.session_state.documents_eurlex)
                        table_slot_el.dataframe(full_df[selected_metadata]) 
                    
                except ET.ParseError:
                    log_container.error(f"⚠️ Erreur de lecture XML à la page {page}.")
                    break 

                progress_bar.progress((i + 1) / max_requests)
                time.sleep(1) # Petit délai pour éviter de surcharger
                
            status_text_slot.text("✅ Extraction terminée.")

    # Affichage permanent si données en cache
    if st.session_state.documents_eurlex:
        full_df = pd.DataFrame(st.session_state.documents_eurlex)
        # Gestion d'erreur si la sélection des colonnes change après l'extraction
        cols_to_show = [c for c in selected_metadata if c in full_df.columns] 
        filtered_df = full_df[cols_to_show] if cols_to_show else full_df
        
        with export_slot_el.container():
            st.success(f"🎉 {len(st.session_state.documents_eurlex)} documents récupérés !")
            csv_data = filtered_df.to_csv(index=False, sep=';').encode('utf-8-sig')
            st.download_button(
                label="📥 Télécharger les données EUR-Lex (CSV)",
                data=csv_data,
                file_name="eurlex_donnees.csv",
                mime="text/csv",
                type="primary",
                key="btn_dl_eurlex"
            )
            
        table_slot_el.dataframe(filtered_df)
        with raw_data_slot_el.expander("Voir le JSON brut (Toutes les métadonnées)"):
            st.json(st.session_state.documents_eurlex)

# ==========================================
# ONGLET 2 : LÉGIFRANCE (Corrigé)
# ==========================================
with tab_legifrance:
    st.header("Extraction depuis Légifrance")
    st.markdown("Utilise l'API REST de la plateforme PISTE (OAuth2).")

    if 'documents_legifrance' not in st.session_state:
        st.session_state.documents_legifrance = []

    col_lf1, col_lf2 = st.columns(2)

    with col_lf1:
        st.subheader("🔑 Identifiants API PISTE")
        client_id = st.text_input("Client ID", placeholder="Votre Client ID PISTE")
        client_secret = st.text_input("Client Secret", placeholder="Votre Client Secret PISTE", type="password")

    with col_lf2:
        st.subheader("🔍 Recherche Légifrance")
        recherche_lf = st.text_input("Mots-clés (Texte intégral) :")
        fonds_lf = st.selectbox("Fonds de données :", ["ALL", "CODE_ET_LOI", "JURI", "CNIL", "CONSTIT"])
        limite_resultats = st.number_input("Nombre de résultats max", min_value=10, max_value=100, value=20)

    # --- LOGIQUE D'EXTRACTION LÉGIFRANCE ---
    if st.button("🚀 Lancer l'extraction Légifrance", type="primary"):
        if not client_id or not client_secret:
            st.error("⚠️ Veuillez entrer vos identifiants PISTE (Client ID et Secret).")
        elif not recherche_lf:
            st.warning("⚠️ Veuillez entrer un mot-clé de recherche.")
        else:
            with st.spinner("Authentification auprès de PISTE en cours..."):
                token_url = "https://oauth.piste.gouv.fr/api/oauth/token"
                data = {
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": "openid"
                }
                
                try:
                    token_req = requests.post(token_url, data=data, timeout=10)
                    token_req.raise_for_status()
                    access_token = token_req.json().get("access_token")
                    st.success("✅ Authentification réussie !")
                    
                    search_url = "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app/search"
                    headers = {
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/json",
                        "Content-Type": "application/json"
                    }
                    
                    payload = {
                        "recherche": {
                            "champs": [
                                {
                                    "typeChamp": "ALL",
                                    "criteres": [
                                        {"valeur": recherche_lf, "operateur": "ET"}
                                    ]
                                }
                            ]
                        },
                        "fond": fonds_lf,
                        "pageNumber": 1,
                        "pageSize": limite_resultats,
                        "sort": "SIGNATURE_DATE_DESC"
                    }

                    with st.spinner("Recherche des documents en cours..."):
                        search_req = requests.post(search_url, headers=headers, json=payload, timeout=30)
                        search_req.raise_for_status()
                        
                        resultats = search_req.json().get("results", [])
                        
                        if not resultats:
                            st.info("Aucun document trouvé pour cette recherche.")
                        else:
                            donnees_extraites = []
                            for res in resultats:
                                donnees_extraites.append({
                                    "Identifiant / CID": res.get("cid", "N/A"),
                                    "Titre": res.get("title", "N/A"),
                                    "Fonds": res.get("fond", "N/A"),
                                    "Date de publication": res.get("publicationDate", "N/A"),
                                    "Date de signature": res.get("signatureDate", "N/A")
                                })
                            
                            st.session_state.documents_legifrance = donnees_extraites

                except requests.exceptions.HTTPError as e:
                    st.error(f"❌ Erreur API : {e.response.status_code} - {e.response.text}")
                except Exception as e:
                    st.error(f"❌ Erreur inattendue : {e}")

    # Affichage permanent si données en cache
    if st.session_state.documents_legifrance:
        df_lf = pd.DataFrame(st.session_state.documents_legifrance)
        st.dataframe(df_lf, use_container_width=True)
        
        csv_lf = df_lf.to_csv(index=False, sep=';').encode('utf-8-sig')
        st.download_button(
            label="📥 Télécharger les données Légifrance (CSV)",
            data=csv_lf,
            file_name="legifrance_donnees.csv",
            mime="text/csv",
            type="primary",
            key="btn_dl_legifrance"
        )
        
        with st.expander("Voir le JSON brut retourné par l'API"):
            st.json(st.session_state.documents_legifrance)