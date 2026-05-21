import streamlit as st
import requests
import pandas as pd
from xml.etree import ElementTree as ET
import time
import io

# --- CONFIGURATION DE L'INTERFACE STREAMLIT ---
st.set_page_config(page_title="EUR-Lex Extractor", page_icon="🇪🇺", layout="wide")

st.title("🇪🇺 Extracteur de Documents EUR-Lex")
st.markdown("Interface d'extraction respectant le standard WS-Security d'EUR-Lex.")

# --- BARRE LATÉRALE : PARAMÈTRES ---
with st.sidebar:
    st.header("🔑 Identifiants")
    username = st.text_input("Nom d'utilisateur", value="XXXXXX")
    password = st.text_input("Mot de passe", value="XXXXXX", type="password")
    
    st.header("⚙️ Paramètres de recherche")
    query = st.text_input("Requête (Filtre)", value="DTS_SUBDOM:MNE AND YEAR:[2010 TO 2025]")
    metadata = st.text_input("Métadonnées (séparées par des virgules)", value="CELEX, TITLE, COUNTRY")
    
    st.header("⏱️ Pagination & Limites")
    rows_per_request = st.number_input("Documents par requête", min_value=1, max_value=100, value=5)
    max_requests = st.number_input("Nombre de requêtes maximum", min_value=1, max_value=2000, value=1000)
    delay = st.slider("Délai entre requêtes (secondes)", min_value=0, max_value=15, value=5)

URL = "https://eur-lex.europa.eu/EURLexWebService"

# --- FONCTION POUR ENVOYER UNE REQUÊTE SOAP VALIDE ---
def send_soap_request(page, log_container):
    # Pour récupérer les métadonnées spécifiques sur EUR-Lex, la syntaxe exige un "SELECT ... WHERE ..."
    full_expert_query = query
    
    # Enveloppe SOAP stricte respectant WS-Security et le format de recherche EUR-Lex
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
            <sear:expertQuery><![CDATA[{full_expert_query}]]></sear:expertQuery>
            <sear:page>{page}</sear:page>
            <sear:pageSize>{rows_per_request}</sear:pageSize>
            <sear:searchLanguage>fr</sear:searchLanguage>
            <sear:searchProfile>STANDARD</sear:searchProfile> 
        </sear:searchRequest>
   </soap:Body>
</soap:Envelope>"""

    # L'API SOAP 1.2 exige un Content-Type 'application/soap+xml'
    headers = {
        'Content-Type': 'application/soap+xml; charset=utf-8'
    }

    try:
        # Note : On retire HTTPBasicAuth() car l'authentification est désormais dans le Header XML
        response = requests.post(URL, data=soap_query.encode('utf-8'), headers=headers, timeout=60)
        return response
    except requests.exceptions.RequestException as e:
        log_container.error(f"⚠️ Erreur de connexion au serveur : {e}")
        return None

# --- BOUTON DE LANCEMENT ---
if st.button("🚀 Lancer l'extraction", type="primary"):
    if username == "XXXXXX" or password == "XXXXXX" or not username or not password:
        st.warning("⚠️ Veuillez entrer vos identifiants EUR-Lex valides dans la barre latérale.")
    else:
        all_documents = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        log_container = st.container()

        # Boucle de requêtes (EUR-Lex utilise des numéros de pages, pas des index de départ)
        for i in range(max_requests):
            page = i + 1 
            status_text.text(f"🔍 Requête {page}/{max_requests} en cours...")
            
            response = send_soap_request(page, log_container)
            
            if response is None:
                break # Erreur réseau, on arrête la boucle
                
            # Vérification rigoureuse de la réponse HTTP
            if response.status_code != 200:
                log_container.error(f"❌ Échec critique. EUR-Lex a renvoyé l'erreur HTTP {response.status_code}.")
                with log_container.expander("Voir le contenu renvoyé par EUR-Lex (pour débogage)"):
                    st.code(response.text[:2000])
                break # On arrête immédiatement pour ne pas générer 100 fois la même erreur

            try:
                # Parsing XML
                root = ET.fromstring(response.content)
                
                # Recherche des balises de documents 
                documents = root.findall('.//document') or root.findall('.//*[local-name()="document"]') or root.findall('.//*[local-name()="result"]')
                
                if not documents:
                    log_container.warning(f"⚠️ Fin de la pagination atteinte à la page {page} ou aucun document trouvé.")
                    break

                # 💡 AJOUT CRUCIAL : Afficher la structure du premier document lors de la première requête
                if i == 0 and len(documents) > 0:
                    with log_container.expander("🔍 Voir le XML brut du premier document (pour trouver les bons noms de balises)"):
                        # Convertir l'élément XML en chaîne lisible
                        xml_str = ET.tostring(documents[0], encoding='unicode')
                        st.code(xml_str, language='xml')

                for doc in documents:
                    # 💡 MODIFICATION : Recherche plus large incluant les standards EUR-Lex habituels
                    # ID_CELEX est le nom standard dans l'ontologie EUR-Lex
                    celex = doc.find('.//*[local-name()="ID_CELEX"]') 
                    if celex is None: 
                        celex = doc.find('.//*[local-name()="CELEX"]')

                    # Le titre est souvent imbriqué dans VALUE à l'intérieur de EXPRESSION_TITLE
                    title_node = doc.find('.//*[local-name()="EXPRESSION_TITLE"]//*[local-name()="VALUE"]')
                    if title_node is None:
                        title_node = doc.find('.//*[local-name()="TITLE"]')
                        
                    # Pays ou auteur (souvent WORK_IS_CREATED_BY_AGENT)
                    country_node = doc.find('.//*[local-name()="COUNTRY"]') 

                    all_documents.append({
                        'CELEX': celex.text if celex is not None else 'N/A',
                        'Titre': title_node.text if title_node is not None else 'N/A',
                        'Pays': country_node.text if country_node is not None else 'N/A'
                    })

                log_container.success(f"✅ Page {page} : documents récupérés.")
                
            except ET.ParseError as e:
                log_container.error(f"⚠️ EUR-Lex n'a pas renvoyé de XML valide à la page {page}.")
                with log_container.expander("Voir ce qu'EUR-Lex a réellement renvoyé (HTML/Erreur)"):
                    st.code(response.text[:2000])
                break 

            progress_bar.progress((i + 1) / max_requests)

            if i < max_requests - 1:
                time.sleep(delay)

        # --- EXPORT ---
        status_text.text("✨ Processus terminé !")
        
        if all_documents:
            st.success(f"🎉 Succès ! {len(all_documents)} documents récupérés au total.")
            
            df = pd.DataFrame(all_documents)
            st.dataframe(df.head(10))
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='EURLex_Data')
            processed_data = output.getvalue()
            
            st.download_button(
                label="📥 Télécharger les résultats en Excel",
                data=processed_data,
                file_name=f"eurlex_resultats.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.error("❌ Aucune donnée n'a été récupérée. Vérifiez votre requête ou vos droits d'accès au WebService.")