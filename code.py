import streamlit as st
import requests
import pandas as pd
from xml.etree import ElementTree as ET
import time
import json
import logging
from datetime import datetime, timedelta

# ── PAGE CONFIG ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Extracteur Juridique Pro",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.title("⚖️ Extracteur Juridique Pro")
st.markdown("Extraction complète des métadonnées — **EUR-Lex** (SOAP) · **Légifrance** (API PISTE OAuth2)")

# ==========================================
# CONSTANTES & MÉTADONNÉES
# ==========================================

URL_EURLEX = "https://eur-lex.europa.eu/EURLexWebService"

EL_SOUS_DOMAINES = {
    "Législation (DIR, REG, DEC…)": "LEGISLATION",
    "Mesures Nationales d'Exécution (MNE)": "MNE",
    "Jurisprudence CJUE": "EU_CASE_LAW",
    "Actes préparatoires": "PREP_ACT",
    "Journal Officiel UE": "EU_OJ",
    "Accords internationaux": "INTERNATIONAL_AGREEMENTS",
    "Questions parlementaires": "PARL_QUEST",
}

EL_TYPES_ACTE = {
    "Tous types": "",
    "Directive": "DIR",
    "Règlement": "REG",
    "Décision": "DEC",
    "Recommandation": "REC",
    "Résolution": "RES",
    "Avis": "OPIN",
    "Lignes directrices": "GENGUID",
    "Règlement délégué": "DELEG_REG",
    "Règlement d'exécution": "IMPL_REG",
    "Décision déléguée": "DELEG_DEC",
    "Décision d'exécution": "IMPL_DEC",
}

EL_INSTITUTIONS = {
    "Toutes institutions": "",
    "Commission européenne": "COM",
    "Conseil de l'UE": "CONSIL",
    "Parlement européen": "EP",
    "Cour de Justice (CJUE)": "CJEU",
    "Banque Centrale Européenne": "ECB",
    "Cour des Comptes": "ECA",
    "Comité économique et social": "EESC",
    "Comité des Régions": "COR",
    "EFSA": "EFSA",
    "EMA": "EMA",
    "ESMA": "ESMA",
    "EIOPA": "EIOPA",
    "EBA": "EBA",
    "ENISA": "ENISA",
}

EL_PAYS = {
    "Tous pays": "",
    "France": "FRA", "Allemagne": "DEU", "Espagne": "ESP",
    "Italie": "ITA", "Belgique": "BEL", "Pays-Bas": "NLD",
    "Pologne": "POL", "Portugal": "PRT", "Suède": "SWE",
    "Roumanie": "ROU", "Autriche": "AUT", "Tchéquie": "CZE",
    "Hongrie": "HUN", "Grèce": "GRC", "Danemark": "DNK",
    "Finlande": "FIN", "Irlande": "IRL", "Slovaquie": "SVK",
    "Croatie": "HRV", "Bulgarie": "BGR",
}

EL_LANGUES = {
    "Français": "fr", "Anglais": "en", "Allemand": "de",
    "Espagnol": "es", "Italien": "it", "Polonais": "pl",
    "Portugais": "pt", "Néerlandais": "nl", "Roumain": "ro",
}

EL_TRIS = {
    "Pertinence (défaut)": "",
    "Date du document ↓": "SORT_DATE_OF_DOC_DESC",
    "Date du document ↑": "SORT_DATE_OF_DOC_ASC",
    "Date publication ↓": "SORT_DATE_OF_PUBLICATION_DESC",
    "Date publication ↑": "SORT_DATE_OF_PUBLICATION_ASC",
}

# Toutes les métadonnées EUR-Lex groupées
EL_METADATA = {
    "🔑 Identification": {
        "CELEX (identifiant unique)": ["ID_CELEX", "CELEX"],
        "Titre complet": ["EXPRESSION_TITLE", "TITLE", "TITLE_OF_DOCUMENT"],
        "Titre abrégé": ["EXPRESSION_TITLE_SHORT"],
        "Type d'acte (code)": ["FM_CODED", "ACT_TYPE"],
        "Type de document (libellé)": ["TYPE_OF_DOCUMENT"],
        "Institution auteur": ["WORK_IS_CREATED_BY_AGENT", "AUTHOR", "AGENT_NAME"],
        "Rôle de l'auteur": ["ROLE_QUALIFIER"],
        "N° document interne": ["WORK_ID_DOCUMENT"],
        "N° au Journal Officiel UE": ["WORK_ID_DOCUMENT_JO"],
        "Langue authentique": ["AUTHENTIC_LANGUAGE", "LANGUAGE"],
        "Langues disponibles": ["WORK_HAS_EXPRESSION"],
        "Destinataire": ["ADDRESSEE"],
        "État membre (MNE)": ["NATIONAL_IMPLEMENTING_MEASURE_COUNTRY", "COUNTRY", "MEMBER_STATE"],
        "ECLI (jurisprudence)": ["ECLI"],
        "Collection / Série": ["WORK_PART_OF_COLLECTION"],
        "Nombre de pages": ["NUMBER_OF_PAGES"],
    },
    "📅 Dates": {
        "Date du document": ["WORK_DATE_DOCUMENT", "DATE_DOCUMENT", "DATE"],
        "Date de publication JO": ["DATE_PUBLICATION", "PUBLICATION_DATE"],
        "Date d'entrée en vigueur": ["WORK_DATE_ENTRY_INTO_FORCE", "DATE_ENTRY_INTO_FORCE"],
        "Date de fin de validité": ["DATE_END_OF_VALIDITY", "END_OF_VALIDITY_DATE"],
        "Date de transposition (DIR)": ["DATE_TRANSPOSITION"],
        "Date d'effet": ["DATE_EFFECT"],
        "Date de signature": ["DATE_SIGNATURE"],
        "Date de notification": ["DATE_NOTIFICATION"],
        "Date limite / échéance": ["DATE_DEADLINE"],
        "Date de création (base)": ["WORK_DATE_CREATION"],
        "Date du corrigendum": ["WORK_DATE_CORRIGENDUM"],
    },
    "📋 Contenu & Classification": {
        "Matière / Sujet": ["SUBJECT_MATTER", "SUBJECT"],
        "Descripteurs Eurovoc": ["EUROVOC", "EUROVOC_DESCRIPTOR"],
        "Code répertoire législatif": ["DIRECTORY_CODE"],
        "Base légale (article Traité)": ["LEGAL_BASIS", "BASE_LEGALE"],
        "Base légale (code)": ["LEGAL_BASIS_CODED"],
        "Traité de référence": ["TREATY_CODE", "TREATY"],
        "Secteur": ["SECTOR"],
        "Forme de l'acte": ["FORM_ORIG"],
        "Statut (en vigueur / abrogé)": ["STATUS_FORCE"],
        "Version consolidée actuelle": ["CURRENT_CONSOLIDATED_VERSION"],
        "Lien vers consolidation": ["WORK_HAS_CONSOLIDATION"],
        "Concept EuroVoc lié": ["WORK_IS_ABOUT_CONCEPT"],
        "Juridiction (CJUE)": ["WORK_EXAMPLES_JURISDICTION"],
        "Formation de jugement": ["CASE_LAW_FORMATION"],
        "Issue / dispositif": ["CASE_LAW_OUTCOME"],
    },
    "🔗 Procédure & Relations": {
        "N° procédure interinstitutionnel": ["INTERINSTITUTIONAL_FILE_NUMBER", "PROCEDURE_NUMBER"],
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
        "Cité dans affaire CJUE": ["WORK_CITED_IN_CASE"],
        "Transposé depuis (DIR)": ["WORK_TRANSPOSES"],
    },
}

LF_FONDS = {
    "Tous": "ALL",
    "Lois, ordonnances, décrets, arrêtés": "LODA",
    "Codes": "CODE",
    "Jurisprudence judiciaire": "JURI",
    "Jurisprudence administrative": "CETAT",
    "Jurisprudence constitutionnelle": "CONSTIT",
    "Journal Officiel": "JORF",
    "Délibérations CNIL": "CNIL",
    "Circulaires": "CIRC",
    "Accords d'entreprise": "ACCO",
    "Conventions collectives": "KALI",
}

LF_NATURES = {
    "Toutes natures": "",
    "Loi": "LOI",
    "Ordonnance": "ORDONNANCE",
    "Décret": "DECRET",
    "Arrêté": "ARRETE",
    "Décision": "DECISION",
    "Circulaire": "CIRCULAIRE",
    "Accord": "ACCORD",
    "Avenant": "AVENANT",
    "Convention": "CONVENTION",
    "Instruction": "INSTRUCTION",
}

LF_MINISTERES = {
    "Tous": "",
    "Premier Ministre": "PREMIER MINISTRE",
    "Ministère de l'Économie": "ECONOMIE",
    "Ministère de l'Intérieur": "INTERIEUR",
    "Ministère de la Justice": "JUSTICE",
    "Ministère du Travail": "TRAVAIL",
    "Ministère de la Santé": "SANTE",
    "Ministère de l'Éducation nationale": "EDUCATION",
    "Ministère de la Défense": "DEFENSE",
    "Ministère de l'Environnement": "ENVIRONNEMENT",
    "Ministère de la Culture": "CULTURE",
    "Secrétariat d'État au Numérique": "NUMERIQUE",
    "Ministère de l'Agriculture": "AGRICULTURE",
    "Ministère des Transports": "TRANSPORTS",
    "Ministère du Logement": "LOGEMENT",
}

LF_CHAMPS = {
    "Texte intégral": "ALL",
    "Titre": "TITLE",
    "Table des matières": "TABLE_MATIERE",
    "Article": "ARTICLE",
    "Numéro NOR": "NOR",
    "Numéro du texte": "NUM",
    "Visa": "VISA",
    "Nota": "NOTA",
}

LF_OPERATEURS = {"ET (AND)": "ET", "OU (OR)": "OU", "Expression exacte": "EXACTE"}

LF_TRIS = {
    "Pertinence": "PERTINENCE",
    "Date signature ↓": "SIGNATURE_DATE_DESC",
    "Date signature ↑": "SIGNATURE_DATE_ASC",
    "Date publication ↓": "PUBLICATION_DATE_DESC",
    "N° article ↓": "NUM_ARTICLE_DESC",
}

LF_METADATA_FIELDS = {
    "🔑 Identification": {
        "CID (identifiant Légifrance)": "cid",
        "ID interne": "id",
        "Numéro NOR": "nor",
        "Numéro du texte": "num",
        "Titre complet": "title",
        "Titre abrégé": "shortTitle",
        "Nature du texte": "nature",
        "Fonds de données": "fond",
    },
    "📅 Dates": {
        "Date de signature": "signatureDate",
        "Date de publication (JORF)": "publicationDate",
        "Date de début de vigueur": "dateDebut",
        "Date de fin de vigueur": "dateFin",
    },
    "🏛️ Auteur & Publication": {
        "État (vigueur / abrogé)": "etat",
        "Ministère signataire": "ministere",
        "Autorité signataire": "autorite",
        "Page JORF": "jorfPage",
        "Numéro JORF": "jorfNum",
        "Numéro de parution": "numParution",
    },
    "🔗 Liens & Contenu": {
        "Lien texte HTML": "texteHtml",
        "Lien texte PDF": "textePdf",
        "URL Légifrance": "lienLegifrance",
        "Code(s) affecté(s)": "codeAffecte",
        "Article(s) modifié(s)": "articleAffecte",
        "Visas": "visas",
        "Nota bene": "nota",
        "Tags thématiques": "observatoire",
    },
}

# ==========================================
# FONCTIONS UTILITAIRES
# ==========================================

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
                clean_text = " ".join([w for w in raw_text.split() if not w.startswith("http")])
                if clean_text:
                    return clean_text
    return "Non renseigné"

def send_soap_request(page, query, user, pwd, rows, lang, sort_by, log_container):
    # L'API SOAP EUR-Lex ne gère pas de balise XML de tri.
    # L'ajout de <sear:sortBy> provoque une erreur 500. Le tri par défaut est la pertinence.
    
    envelope = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" xmlns:sear="http://eur-lex.europa.eu/search">'
        '<soap:Header>'
        '<wsse:Security soap:mustUnderstand="true" xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">'
        # Ajout obligatoire de wsu:Id
        '<wsse:UsernameToken wsu:Id="UsernameToken-1" xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">'
        f'<wsse:Username>{user}</wsse:Username>'
        f'<wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordText">{pwd}</wsse:Password>'
        '</wsse:UsernameToken>'
        '</wsse:Security>'
        '</soap:Header>'
        '<soap:Body>'
        '<sear:searchRequest>'
        f'<sear:expertQuery><![CDATA[{query}]]></sear:expertQuery>'
        f'<sear:page>{page}</sear:page>'
        f'<sear:pageSize>{rows}</sear:pageSize>'
        f'<sear:searchLanguage>{lang}</sear:searchLanguage>'
        '</sear:searchRequest>'
        '</soap:Body>'
        '</soap:Envelope>'
    )
    try:
        resp = requests.post(
            URL_EURLEX,
            data=envelope.encode('utf-8'),
            headers={'Content-Type': 'application/soap+xml; charset=utf-8'},
            timeout=60
        )
        if resp.status_code == 500:
            log_container.error(
                f"❌ HTTP 500 — Réponse serveur : `{resp.text[:600]}`\n\n"
                f"Vérifiez que la requête Expert Query est valide : `{query}`"
            )
        return resp
    except requests.exceptions.RequestException as e:
        log_container.error(f"⚠️ Erreur de connexion : {e}")
        return None


# ── Session state init ─────────────────────────────────────────────────────────
if 'docs_eurlex' not in st.session_state:
    st.session_state.docs_eurlex = []
if 'docs_lf' not in st.session_state:
    st.session_state.docs_lf = []

# ==========================================
# ONGLETS PRINCIPAUX
# ==========================================
tab_el, tab_lf = st.tabs(["🇪🇺 EUR-Lex", "🇫🇷 Légifrance"])


# ══════════════════════════════════════════
# ONGLET 1 — EUR-LEX
# ══════════════════════════════════════════
with tab_el:
    st.header("Extraction depuis EUR-Lex (SOAP WebService)")

    # ── Authentification & Pagination ─────────────────────────────────────────
    with st.expander("🔑 Authentification & Pagination", expanded=True):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            el_user = st.text_input("Nom d'utilisateur EUR-Lex", key="el_user")
        with col2:
            el_pass = st.text_input("Mot de passe EUR-Lex", type="password", key="el_pass")
        with col3:
            el_rows = st.number_input("Documents par requête (max 100)", 1, 100, 10, key="el_rows")
        with col4:
            el_max_req = st.number_input("Nombre de requêtes max", 1, 2000, 5, key="el_max_req")

        col5, col6 = st.columns(2)
        with col5:
            el_lang = st.selectbox("Langue de recherche", list(EL_LANGUES.keys()), key="el_lang")
        with col6:
            el_sort = st.selectbox("Tri des résultats", list(EL_TRIS.keys()), key="el_sort")

    # ── Critères de recherche ─────────────────────────────────────────────────
    with st.expander("🔍 Critères de recherche", expanded=True):
        col_a, col_b = st.columns(2)

        with col_a:
            st.subheader("Domaine & Type")
            el_subdomain = st.selectbox("Sous-domaine", list(EL_SOUS_DOMAINES.keys()), key="el_subdomain")
            subdomain_code = EL_SOUS_DOMAINES[el_subdomain]

            show_type = subdomain_code in ("LEGISLATION", "PREP_ACT")
            show_country = subdomain_code == "MNE"

            if show_type:
                el_type = st.selectbox("Type d'acte", list(EL_TYPES_ACTE.keys()), key="el_type")
            else:
                el_type = "Tous types"

            el_author = st.selectbox("Institution auteur", list(EL_INSTITUTIONS.keys()), key="el_author")

            if show_country:
                el_country = st.selectbox("État membre (MNE)", list(EL_PAYS.keys()), key="el_country")
            else:
                el_country = "Tous pays"

            st.subheader("Identifiants")
            el_celex = st.text_input("Numéro CELEX exact (ex: 32016R0679)", key="el_celex")
            el_proc_num = st.text_input("N° procédure interinstitutionnel (ex: 2018/0048(COD))", key="el_proc_num")
            el_jo_num = st.text_input("Numéro du Journal Officiel UE", key="el_jo_num")
            el_jo_serie = st.selectbox("Série JO", ["Toutes", "L (actes législatifs)", "C (communications)"], key="el_jo_serie")

        with col_b:
            st.subheader("Recherche textuelle")
            el_txt = st.text_input("Texte intégral (TE~)", placeholder="ex: protection données personnelles", key="el_txt")
            el_title_q = st.text_input("Titre (TI~)", placeholder="ex: règlement général", key="el_title_q")
            el_eurovoc = st.text_input("Descripteurs Eurovoc", placeholder="ex: protection des données", key="el_eurovoc")
            el_legal_basis = st.text_input("Base légale (ex: TFEU ART114)", key="el_legal_basis")
            el_subject = st.text_input("Matière / Sujet", key="el_subject")

            st.subheader("Filtres temporels")
            col_yr1, col_yr2 = st.columns(2)
            with col_yr1:
                el_year = st.text_input("Année du document (DD_YEAR)", max_chars=4, placeholder="2024", key="el_year")
            with col_yr2:
                el_pub_year = st.text_input("Année publication JO (PUB_YEAR)", max_chars=4, placeholder="2024", key="el_pub_year")

            col_d1, col_d2 = st.columns(2)
            with col_d1:
                el_date1 = st.text_input("Date début (DD>=)", placeholder="01/01/2020", key="el_date1")
            with col_d2:
                el_date2 = st.text_input("Date fin (DD<=)", placeholder="31/12/2024", key="el_date2")

            el_in_force = st.checkbox("Actes en vigueur uniquement", key="el_in_force")
            el_with_consol = st.checkbox("Avec version consolidée disponible", key="el_with_consol")

    # ── Construction de la requête Expert Query ────────────────────────────────
    parts = [f"DTS_SUBDOM={subdomain_code}"]

    if show_type and EL_TYPES_ACTE[el_type]:
        parts.append(f"FM_CODED={EL_TYPES_ACTE[el_type]}")

    if EL_INSTITUTIONS[el_author]:
        parts.append(f"WORK_IS_CREATED_BY_AGENT={EL_INSTITUTIONS[el_author]}")

    if show_country and EL_PAYS[el_country]:
        parts.append(f"NATIONAL_IMPLEMENTING_MEASURE_COUNTRY={EL_PAYS[el_country]}")

    # ── Champs textuels — opérateur ~ supporté sur TE et TI uniquement ──────────
    if el_celex.strip():
        parts.append(f'ID_CELEX={el_celex.strip()}')
    if el_proc_num.strip():
        # Numéro de procédure : recherche exacte, pas de guillemets
        parts.append(f'INTERINSTITUTIONAL_FILE_NUMBER={el_proc_num.strip()}')
    if el_jo_num.strip():
        parts.append(f'OJ_NO={el_jo_num.strip()}')
    # Série JO : L ou C — via FM_CODED n'est pas fiable, on l'omet intentionnellement
    # pour éviter les 500. L'utilisateur peut affiner via FM_CODED.
    if el_txt.strip():
        # TE~ : recherche plein texte, opérateur ~ supporté
        parts.append(f'TE~"{el_txt.strip()}"')
    if el_title_q.strip():
        # TI~ : recherche dans le titre, opérateur ~ supporté
        parts.append(f'TI~"{el_title_q.strip()}"')
    if el_eurovoc.strip():
        # EUROVOC_MT : champ officiel pour les descripteurs, opérateur = requis
        parts.append(f'DESCRIPTOR_EUROVOC~"{el_eurovoc.strip()}"')
    if el_legal_basis.strip():
        # BASE_LEGALE : recherche textuelle exacte
        parts.append(f'WORK_BASED_ON_TREATY_CONCEPT~"{el_legal_basis.strip()}"')
    if el_subject.strip():
        parts.append(f'SUBJECT_MATTER~"{el_subject.strip()}"')
    if el_year.strip():
        parts.append(f'DD_YEAR={el_year.strip()}')
    if el_pub_year.strip():
        # DG_YEAR = année de publication au Journal Officiel
        parts.append(f'DG_YEAR={el_pub_year.strip()}')
    if el_date1.strip() and el_date2.strip():
        parts.append(f'DD=[{el_date1.strip()} TO {el_date2.strip()}]')
    elif el_date1.strip():
        parts.append(f'DD>={el_date1.strip()}')
    elif el_date2.strip():
        parts.append(f'DD<={el_date2.strip()}')
    # IN_FORCE et HAS_CONSOLIDATION ne sont pas des champs Expert Query valides,
    # ils sont gérés côté post-filtrage uniquement (voir note ci-dessous)

    final_query = " AND ".join(parts)
    st.info(f"**Requête Expert Query générée :** `{final_query}`")

    # Avertissement si la requête ne contient que DTS_SUBDOM
    if len(parts) < 2:
        st.warning(
            "⚠️ La requête ne contient que le sous-domaine — EUR-Lex exige au moins un critère "
            "supplémentaire (texte intégral, année, type d'acte, CELEX…) pour éviter une erreur HTTP 500."
        )

    # ── Sélection des métadonnées ──────────────────────────────────────────────
    with st.expander("📊 Métadonnées à extraire", expanded=True):
        all_el_labels = []
        for group_name, fields in EL_METADATA.items():
            all_el_labels.extend(list(fields.keys()))

        col_sel1, col_sel2 = st.columns([3, 1])
        with col_sel2:
            if st.button("Tout sélectionner", key="el_select_all"):
                st.session_state.el_selected = all_el_labels
            if st.button("Tout désélectionner", key="el_deselect_all"):
                st.session_state.el_selected = []

        default_el = [
            "CELEX (identifiant unique)", "Titre complet", "Type d'acte (code)",
            "Institution auteur", "Date du document", "Date de publication JO",
            "Date d'entrée en vigueur", "Statut (en vigueur / abrogé)",
            "Matière / Sujet", "Descripteurs Eurovoc", "Base légale (article Traité)",
        ]
        if 'el_selected' not in st.session_state:
            st.session_state.el_selected = default_el

        for group_name, fields in EL_METADATA.items():
            st.markdown(f"**{group_name}**")
            group_cols = st.columns(3)
            for i, label in enumerate(fields.keys()):
                with group_cols[i % 3]:
                    checked = label in st.session_state.el_selected
                    if st.checkbox(label, value=checked, key=f"el_meta_{label}"):
                        if label not in st.session_state.el_selected:
                            st.session_state.el_selected.append(label)
                    else:
                        if label in st.session_state.el_selected:
                            st.session_state.el_selected.remove(label)

    # ── Zone d'affichage & lancement ──────────────────────────────────────────
    export_slot_el = st.empty()
    table_slot_el = st.empty()
    st.divider()
    progress_el = st.empty()
    status_el = st.empty()
    log_el = st.container()
    raw_el = st.empty()

    if st.button("🚀 Lancer l'extraction EUR-Lex", type="primary", use_container_width=True):
        if not el_user or not el_pass:
            st.error("⚠️ Identifiants EUR-Lex manquants.")
        elif len(parts) < 2:
            st.error(
                "⚠️ Requête insuffisante — ajoutez au moins un critère en plus du sous-domaine "
                "(texte intégral, année, type d'acte, CELEX…)."
            )
        elif not st.session_state.el_selected:
            st.error("⚠️ Sélectionnez au moins une métadonnée à extraire.")
        else:
            # Construire la map de fallback pour les champs sélectionnés
            meta_map = {}
            for group_fields in EL_METADATA.values():
                for label, tags in group_fields.items():
                    if label in st.session_state.el_selected:
                        meta_map[label] = tags

            st.session_state.docs_eurlex = []
            lang_code = EL_LANGUES[el_lang]
            sort_code = EL_TRIS[el_sort]
            bar = progress_el.progress(0)

            for i in range(el_max_req):
                page = i + 1
                status_el.text(f"🔍 Requête {page}/{el_max_req} en cours…")

                resp = send_soap_request(
                    page, final_query, el_user, el_pass,
                    el_rows, lang_code, sort_code, log_el
                )

                if resp is None:
                    break
                if resp.status_code != 200:
                    # Le détail de l'erreur est déjà loggé dans send_soap_request pour les 500
                    if resp.status_code != 500:
                        log_el.error(f"❌ HTTP {resp.status_code} — {resp.text[:300]}")
                    break

                try:
                    root = ET.fromstring(resp.content)
                except ET.ParseError as e:
                    log_el.error(f"⚠️ Erreur XML page {page} : {e}")
                    break

                docs_nodes = [
                    e for e in root.iter()
                    if e.tag.split('}')[-1] in ('document', 'result')
                ]
                if not docs_nodes:
                    log_el.info(f"✅ Fin de pagination à la page {page}.")
                    break

                for doc in docs_nodes:
                    row = {lbl: get_xml_value(doc, tags) for lbl, tags in meta_map.items()}
                    st.session_state.docs_eurlex.append(row)

                log_el.success(f"Page {page} : {len(docs_nodes)} documents récupérés (total : {len(st.session_state.docs_eurlex)})")

                if st.session_state.docs_eurlex:
                    df_live = pd.DataFrame(st.session_state.docs_eurlex)
                    table_slot_el.dataframe(df_live, use_container_width=True)

                bar.progress((i + 1) / el_max_req)
                time.sleep(1)

            status_el.text("✅ Extraction terminée.")

    # Affichage permanent des résultats en cache
    if st.session_state.docs_eurlex:
        df_el = pd.DataFrame(st.session_state.docs_eurlex)
        with export_slot_el.container():
            st.success(f"🎉 **{len(st.session_state.docs_eurlex)} documents** récupérés.")
            col_dl1, col_dl2, col_dl3 = st.columns(3)
            with col_dl1:
                st.download_button(
                    "📥 Télécharger CSV",
                    data=df_el.to_csv(index=False, sep=';').encode('utf-8-sig'),
                    file_name="eurlex_donnees.csv",
                    mime="text/csv",
                    type="primary",
                    use_container_width=True,
                    key="dl_el_csv"
                )
            with col_dl2:
                st.download_button(
                    "📥 Télécharger JSON",
                    data=json.dumps(st.session_state.docs_eurlex, ensure_ascii=False, indent=2).encode('utf-8'),
                    file_name="eurlex_donnees.json",
                    mime="application/json",
                    use_container_width=True,
                    key="dl_el_json"
                )
            with col_dl3:
                if st.button("🗑️ Effacer les résultats", use_container_width=True, key="clear_el"):
                    st.session_state.docs_eurlex = []
                    st.rerun()

        table_slot_el.dataframe(df_el, use_container_width=True)
        with raw_el.expander("🔎 JSON brut (toutes les métadonnées extraites)"):
            st.json(st.session_state.docs_eurlex)


# ══════════════════════════════════════════
# ONGLET 2 — LÉGIFRANCE
# ══════════════════════════════════════════
with tab_lf:
    st.header("Extraction depuis Légifrance (API PISTE OAuth2)")

    # ── Authentification ───────────────────────────────────────────────────────
    with st.expander("🔑 Authentification PISTE", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            lf_cid = st.text_input("Client ID PISTE", placeholder="Votre Client ID", key="lf_cid")
        with col2:
            lf_cs = st.text_input("Client Secret PISTE", type="password", placeholder="Votre Client Secret", key="lf_cs")
        st.caption("Obtenez vos identifiants sur **piste.gouv.fr** → Mes Applications → API Légifrance v2")

    # ── Critères de recherche ─────────────────────────────────────────────────
    with st.expander("🔍 Critères de recherche", expanded=True):
        col_a, col_b = st.columns(2)

        with col_a:
            st.subheader("Fonds & Type")
            lf_fond = st.selectbox("Fonds de données", list(LF_FONDS.keys()), key="lf_fond")
            lf_nature = st.selectbox("Nature du texte", list(LF_NATURES.keys()), key="lf_nature")
            lf_minist = st.selectbox("Ministère signataire", list(LF_MINISTERES.keys()), key="lf_minist")

            st.subheader("Identifiants directs")
            lf_nor = st.text_input("Numéro NOR exact (ex: JUSC2307938A)", key="lf_nor")
            lf_num = st.text_input("Numéro du texte (ex: 2023-1107)", key="lf_num")

            st.subheader("Pagination & Tri")
            col_pg1, col_pg2 = st.columns(2)
            with col_pg1:
                lf_page_size = st.number_input("Résultats par page", 1, 100, 25, key="lf_page_size")
                lf_max_pages = st.number_input("Nombre de pages max", 1, 50, 3, key="lf_max_pages")
            with col_pg2:
                lf_sort = st.selectbox("Tri", list(LF_TRIS.keys()), key="lf_sort")

        with col_b:
            st.subheader("Recherche textuelle")
            lf_champ = st.selectbox("Champ de recherche", list(LF_CHAMPS.keys()), key="lf_champ")
            lf_q = st.text_input("Valeur recherchée", placeholder="ex: intelligence artificielle", key="lf_q")
            lf_op = st.selectbox("Opérateur", list(LF_OPERATEURS.keys()), key="lf_op")

            lf_champ2 = st.selectbox("2ème champ (optionnel)", ["(aucun)"] + list(LF_CHAMPS.keys()), key="lf_champ2")
            lf_q2 = st.text_input("Valeur 2ème champ", key="lf_q2")
            lf_op2 = st.selectbox("Opérateur 2ème champ", list(LF_OPERATEURS.keys()), key="lf_op2")

            st.subheader("Filtres temporels")
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                lf_date1 = st.text_input("Date début signature (YYYY-MM-DD)", placeholder="2020-01-01", key="lf_date1")
            with col_d2:
                lf_date2 = st.text_input("Date fin signature (YYYY-MM-DD)", placeholder="2024-12-31", key="lf_date2")

            col_dp1, col_dp2 = st.columns(2)
            with col_dp1:
                lf_pub1 = st.text_input("Date début publication (YYYY-MM-DD)", key="lf_pub1")
            with col_dp2:
                lf_pub2 = st.text_input("Date fin publication (YYYY-MM-DD)", key="lf_pub2")

            lf_in_force = st.checkbox("Textes en vigueur uniquement", key="lf_in_force")

    # ── Sélection des métadonnées ──────────────────────────────────────────────
    with st.expander("📊 Métadonnées à extraire", expanded=True):
        all_lf_keys = []
        for fields in LF_METADATA_FIELDS.values():
            all_lf_keys.extend(list(fields.keys()))

        col_s1, col_s2 = st.columns([3, 1])
        with col_s2:
            if st.button("Tout sélectionner", key="lf_sel_all"):
                st.session_state.lf_selected = all_lf_keys
            if st.button("Tout désélectionner", key="lf_desel_all"):
                st.session_state.lf_selected = []

        default_lf = [
            "CID (identifiant Légifrance)", "Numéro NOR", "Titre complet",
            "Nature du texte", "Fonds de données", "Date de signature",
            "Date de publication (JORF)", "État (vigueur / abrogé)", "Ministère signataire",
        ]
        if 'lf_selected' not in st.session_state:
            st.session_state.lf_selected = default_lf

        for group_name, fields in LF_METADATA_FIELDS.items():
            st.markdown(f"**{group_name}**")
            group_cols = st.columns(4)
            for i, label in enumerate(fields.keys()):
                with group_cols[i % 4]:
                    checked = label in st.session_state.lf_selected
                    if st.checkbox(label, value=checked, key=f"lf_meta_{label}"):
                        if label not in st.session_state.lf_selected:
                            st.session_state.lf_selected.append(label)
                    else:
                        if label in st.session_state.lf_selected:
                            st.session_state.lf_selected.remove(label)

    # ── Lancement de l'extraction ──────────────────────────────────────────────
    if st.button("🚀 Lancer l'extraction Légifrance", type="primary", use_container_width=True):
        if not lf_cid or not lf_cs:
            st.error("⚠️ Identifiants PISTE manquants (Client ID et Client Secret).")
        elif not lf_q and not lf_nor and not lf_num:
            st.warning("⚠️ Saisissez au moins un mot-clé, un NOR ou un numéro de texte.")
        elif not st.session_state.lf_selected:
            st.error("⚠️ Sélectionnez au moins une métadonnée à extraire.")
        else:
            # Authentification
            with st.spinner("🔐 Authentification PISTE en cours…"):
                try:
                    token_resp = requests.post(
                        "https://oauth.piste.gouv.fr/api/oauth/token",
                        data={
                            "grant_type": "client_credentials",
                            "client_id": lf_cid,
                            "client_secret": lf_cs,
                            "scope": "openid"
                        },
                        timeout=15
                    )
                    token_resp.raise_for_status()
                    token = token_resp.json().get("access_token")
                    st.success("✅ Authentification réussie.")
                except requests.exceptions.HTTPError as e:
                    st.error(f"❌ Erreur d'authentification : {e.response.status_code} — {e.response.text[:200]}")
                    token = None
                except Exception as e:
                    st.error(f"❌ Erreur inattendue : {e}")
                    token = None

            if token:
                headers_lf = {
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json"
                }

                # Construire la map label → clé API
                meta_map_lf = {}
                for group_fields in LF_METADATA_FIELDS.values():
                    for label, api_key in group_fields.items():
                        if label in st.session_state.lf_selected:
                            meta_map_lf[label] = api_key

                st.session_state.docs_lf = []
                bar_lf = st.progress(0)
                status_lf = st.empty()
                log_lf = st.container()

                for page_num in range(1, lf_max_pages + 1):
                    status_lf.text(f"🔍 Page {page_num}/{lf_max_pages} en cours…")

                    # Construire le payload
                    champs = []
                    if lf_q.strip():
                        champs.append({
                            "typeChamp": LF_CHAMPS[lf_champ],
                            "criteres": [{"valeur": lf_q.strip(), "operateur": LF_OPERATEURS[lf_op]}]
                        })
                    if lf_champ2 != "(aucun)" and lf_q2.strip():
                        champs.append({
                            "typeChamp": LF_CHAMPS[lf_champ2],
                            "criteres": [{"valeur": lf_q2.strip(), "operateur": LF_OPERATEURS[lf_op2]}]
                        })
                    if lf_nor.strip():
                        champs.append({
                            "typeChamp": "NOR",
                            "criteres": [{"valeur": lf_nor.strip(), "operateur": "EXACTE"}]
                        })
                    if lf_num.strip():
                        champs.append({
                            "typeChamp": "NUM",
                            "criteres": [{"valeur": lf_num.strip(), "operateur": "EXACTE"}]
                        })

                    if not champs:
                        champs = [{"typeChamp": "ALL", "criteres": []}]

                    recherche = {"champs": champs}

                    # Filtres temporels
                    if lf_date1.strip():
                        recherche["dateDebut"] = lf_date1.strip()
                    if lf_date2.strip():
                        recherche["dateFin"] = lf_date2.strip()

                    # Filtres publication
                    if lf_pub1.strip():
                        recherche["publicationDateDebut"] = lf_pub1.strip()
                    if lf_pub2.strip():
                        recherche["publicationDateFin"] = lf_pub2.strip()

                    # Filtres facettes
                    filtres = []
                    if LF_NATURES[lf_nature]:
                        filtres.append({"facette": "NATURE", "valeur": LF_NATURES[lf_nature]})
                    if LF_MINISTERES[lf_minist]:
                        filtres.append({"facette": "MINISTERE", "valeur": LF_MINISTERES[lf_minist]})
                    if lf_in_force:
                        filtres.append({"facette": "ETAT_JURIDIQUE", "valeur": "VIGEUR"})
                    if filtres:
                        recherche["filtres"] = filtres

                    payload_lf = {
                        "recherche": recherche,
                        "fond": LF_FONDS[lf_fond],
                        "pageNumber": page_num,
                        "pageSize": lf_page_size,
                        "sort": LF_TRIS[lf_sort]
                    }

                    try:
                        resp_lf = requests.post(
                            "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app/search",
                            headers=headers_lf,
                            json=payload_lf,
                            timeout=30
                        )
                        resp_lf.raise_for_status()
                    except requests.exceptions.HTTPError as e:
                        log_lf.error(f"❌ Erreur HTTP page {page_num} : {e.response.status_code} — {e.response.text[:200]}")
                        break
                    except Exception as e:
                        log_lf.error(f"❌ Erreur : {e}")
                        break

                    data_lf = resp_lf.json()
                    results = data_lf.get("results", [])
                    total = data_lf.get("totalResultNumber", 0)

                    if not results:
                        log_lf.info(f"✅ Fin de pagination à la page {page_num} (total API : {total}).")
                        break

                    for res in results:
                        row = {}
                        for label, api_key in meta_map_lf.items():
                            val = res.get(api_key)
                            if isinstance(val, list):
                                row[label] = " | ".join(str(v) for v in val)
                            elif val is None:
                                row[label] = "N/A"
                            else:
                                row[label] = str(val)
                        st.session_state.docs_lf.append(row)

                    log_lf.success(f"Page {page_num} : {len(results)} résultats (total récupéré : {len(st.session_state.docs_lf)}/{total})")
                    bar_lf.progress(page_num / lf_max_pages)

                    if len(st.session_state.docs_lf) >= total:
                        log_lf.info("Tous les résultats disponibles ont été récupérés.")
                        break

                    time.sleep(0.5)

                status_lf.text("✅ Extraction terminée.")

    # Affichage permanent
    if st.session_state.docs_lf:
        df_lf = pd.DataFrame(st.session_state.docs_lf)
        st.success(f"🎉 **{len(st.session_state.docs_lf)} documents** récupérés.")

        col_dl1, col_dl2, col_dl3 = st.columns(3)
        with col_dl1:
            st.download_button(
                "📥 Télécharger CSV",
                data=df_lf.to_csv(index=False, sep=';').encode('utf-8-sig'),
                file_name="legifrance_donnees.csv",
                mime="text/csv",
                type="primary",
                use_container_width=True,
                key="dl_lf_csv"
            )
        with col_dl2:
            st.download_button(
                "📥 Télécharger JSON",
                data=json.dumps(st.session_state.docs_lf, ensure_ascii=False, indent=2).encode('utf-8'),
                file_name="legifrance_donnees.json",
                mime="application/json",
                use_container_width=True,
                key="dl_lf_json"
            )
        with col_dl3:
            if st.button("🗑️ Effacer les résultats", use_container_width=True, key="clear_lf"):
                st.session_state.docs_lf = []
                st.rerun()

        st.dataframe(df_lf, use_container_width=True)
        with st.expander("🔎 JSON brut retourné par l'API"):
            st.json(st.session_state.docs_lf)