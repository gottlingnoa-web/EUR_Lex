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

# Création des onglets principaux
tab_eurlex, tab_legifrance = st.tabs(["🇪🇺 EUR-Lex", "🇫🇷 Légifrance"])

# ==========================================
# ONGLET 1 : EUR-LEX (Votre code existant adapté)
# ==========================================
with tab_eurlex:
    st.header("Extraction depuis EUR-Lex")
    
    # --- DICTIONNAIRES DE CONFIGURATION EUR-LEX ---
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
        "Date du document": ["WORK_DATE_DOCUMENT", "DATE_DOCUMENT", "DATE"],
        "Matière / Sujet": ["SUBJECT_MATTER", "SUBJECT"],
    } # Raccourci pour l'exemple, gardez votre dictionnaire complet ici

    if 'documents_eurlex' not in st.session_state:
        st.session_state.documents_eurlex = []

    # On utilise des colonnes pour organiser les paramètres EUR-Lex
    col_param1, col_param2 = st.columns(2)
    
    with col_param1:
        st.subheader("🔑 Identifiants SOAP")
        username = st.text_input("Nom d'utilisateur EUR-Lex", value="XXXXXX")
        password = st.text_input("Mot de passe EUR-Lex", value="XXXXXX", type="password")
        
    with col_param2:
        st.subheader("🔍 Critères de recherche")
        txt_integral = st.text_input("Mots dans le texte intégral :")
        doc_type = st.selectbox("Type d'acte :", list(DOC_TYPES.keys()))
        annee = st.text_input("Année (ex: 2023) :", max_chars=4)

    # Bouton d'action EUR-Lex
    if st.button("🚀 Lancer l'extraction EUR-Lex", type="primary"):
        st.info("Logique d'extraction SOAP EUR-Lex à insérer ici (votre code `send_soap_request`).")
        # Insérez ici votre boucle for i in range(max_requests): ...

# ==========================================
# ONGLET 2 : LÉGIFRANCE (Nouvelle API PISTE)
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
                # 1. Obtenir le token OAuth2
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
                    
                    # 2. Requête vers le moteur de recherche Légifrance
                    search_url = "https://api.piste.gouv.fr/dila/legifrance/lf/engine/api/search"
                    headers = {
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/json",
                        "Content-Type": "application/json"
                    }
                    
                    # Payload officiel de l'API de recherche Légifrance
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
                        "sort": "SIGNATURE_DATE_DESC" # Tri par date de signature
                    }

                    with st.spinner("Recherche des documents en cours..."):
                        search_req = requests.post(search_url, headers=headers, json=payload, timeout=30)
                        search_req.raise_for_status()
                        
                        resultats = search_req.json().get("results", [])
                        
                        if not resultats:
                            st.info("Aucun document trouvé pour cette recherche.")
                        else:
                            # Extraction simplifiée des données Légifrance
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
                            
                            # Affichage
                            df_lf = pd.DataFrame(donnees_extraites)
                            st.dataframe(df_lf, use_container_width=True)
                            
                            # Export CSV
                            csv_lf = df_lf.to_csv(index=False, sep=';').encode('utf-8-sig')
                            st.download_button(
                                label="📥 Télécharger les données Légifrance (CSV)",
                                data=csv_lf,
                                file_name="legifrance_donnees.csv",
                                mime="text/csv",
                                type="secondary"
                            )
                            
                            # JSON brut
                            with st.expander("Voir le JSON brut retourné par l'API"):
                                st.json(resultats)

                except requests.exceptions.HTTPError as e:
                    st.error(f"❌ Erreur API : {e.response.status_code} - {e.response.text}")
                except Exception as e:
                    st.error(f"❌ Erreur inattendue : {e}")