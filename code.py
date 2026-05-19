import streamlit as st
import requests
from requests.auth import HTTPBasicAuth
import pandas as pd
from xml.etree import ElementTree as ET
import time
import io

# --- CONFIGURATION DE L'INTERFACE STREAMLIT ---
st.set_page_config(page_title="EUR-Lex Extractor", page_icon="🇪🇺", layout="wide")

st.title("🇪🇺 Extracteur de Documents EUR-Lex")
st.markdown("Interface d'extraction des métadonnées du webservice SOAP d'EUR-Lex.")

# --- BARRE LATÉRALE : PARAMÈTRES ---
with st.sidebar:
    st.header("🔑 Identifiants")
    username = st.text_input("Nom d'utilisateur", value="XXXXXX")
    password = st.text_input("Mot de passe", value="XXXXXX", type="password")
    
    st.header("⚙️ Paramètres de recherche")
    query = st.text_input("Requête (Filtre)", value="DTS_SUBDOM:MNE AND YEAR:[2010 TO 2025]")
    metadata = st.text_input("Métadonnées (séparées par des virgules)", value="CELEX,TITLE,COUNTRY")
    
    st.header("⏱️ Pagination & Limites")
    rows_per_request = st.number_input("Documents par requête", min_value=1, max_value=100, value=5)
    max_requests = st.number_input("Nombre de requêtes", min_value=1, max_value=2000, value=1000)
    delay = st.slider("Délai entre requêtes (secondes)", min_value=0, max_value=15, value=5)

URL = "https://eur-lex.europa.eu/EURLexWebService"

# --- FONCTION POUR ENVOYER UNE REQUÊTE SOAP ---
def send_soap_request(start, log_container, retry_count=0):
    soap_query = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope
   xmlns:soapenv="http://www.w3.org/2003/05/soap-envelope"
   xmlns:eur="http://eur-lex.europa.eu/">
   <soapenv:Header/>
   <soapenv:Body>
      <eur:searchRequest>
         <eur:query>{query}</eur:query>
         <eur:metadata>{metadata}</eur:metadata>
         <eur:start>{start}</eur:start>
         <eur:rows>{rows_per_request}</eur:rows>
      </eur:searchRequest>
   </soapenv:Body>
</soapenv:Envelope>"""

    headers = {
        'Content-Type': 'text/xml; charset=utf-8',
        'SOAPAction': '',
        'Accept': 'text/xml'
    }

    try:
        response = requests.post(
            URL,
            data=soap_query.encode('utf-8'),
            headers=headers,
            auth=HTTPBasicAuth(username, password),
            timeout=60
        )

        if response.status_code == 200:
            return response.content
        elif response.status_code == 415:
            log_container.error(f"⚠️ Erreur 415 (Unsupported Media Type) pour la requête {start}.")
            return None
        elif response.status_code == 202 and retry_count < 3:
            log_container.warning(f"⏳ Requête {start} : 202 Accepted. Réessai {retry_count + 1}/3 dans 10 secondes...")
            time.sleep(10)
            return send_soap_request(start, log_container, retry_count + 1)
        else:
            log_container.error(f"⚠️ Erreur HTTP {response.status_code} pour la requête {start}.")
            return None

    except requests.exceptions.RequestException as e:
        log_container.error(f"⚠️ Erreur de connexion pour la requête {start}: {e}")
        return None

# --- BOUTON DE LANCEMENT ---
if st.button("🚀 Lancer l'extraction", type="primary"):
    if username == "XXXXXX" or password == "XXXXXX" or not username or not password:
        st.warning("⚠️ Veuillez entrer vos identifiants EUR-Lex valides dans la barre latérale avant de lancer l'extraction.")
    else:
        all_documents = []
        
        # Éléments d'interface pour le suivi
        progress_bar = st.progress(0)
        status_text = st.empty()
        log_container = st.container()
        
        # Estimation du temps
        estimated_time = max_requests * delay
        st.info(f"Temps estimé pour {max_requests} requêtes : ~{estimated_time // 60} minutes et {estimated_time % 60} secondes.")

        # Boucle de requêtes
        for i in range(max_requests):
            start = i * rows_per_request
            status_text.text(f"🔍 Requête {i + 1}/{max_requests} en cours (Documents {start + 1} à {start + rows_per_request})...")
            
            response = send_soap_request(start, log_container)
            
            if response is None:
                log_container.error(f"❌ Échec définitif de la requête {i + 1}.")
                continue

            try:
                root = ET.fromstring(response)
                ns = {'ns': 'http://eur-lex.europa.eu/'}
                documents = root.findall('.//ns:document', ns) or root.findall('.//document')

                if not documents:
                    log_container.warning(f"⚠️ Fin des résultats atteinte à la requête {i + 1}.")
                    break

                for doc in documents:
                    celex = doc.find('ns:CELEX', ns) or doc.find('CELEX')
                    title = doc.find('ns:TITLE', ns) or doc.find('TITLE')
                    country = doc.find('ns:COUNTRY', ns) or doc.find('COUNTRY')

                    all_documents.append({
                        'CELEX': celex.text if celex is not None else 'N/A',
                        'Titre': title.text if title is not None else 'N/A',
                        'Pays': country.text if country is not None else 'N/A'
                    })

                log_container.success(f"✅ Requête {i + 1} : {len(documents)} documents récupérés.")
                
            except ET.ParseError as e:
                log_container.error(f"⚠️ Erreur de parsing XML pour la requête {i + 1}: {e}")
                continue

            # Mise à jour de la barre de progression
            progress_bar.progress((i + 1) / max_requests)

            # Pause si ce n'est pas la dernière requête
            if i < max_requests - 1:
                time.sleep(delay)

        # --- FINALISATION ET EXPORT ---
        status_text.text("✨ Extraction terminée !")
        
        if all_documents:
            st.success(f"🎉 Succès ! {len(all_documents)} documents récupérés au total.")
            
            # Affichage d'un aperçu
            df = pd.DataFrame(all_documents)
            st.write("### Aperçu des données :")
            st.dataframe(df.head(10))
            
            # Création du fichier Excel en mémoire (BytesIO) pour Streamlit
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='EURLex_Data')
            processed_data = output.getvalue()
            
            # Bouton de téléchargement
            st.download_button(
                label="📥 Télécharger les résultats en Excel",
                data=processed_data,
                file_name=f"eurlex_{len(all_documents)}_documents.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.error("❌ Aucune donnée n'a été récupérée. Vérifiez votre requête ou vos identifiants.")