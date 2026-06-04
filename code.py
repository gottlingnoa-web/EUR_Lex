#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import requests
import pandas as pd
from xml.etree import ElementTree as ET
import time
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta

# ==========================================
# 1. LOGIQUE MÉTIER : EUR-LEX
# ==========================================
URL_EURLEX = "https://eur-lex.europa.eu/EURLexWebService"
ROWS_PER_REQ = 10
SEARCH_LANGUAGE = "fr"

METADATA_MAP = {
    "CELEX (identifiant unique)": ["ID_CELEX"],
    "Titre complet": ["EXPRESSION_TITLE"],
    "Type d'acte (code)": ["FM_CODED"],
    "Type de document (libellé)": ["TYPE_OF_DOCUMENT"],
    "Date publication JO": ["DATE_PUBLICATION"],
    # J'ai réduit la liste ici pour la lisibilité du code, 
    # mais vous pouvez rajouter toute votre liste METADATA_MAP d'origine.
    "Date d'effet": ["DATE_EFFECT"],
    "Base légale (article Traité)": ["LEGAL_BASIS"],
    "Statut (en vigueur / abrogé)": ["STATUS_FORCE"]
}

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

def run_eurlex_extraction(username, password, query, max_requests, log_callback):
    log_callback("--- Démarrage de l'extraction EUR-Lex ---")
    all_docs = []
    
    for i in range(max_requests):
        page = i + 1
        log_callback(f"Requête {page}/{max_requests}…")
        
        envelope = f"""<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" xmlns:sear="http://eur-lex.europa.eu/search">
  <soap:Header>
    <wsse:Security soap:mustUnderstand="true" xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">
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
      <sear:pageSize>{ROWS_PER_REQ}</sear:pageSize>
      <sear:searchLanguage>{SEARCH_LANGUAGE}</sear:searchLanguage>
    </sear:searchRequest>
  </soap:Body>
</soap:Envelope>"""

        try:
            resp = requests.post(URL_EURLEX, data=envelope.encode("utf-8"), headers={"Content-Type": "application/soap+xml; charset=utf-8"}, timeout=60)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            
            docs = []
            for elem in root.iter():
                if elem.tag.split("}")[-1] in ("document", "result"):
                    docs.append({label: extract_meta_eurlex(elem, tags) for label, tags in METADATA_MAP.items()})
            
            if not docs:
                log_callback(f"Fin de pagination (Page {page}).")
                break
                
            all_docs.extend(docs)
            log_callback(f"  → {len(docs)} documents récupérés (total: {len(all_docs)})")
            time.sleep(1)
            
        except Exception as e:
            log_callback(f"ERREUR à la page {page}: {str(e)}")
            break

    if all_docs:
        df = pd.DataFrame(all_docs)
        df.to_csv("eurlex_resultats.csv", index=False, sep=";", encoding="utf-8-sig")
        Path("eurlex_resultats.json").write_text(json.dumps(all_docs, ensure_ascii=False, indent=2), encoding="utf-8")
        log_callback(f"✅ Extraction terminée ! Fichiers sauvegardés (CSV et JSON). Lignes : {len(df)}")
    else:
        log_callback("❌ Aucun document trouvé ou échec de la connexion.")

# ==========================================
# 2. LOGIQUE MÉTIER : LÉGIFRANCE
# ==========================================
TOKEN_URL = "https://oauth.piste.gouv.fr/api/oauth/token"
API_BASE = "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app"
PAGE_SIZE = 25
FIELDS_TO_EXTRACT = ["cid", "id", "title", "nature", "fond", "publicationDate", "etat", "ministere"] # Réduit pour l'exemple

class PisteAuth:
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self._token = None
        self._expires_at = datetime.min

    def get_token(self, log_callback):
        if datetime.now() < self._expires_at:
            return self._token
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
        log_callback("Token PISTE obtenu/renouvelé.")
        return self._token

def run_legifrance_extraction(client_id, client_secret, fond, champ, valeur, max_pages, log_callback):
    log_callback("--- Démarrage de l'extraction Légifrance ---")
    all_docs = []
    auth = PisteAuth(client_id, client_secret)
    
    for page in range(1, max_pages + 1):
        log_callback(f"Page {page}/{max_pages}…")
        try:
            token = auth.get_token(log_callback)
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "Content-Type": "application/json"}
            
            criteres = [{"valeur": valeur, "operateur": "ET"}] if valeur else []
            champs = [{"typeChamp": champ, "criteres": criteres}] if criteres else [{"typeChamp": "ALL", "criteres": []}]
            
            payload = {
                "recherche": {"champs": champs},
                "fond": fond,
                "pageNumber": page,
                "pageSize": PAGE_SIZE,
                "sort": "PERTINENCE"
            }
            
            resp = requests.post(f"{API_BASE}/search", headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            total = data.get("totalResultNumber", 0)
            
            if not results:
                log_callback(f"Fin de pagination (total API : {total}).")
                break
                
            for r in results:
                row = {}
                for f in FIELDS_TO_EXTRACT:
                    val = r.get(f)
                    if isinstance(val, list): row[f] = " | ".join(str(v) for v in val)
                    elif val is None: row[f] = "N/A"
                    else: row[f] = str(val)
                all_docs.append(row)
                
            log_callback(f"  → {len(results)} résultats (total: {len(all_docs)}/{total})")
            if len(all_docs) >= total: break
            time.sleep(0.5)
            
        except Exception as e:
            log_callback(f"ERREUR à la page {page}: {str(e)}")
            break

    if all_docs:
        df = pd.DataFrame(all_docs)
        df.to_csv("legifrance_resultats.csv", index=False, sep=";", encoding="utf-8-sig")
        Path("legifrance_resultats.json").write_text(json.dumps(all_docs, ensure_ascii=False, indent=2), encoding="utf-8")
        log_callback(f"✅ Extraction terminée ! Fichiers sauvegardés (CSV et JSON). Lignes : {len(df)}")
    else:
        log_callback("❌ Aucun document trouvé ou échec de la connexion.")


# ==========================================
# 3. INTERFACE GRAPHIQUE (TKINTER)
# ==========================================
class ExtractorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Extracteurs Juridiques : EUR-Lex & Légifrance")
        self.geometry("800x600")
        self.configure(padx=10, pady=10)

        notebook = ttk.Notebook(self)
        notebook.pack(expand=True, fill='both')

        self.tab_eurlex = ttk.Frame(notebook)
        self.tab_legifrance = ttk.Frame(notebook)

        notebook.add(self.tab_eurlex, text='🇪🇺 EUR-Lex')
        notebook.add(self.tab_legifrance, text='🇫🇷 Légifrance')

        self.setup_eurlex_tab()
        self.setup_legifrance_tab()

    # --- ONGLET EUR-LEX ---
    def setup_eurlex_tab(self):
        frame = ttk.Frame(self.tab_eurlex, padding=10)
        frame.pack(fill='x')

        ttk.Label(frame, text="Nom d'utilisateur:").grid(row=0, column=0, sticky='w', pady=2)
        self.eurlex_user = ttk.Entry(frame, width=40)
        self.eurlex_user.grid(row=0, column=1, pady=2)

        ttk.Label(frame, text="Mot de passe:").grid(row=1, column=0, sticky='w', pady=2)
        self.eurlex_pass = ttk.Entry(frame, width=40, show="*")
        self.eurlex_pass.grid(row=1, column=1, pady=2)

        ttk.Label(frame, text="Requête:").grid(row=2, column=0, sticky='w', pady=2)
        self.eurlex_query = ttk.Entry(frame, width=40)
        self.eurlex_query.insert(0, "DTS_SUBDOM=LEGISLATION")
        self.eurlex_query.grid(row=2, column=1, pady=2)

        ttk.Label(frame, text="Max requêtes (Pages):").grid(row=3, column=0, sticky='w', pady=2)
        self.eurlex_pages = ttk.Entry(frame, width=10)
        self.eurlex_pages.insert(0, "5")
        self.eurlex_pages.grid(row=3, column=1, sticky='w', pady=2)

        self.btn_eurlex = ttk.Button(frame, text="▶ Lancer l'extraction", command=self.start_eurlex)
        self.btn_eurlex.grid(row=4, column=0, columnspan=2, pady=10)

        ttk.Label(self.tab_eurlex, text="Logs de l'extraction:").pack(anchor='w', padx=10)
        self.log_eurlex = scrolledtext.ScrolledText(self.tab_eurlex, height=15, state='disabled')
        self.log_eurlex.pack(expand=True, fill='both', padx=10, pady=5)

    def write_log_eurlex(self, message):
        self.log_eurlex.configure(state='normal')
        self.log_eurlex.insert(tk.END, message + "\n")
        self.log_eurlex.see(tk.END)
        self.log_eurlex.configure(state='disabled')
        self.update_idletasks()

    def start_eurlex(self):
        user = self.eurlex_user.get()
        pwd = self.eurlex_pass.get()
        query = self.eurlex_query.get()
        try: pages = int(self.eurlex_pages.get())
        except ValueError: pages = 5

        if not user or not pwd:
            messagebox.showwarning("Attention", "Veuillez renseigner vos identifiants EUR-Lex.")
            return

        self.btn_eurlex.config(state='disabled')
        self.log_eurlex.configure(state='normal')
        self.log_eurlex.delete('1.0', tk.END)
        self.log_eurlex.configure(state='disabled')

        def thread_task():
            run_eurlex_extraction(user, pwd, query, pages, self.write_log_eurlex)
            self.after(0, lambda: self.btn_eurlex.config(state='normal'))

        threading.Thread(target=thread_task, daemon=True).start()


    # --- ONGLET LÉGIFRANCE ---
    def setup_legifrance_tab(self):
        frame = ttk.Frame(self.tab_legifrance, padding=10)
        frame.pack(fill='x')

        ttk.Label(frame, text="Client ID:").grid(row=0, column=0, sticky='w', pady=2)
        self.leg_client = ttk.Entry(frame, width=50)
        self.leg_client.grid(row=0, column=1, pady=2)

        ttk.Label(frame, text="Client Secret:").grid(row=1, column=0, sticky='w', pady=2)
        self.leg_secret = ttk.Entry(frame, width=50, show="*")
        self.leg_secret.grid(row=1, column=1, pady=2)

        ttk.Label(frame, text="Fond:").grid(row=2, column=0, sticky='w', pady=2)
        self.leg_fond = ttk.Combobox(frame, values=["ALL", "JURI", "LEGI", "CNIL"], state="readonly")
        self.leg_fond.set("ALL")
        self.leg_fond.grid(row=2, column=1, sticky='w', pady=2)

        ttk.Label(frame, text="Valeur recherchée:").grid(row=3, column=0, sticky='w', pady=2)
        self.leg_valeur = ttk.Entry(frame, width=50)
        self.leg_valeur.grid(row=3, column=1, pady=2)

        ttk.Label(frame, text="Max Pages:").grid(row=4, column=0, sticky='w', pady=2)
        self.leg_pages = ttk.Entry(frame, width=10)
        self.leg_pages.insert(0, "10")
        self.leg_pages.grid(row=4, column=1, sticky='w', pady=2)

        self.btn_leg = ttk.Button(frame, text="▶ Lancer l'extraction", command=self.start_legifrance)
        self.btn_leg.grid(row=5, column=0, columnspan=2, pady=10)

        ttk.Label(self.tab_legifrance, text="Logs de l'extraction:").pack(anchor='w', padx=10)
        self.log_leg = scrolledtext.ScrolledText(self.tab_legifrance, height=15, state='disabled')
        self.log_leg.pack(expand=True, fill='both', padx=10, pady=5)

    def write_log_leg(self, message):
        self.log_leg.configure(state='normal')
        self.log_leg.insert(tk.END, message + "\n")
        self.log_leg.see(tk.END)
        self.log_leg.configure(state='disabled')
        self.update_idletasks()

    def start_legifrance(self):
        client = self.leg_client.get()
        secret = self.leg_secret.get()
        fond = self.leg_fond.get()
        valeur = self.leg_valeur.get()
        try: pages = int(self.leg_pages.get())
        except ValueError: pages = 10

        if not client or not secret:
            messagebox.showwarning("Attention", "Veuillez renseigner vos identifiants PISTE (Légifrance).")
            return

        self.btn_leg.config(state='disabled')
        self.log_leg.configure(state='normal')
        self.log_leg.delete('1.0', tk.END)
        self.log_leg.configure(state='disabled')

        def thread_task():
            run_legifrance_extraction(client, secret, fond, "ALL", valeur, pages, self.write_log_leg)
            self.after(0, lambda: self.btn_leg.config(state='normal'))

        threading.Thread(target=thread_task, daemon=True).start()

if __name__ == "__main__":
    app = ExtractorApp()
    app.mainloop()