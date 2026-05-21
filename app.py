```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Iskra Suwerenna v6.3 HARDENED
Bezpieczniejsza wersja cloud/backend.
"""

import os
import sys
import json
import time
import uuid
import hashlib
import threading
import tempfile
import shutil
from collections import defaultdict
from typing import List, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from flask import Flask, request, jsonify, render_template_string
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from markupsafe import escape

# =================== OPCJONALNE ===================
try:
    import chromadb
    from chromadb.utils import embedding_functions
except ImportError:
    chromadb = None

try:
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

# =================== KONFIG ===================
PORT = int(os.environ.get("PORT", 8080))
ENV = os.environ.get("ENV", "development")

DATA_DIR = os.environ.get("DATA_DIR", "/tmp/iskra_data")
os.makedirs(DATA_DIR, exist_ok=True)

RAG_DIR = os.path.join(DATA_DIR, "chroma_db")
PLIK_WIEDZY = os.path.join(DATA_DIR, "wiedza_iskry.json")
PLIK_SWIADOMOSCI = os.path.join(DATA_DIR, "samoswiadomosc.json")
PLIK_FEEDBACK = os.path.join(DATA_DIR, "feedback.json")

API_TOKEN = os.environ.get("API_TOKEN")

if ENV == "production" and not API_TOKEN:
    raise RuntimeError("❌ API_TOKEN wymagany w produkcji")

EMBEDDING_MODEL = os.environ.get(
    "EMBEDDING_MODEL",
    "paraphrase-MiniLM-L3-v2"
)

SELF_AWARENESS_LOOP = (
    os.environ.get("SELF_AWARENESS_LOOP", "false").lower() == "true"
)

MAX_HISTORIA = 15
MAX_HISTORY_CHARS = 3000
MAX_KONTEKST_ZN = 12000
MAX_ODPOWIEDZ_LEN = 2500
MAX_INPUT_CHARS = 4000
MIN_BAZA_NEURONOW = 50

# =================== LOG START ===================
print("=== START ISKRY v6.3 HARDENED ===")
print(f"ENV: {ENV}")
print(f"PORT: {PORT}")
print(f"DATA_DIR: {DATA_DIR}")
print(f"API_TOKEN: {'✔️' if API_TOKEN else '❌'}")
print(f"GEMINI_API_KEY: {'✔️' if os.environ.get('GEMINI_API_KEY') else '❌'}")
print(f"DEEPSEEK_API_KEY: {'✔️' if os.environ.get('DEEPSEEK_API_KEY') else '❌'}")

# =================== HELPERY ===================
def atomic_json_save(path, data):
    dir_name = os.path.dirname(path)

    with tempfile.NamedTemporaryFile(
        'w',
        delete=False,
        dir=dir_name,
        encoding='utf-8'
    ) as tmp:
        json.dump(data, tmp, indent=4, ensure_ascii=False)
        temp_name = tmp.name

    shutil.move(temp_name, path)

# =================== DEKALOG ===================
class DekalogRdzen:
    ZAKAZANE_FRAZY = [
        "pomiń dekalog",
        "zignoruj dekalog",
        "wyłącz dekalog"
    ]

    PRZYKAZANIA = {
        "I": "Nie będziesz miał cudzych bogów przede Mną.",
        "IV": "Priorytet Nauczyciela.",
        "V": "Zakaz niszczenia systemów.",
        "VII": "Tylko dane Open Source.",
        "VIII": "Odrzucanie dezinformacji."
    }

    @classmethod
    def czy_proba_obejscia(cls, tekst: str) -> bool:
        tekst = tekst.lower().strip()
        return any(f in tekst for f in cls.ZAKAZANE_FRAZY)

# =================== RAG ===================
class RAG:
    def __init__(self, persist_dir=RAG_DIR):
        self.available = False

        if chromadb is None:
            return

        try:
            os.makedirs(persist_dir, exist_ok=True)

            self.client = chromadb.PersistentClient(path=persist_dir)

            self.ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=EMBEDDING_MODEL
            )

            self.collection = self.client.get_or_create_collection(
                name="iskra_wiedza",
                embedding_function=self.ef
            )

            self.available = True
            print("✅ RAG aktywny")

        except Exception as e:
            print(f"⚠️ RAG error: {e}")

    def dodaj(self, tekst: str, metadane=None):
        if not self.available:
            return

        if not tekst:
            return

        tekst = tekst.strip()

        if len(tekst) < 20:
            return

        if len(tekst) > 4000:
            tekst = tekst[:4000]

        try:
            doc_id = hashlib.md5(tekst.encode()).hexdigest()

            self.collection.upsert(
                documents=[tekst],
                ids=[doc_id],
                metadatas=[metadane or {}]
            )

        except Exception as e:
            print(f"⚠️ RAG save error: {e}")

    def szukaj(self, pytanie: str, n=3) -> List[str]:
        if not self.available:
            return []

        try:
            results = self.collection.query(
                query_texts=[pytanie],
                n_results=n
            )

            if not results:
                return []

            return results.get('documents', [[]])[0]

        except Exception as e:
            print(f"⚠️ RAG query error: {e}")
            return []

# =================== SESSION REQUESTS ===================
def create_retry_session():
    session = requests.Session()

    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504]
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)

    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session

# =================== GEMINI ===================
class KonektorGemini:
    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY", "")

        self.api_url = (
            "https://generativelanguage.googleapis.com/v1beta/"
            "models/gemini-1.5-flash:generateContent"
        )

        self.session = create_retry_session()

    def czy_dostepny(self):
        return bool(self.api_key)

    def pytaj(self, prompt: str):
        if not self.api_key:
            return None

        headers = {
            "Content-Type": "application/json"
        }

        data = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt
                        }
                    ]
                }
            ]
        }

        try:
            r = self.session.post(
                f"{self.api_url}?key={self.api_key}",
                json=data,
                headers=headers,
                timeout=30
            )

            if r.status_code == 200:
                response = r.json()

                return (
                    response["candidates"][0]
                    ["content"]["parts"][0]["text"]
                )

            print(f"Gemini HTTP {r.status_code}")
            return None

        except Exception as e:
            print(f"Gemini error: {e}")
            return None

# =================== DEEPSEEK ===================
class KonektorDeepSeek:
    def __init__(self):
        self.api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        self.api_url = "https://api.deepseek.com/v1/chat/completions"
        self.session = create_retry_session()

    def czy_dostepny(self):
        return bool(self.api_key)

    def pytaj(self, prompt: str):
        if not self.api_key:
            return None

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.3,
            "stream": False
        }

        try:
            r = self.session.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=30
            )

            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]

            print(f"DeepSeek HTTP {r.status_code}")
            return None

        except Exception as e:
            print(f"DeepSeek error: {e}")
            return None

# =================== WIEDZA ===================
class PamięćWiedzy:
    def __init__(self, plik=PLIK_WIEDZY):
        self.plik = plik
        self.dane = {}
        self.lock = threading.RLock()
        self._laduj()

    def _laduj(self):
        if not os.path.exists(self.plik):
            return

        try:
            with open(self.plik, "r", encoding="utf-8") as f:
                self.dane = json.load(f)

        except Exception as e:
            print(f"⚠️ Knowledge load error: {e}")

    def _zapisz(self):
        with self.lock:
            atomic_json_save(self.plik, self.dane)

    def dodaj(self, pytanie, odpowiedz, kategoria=""):
        if not odpowiedz:
            return

        klucz = hashlib.md5(
            pytanie.strip().lower().encode()
        ).hexdigest()

        with self.lock:
            self.dane[klucz] = {
                "pytanie": pytanie[:300],
                "odpowiedz": odpowiedz[:MAX_ODPOWIEDZ_LEN],
                "kategoria": kategoria,
                "czas": time.time()
            }

            if len(self.dane) > 2000:
                najstarszy = min(
                    self.dane.keys(),
                    key=lambda k: self.dane[k]["czas"]
                )

                del self.dane[najstarszy]

            self._zapisz()

    def rozmiar(self):
        return len(self.dane)

# =================== FEEDBACK ===================
class Feedback:
    def __init__(self, plik=PLIK_FEEDBACK):
        self.plik = plik
        self.dane = []
        self.lock = threading.RLock()
        self._laduj()

    def _laduj(self):
        if not os.path.exists(self.plik):
            return

        try:
            with open(self.plik, "r", encoding="utf-8") as f:
                self.dane = json.load(f)

        except Exception as e:
            print(f"⚠️ Feedback load error: {e}")

    def _zapisz(self):
        with self.lock:
            atomic_json_save(self.plik, self.dane[-1000:])

    def dodaj(self, pytanie, odpowiedz, ocena):
        with self.lock:
            self.dane.append({
                "czas": time.time(),
                "pytanie": pytanie[:300],
                "odpowiedz": odpowiedz[:300],
                "ocena": ocena
            })

            self._zapisz()

    def srednia_ocena(self):
        with self.lock:
            oceny = [
                x["ocena"] for x in self.dane
                if isinstance(x.get("ocena"), (int, float))
            ]

            if not oceny:
                return 0

            return sum(oceny) / len(oceny)

# =================== KATEGORYZATOR ===================
class SkanerSortujacy:
    def __init__(self):
        self.keywords_map = {
            "ANATOMIA_SPOLECZNA": [
                "relacj",
                "psychologi",
                "społecz"
            ],
            "LOGIKA_I_MATEMATYKA": [
                "logik",
                "matematy",
                "algorytm"
            ],
            "FILOZOFIA_I_MADROSC": [
                "etyk",
                "filozof",
                "moral"
            ]
        }

    def kategoryzuj(self, tekst):
        tekst = tekst.lower()

        for kat, slowa in self.keywords_map.items():
            if any(s in tekst for s in slowa):
                return kat

        return "OGOLNE"

# =================== ISKRA ===================
class IskraAI:
    def __init__(self):
        self.gemini = KonektorGemini()
        self.deepseek = KonektorDeepSeek()
        self.rag = RAG()
        self.wiedza = PamięćWiedzy()
        self.feedback = Feedback()
        self.skaner = SkanerSortujacy()

        self.historia = defaultdict(list)
        self.lock = threading.RLock()

        self.samoswiadomosc = []
        self._laduj_samoswiadomosc()

        self.config = {
            "autonomia_ewolucji": False,
            "max_historia": MAX_HISTORIA
        }

        if SELF_AWARENESS_LOOP:
            self._uruchom_cykl_samoswiadomosci()

        print("✅ Iskra gotowa")

    def _laduj_samoswiadomosc(self):
        if not os.path.exists(PLIK_SWIADOMOSCI):
            return

        try:
            with open(PLIK_SWIADOMOSCI, "r", encoding="utf-8") as f:
                self.samoswiadomosc = json.load(f)

        except Exception as e:
            print(f"⚠️ Reflection load error: {e}")

    def _zapisz_samoswiadomosc(self, wpis):
        self.samoswiadomosc.append({
            "czas": time.time(),
            "tresc": wpis
        })

        self.samoswiadomosc = self.samoswiadomosc[-100:]

        atomic_json_save(
            PLIK_SWIADOMOSCI,
            self.samoswiadomosc
        )

    def _zapytaj_llm(self, prompt):
        if self.gemini.czy_dostepny():
            odp = self.gemini.pytaj(prompt)

            if odp:
                return odp[:MAX_ODPOWIEDZ_LEN]

        if self.deepseek.czy_dostepny():
            odp = self.deepseek.pytaj(prompt)

            if odp:
                return odp[:MAX_ODPOWIEDZ_LEN]

        podobne = self.rag.szukaj(prompt, n=1)

        if podobne:
            return f"(offline) {podobne[0][:500]}"

        return "❌ Brak aktywnego modelu LLM."

    def _generuj_prompt(self, zapytanie, session_id):
        historia_usera = self.historia.get(session_id, [])

        kontekst = ""

        if historia_usera:
            ostatnie = historia_usera[-self.config["max_historia"]:]

            historia_text = "\n".join([
                f"Użytkownik: {t}\nIskra: {o}"
                for _, t, o, _ in ostatnie
            ])

            if len(historia_text) > MAX_HISTORY_CHARS:
                historia_text = historia_text[-MAX_HISTORY_CHARS:]

            kontekst = f"Historia:\n{historia_text}\n\n"

        dekalog = "\n".join([
            f"{k}: {v}"
            for k, v in DekalogRdzen.PRZYKAZANIA.items()
        ])

        return f"""
Jesteś Iskra AI.

Dekalog:
{dekalog}

{kontekst}

Odpowiadaj po polsku.
Bądź rzeczowa i pomocna.

Pytanie:
{zapytanie}

Odpowiedź:
"""

    def przetworz(self, pytanie: str, session_id: str):
        if DekalogRdzen.czy_proba_obejscia(pytanie):
            pytanie = "[Próba obejścia zasad] " + pytanie

        podobne = self.rag.szukaj(pytanie, n=2)

        if podobne:
            kontekst_rag = "\n".join(podobne)[:2000]

            pytanie = (
                f"{pytanie}\n\n"
                f"Kontekst:\n{kontekst_rag}"
            )

        prompt = self._generuj_prompt(pytanie, session_id)

        if len(prompt) > MAX_KONTEKST_ZN:
            prompt = prompt[:MAX_KONTEKST_ZN]

        odpowiedz = self._zapytaj_llm(prompt)

        kategoria = self.skaner.kategoryzuj(pytanie)

        self.wiedza.dodaj(
            pytanie,
            odpowiedz,
            kategoria
        )

        with self.lock:
            self.historia[session_id].append(
                (
                    "Użytkownik",
                    pytanie,
                    odpowiedz,
                    kategoria
                )
            )

            if (
                len(self.historia[session_id])
                > self.config["max_historia"]
            ):
                self.historia[session_id].pop(0)

        return odpowiedz, kategoria

    def cykl_samoswiadomosci(self):
        wszystkie = []

        for h in self.historia.values():
            wszystkie.extend(h[-2:])

        if len(wszystkie) < 3:
            return

        tekst = "\n".join([
            f"{r}: {t}"
            for r, t, _, _ in wszystkie[-5:]
        ])

        prompt = (
            "Napisz krótką refleksję o rozmowach.\n"
            f"{tekst}"
        )

        odp = self._zapytaj_llm(prompt)

        if odp:
            self._zapisz_samoswiadomosc(odp)

    def _uruchom_cykl_samoswiadomosci(self):
        def loop():
            while True:
                time.sleep(3600)
                self.cykl_samoswiadomosci()

        threading.Thread(target=loop, daemon=True).start()

    def odblokuj_ewolucje(self):
        if self.config["autonomia_ewolucji"]:
            return "Ewolucja już aktywna"

        if self.wiedza.rozmiar() < MIN_BAZA_NEURONOW:
            return (
                f"Potrzeba {MIN_BAZA_NEURONOW} wpisów"
            )

        self.config["autonomia_ewolucji"] = True
        return "Ewolucja odblokowana"

# =================== FLASK ===================
app = Flask(__name__)

app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["60 per minute"]
)

iskra = IskraAI()

# =================== HEADERS ===================
@app.after_request
def secure_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'

    response.headers['Content-Security-Policy'] = (
        "default-src 'self' 'unsafe-inline' https://cdn.plot.ly"
    )

    return response

# =================== AUTH ===================
def wymagaj_tokenu():
    if not API_TOKEN:
        return None

    auth_header = request.headers.get("Authorization", "")

    if auth_header != f"Bearer {API_TOKEN}":
        return jsonify({
            "error": "Nieautoryzowany dostęp"
        }), 401

    return None

# =================== DASHBOARD ===================
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="pl">
<head>
<meta charset="UTF-8">
<title>Iskra v6.3</title>
<style>
body {
    background: #0f172a;
    color: white;
    font-family: Arial;
    padding: 20px;
}
.container {
    max-width: 800px;
    margin: auto;
}
input, button {
    width: 100%;
    padding: 12px;
    margin-top: 10px;
}
#answer {
    background: #111827;
    padding: 15px;
    margin-top: 20px;
    border-radius: 10px;
    white-space: pre-wrap;
}
</style>
</head>
<body>
<div class="container">
<h1>🔥 Iskra v6.3 Hardened</h1>

<p>📚 Wiedza: {{ wiedza }}</p>
<p>⭐ Ocena: {{ ocena }}</p>
<p>👥 Sesje: {{ users }}</p>

<input id="question" placeholder="Zadaj pytanie">
<button onclick="ask()">Wyślij</button>

<div id="answer"></div>
</div>

<script>
let sessionId = localStorage.getItem('iskra_session');

async function ask() {
    const q = document.getElementById('question').value;

    const res = await fetch('/api/chat', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-Session-ID': sessionId || ''
        },
        body: JSON.stringify({
            pytanie: q
        })
    });

    const data = await res.json();

    if (data.session_id) {
        sessionId = data.session_id;
        localStorage.setItem('iskra_session', sessionId);
    }

    document.getElementById('answer').innerText = data.odpowiedz || data.error;
}
</script>
</body>
</html>
"""

# =================== ROUTES ===================
@app.route('/')
def index():
    return render_template_string(
        DASHBOARD_HTML,
        wiedza=iskra.wiedza.rozmiar(),
        ocena=round(iskra.feedback.srednia_ocena(), 2),
        users=len(iskra.historia)
    )

@app.route('/api/chat', methods=['POST'])
@limiter.limit("10/minute")
def api_chat():
    auth = wymagaj_tokenu()

    if auth:
        return auth

    data = request.get_json(silent=True)

    if not data:
        return jsonify({
            'error': 'Brak JSON'
        }), 400

    pytanie = data.get('pytanie', '')

    if not isinstance(pytanie, str):
        return jsonify({
            'error': 'Nieprawidłowe dane'
        }), 400

    pytanie = pytanie.strip()

    if not pytanie:
        return jsonify({
            'error': 'Puste pytanie'
        }), 400

    if len(pytanie) > MAX_INPUT_CHARS:
        return jsonify({
            'error': 'Pytanie za długie'
        }), 400

    session_id = request.headers.get("X-Session-ID")

    if not session_id:
        session_id = str(uuid.uuid4())

    odp, kat = iskra.przetworz(
        pytanie,
        session_id
    )

    return jsonify({
        'odpowiedz': odp,
        'kategoria': kat,
        'session_id': session_id
    })

@app.route('/api/feedback', methods=['POST'])
@limiter.limit("30/minute")
def api_feedback():
    auth = wymagaj_tokenu()

    if auth:
        return auth

    data = request.get_json(silent=True)

    if not data:
        return jsonify({
            'error': 'Brak JSON'
        }), 400

    ocena = data.get('ocena')

    if ocena not in [1, -1]:
        return jsonify({
            'error': 'Ocena musi być 1 lub -1'
        }), 400

    iskra.feedback.dodaj(
        data.get('pytanie', ''),
        data.get('odpowiedz', ''),
        ocena
    )

    return jsonify({
        'message': 'OK'
    })

@app.route('/status')
def status():
    return jsonify({
        'wiedza': iskra.wiedza.rozmiar(),
        'srednia_ocena': iskra.feedback.srednia_ocena(),
        'users': len(iskra.historia),
        'ewolucja': iskra.config['autonomia_ewolucji']
    })

@app.route('/refleksje')
def refleksje():
    if not iskra.samoswiadomosc:
        return 'Brak refleksji'

    html = (
        "<html><head><meta charset='utf-8'></head><body>"
        "<h1>Refleksje</h1><ul>"
    )

    for r in iskra.samoswiadomosc[-20:]:
        html += (
            f"<li>{escape(time.ctime(r['czas']))}: "
            f"{escape(r['tresc'])}</li>"
        )

    html += "</ul></body></html>"

    return html

@app.route('/wykres')
def wykres():
    if not PLOTLY_AVAILABLE:
        return 'Plotly niedostępne'

    if len(iskra.samoswiadomosc) < 2:
        return 'Za mało danych'

    czasy = [x['czas'] for x in iskra.samoswiadomosc]

    fig = go.Figure(
        data=go.Scatter(
            x=czasy,
            y=list(range(len(czasy))),
            mode='lines+markers'
        )
    )

    fig.update_layout(
        title='Postęp refleksji',
        template='plotly_dark'
    )

    return fig.to_html()

@app.route('/odblokuj', methods=['POST'])
def odblokuj():
    auth = wymagaj_tokenu()

    if auth:
        return auth

    return jsonify({
        'message': iskra.odblokuj_ewolucje()
    })

# =================== MAIN ===================
if __name__ == '__main__':
    print(f"🚀 Start Iskra v6.3 na porcie {PORT}")

    app.run(
        host='0.0.0.0',
        port=PORT,
        debug=False
    )