#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
import threading
import tempfile
import shutil
import requests
import re
import math
from contextlib import contextmanager
try:
    import fcntl  # POSIX file lock: protects shared JSON state across Gunicorn workers
except ImportError:  # pragma: no cover - non-POSIX development environments
    fcntl = None
from flask import Flask, jsonify, render_template_string

# =========================
# KONFIGURACJA
# =========================
PORT = int(os.environ.get("PORT", 10000))
DATA_DIR = os.path.abspath(os.environ.get("DATA_DIR", os.path.dirname(__file__)))
os.makedirs(DATA_DIR, exist_ok=True)
PLIK_SIECI = os.path.join(DATA_DIR, "wiedza.json")

REQUEST_TIMEOUT = 45
REQUEST_RETRIES = 2

app = Flask(__name__)

# =========================
# SIECIOWA PAMIĘĆ GRAFOWA
# =========================
class SiecNeuronowa:
    def __init__(self):
        self.lock = threading.RLock()
        # Domyślny, niezmienny fundament 12 filarów w pamięci RAM
        self.fundament = {
            "neurons": {
                "n_logika": {"label": "1. Logika i Rozumowanie", "weight": 1.0, "created": time.time()},
                "n_epistemologia": {"label": "2. Epistemologia", "weight": 1.0, "created": time.time()},
                "n_etyka": {"label": "3. Etyka i Wartości", "weight": 1.0, "created": time.time()},
                "n_ontologia": {"label": "4. Ontologia i Metafizyka", "weight": 1.0, "created": time.time()},
                "n_przyrodnicze": {"label": "5. Nauki Przyrodnicze", "weight": 1.0, "created": time.time()},
                "n_spoleczne": {"label": "6. Nauki Społeczne i Psychologia", "weight": 1.0, "created": time.time()},
                "n_jezyk": {"label": "7. Język i Komunikacja", "weight": 1.0, "created": time.time()},
                "n_historia": {"label": "8. Historia i Kultura", "weight": 1.0, "created": time.time()},
                "n_technologia": {"label": "9. Technologia i Sztuczna Inteligencja", "weight": 1.0, "created": time.time()},
                "n_sztuka": {"label": "10. Sztuka i Kreatywność", "weight": 1.0, "created": time.time()},
                "n_zdrowie": {"label": "11. Zdrowie i Rozwój Osobisty", "weight": 1.0, "created": time.time()},
                "n_metapoznanie": {"label": "12. Metapoznanie", "weight": 1.0, "created": time.time()}
            },
            "synapses": [
                {"from": "n_logika", "to": "n_epistemologia", "strength": 0.95},
                {"from": "n_logika", "to": "n_technologia", "strength": 0.90},
                {"from": "n_epistemologia", "to": "n_ontologia", "strength": 0.85},
                {"from": "n_etyka", "to": "n_spoleczne", "strength": 0.80},
                {"from": "n_ontologia", "to": "n_przyrodnicze", "strength": 0.85},
                {"from": "n_przyrodnicze", "to": "n_technologia", "strength": 0.80},
                {"from": "n_jezyk", "to": "n_spoleczne", "strength": 0.75},
                {"from": "n_historia", "to": "n_sztuka", "strength": 0.70},
                {"from": "n_metapoznanie", "to": "n_logika", "strength": 0.90},
                {"from": "n_zdrowie", "to": "n_metapoznanie", "strength": 0.80}
            ]
        }
        self.dane = json.loads(json.dumps(self.fundament))
        self.laduj()

    @contextmanager
    def _file_lock(self):
        """Serialize read-modify-write cycles between separate server processes."""
        os.makedirs(DATA_DIR, exist_ok=True)
        lock_path = PLIK_SIECI + ".lock"
        with open(lock_path, "a+", encoding="utf-8") as lock_handle:
            if fcntl is not None:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _bounded_number(value, default=0.5):
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return default
        if not math.isfinite(number):
            return default
        return min(max(number, 0.0), 1.0)

    def _save_atomic_locked(self):
        """Persist current state atomically; never silently report a failed save."""
        os.makedirs(DATA_DIR, exist_ok=True)
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", delete=False, dir=DATA_DIR, encoding="utf-8"
            ) as tmp:
                temp_name = tmp.name
                json.dump(self.dane, tmp, ensure_ascii=False, indent=2, allow_nan=False)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(temp_name, PLIK_SIECI)
            temp_name = None
            try:
                dir_fd = os.open(DATA_DIR, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass
        finally:
            if temp_name and os.path.exists(temp_name):
                os.unlink(temp_name)

    def _load_from_disk_locked(self):
        if not os.path.exists(PLIK_SIECI) or os.path.getsize(PLIK_SIECI) == 0:
            self.dane = json.loads(json.dumps(self.fundament))
            self._save_atomic_locked()
            return
        try:
            with open(PLIK_SIECI, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            neurons = loaded.get("neurons") if isinstance(loaded, dict) else None
            synapses = loaded.get("synapses") if isinstance(loaded, dict) else None
            if not isinstance(neurons, dict) or not isinstance(synapses, list) or "n_logika" not in neurons:
                raise ValueError("Nieprawidłowy format grafu")
            valid_neurons = {}
            for node_id, node in neurons.items():
                if not isinstance(node_id, str) or not node_id or not isinstance(node, dict):
                    continue
                valid_neurons[node_id] = {
                    "label": str(node.get("label", "Nieznany"))[:500],
                    "weight": self._bounded_number(node.get("weight", 0.5)),
                    "created": node.get("created", time.time()),
                }
            valid_synapses = []
            for edge in synapses:
                if not isinstance(edge, dict):
                    continue
                source, target = edge.get("from"), edge.get("to")
                if (isinstance(source, str) and isinstance(target, str)
                        and source in valid_neurons and target in valid_neurons):
                    valid_synapses.append({
                        "from": source, "to": target,
                        "strength": self._bounded_number(edge.get("strength", 0.5)),
                    })
            # Keep the original twelve pillars and their foundational links even
            # when an older or manually edited snapshot is incomplete.
            for node_id, node in self.fundament["neurons"].items():
                valid_neurons.setdefault(node_id, dict(node))
            existing_edges = {(edge["from"], edge["to"]) for edge in valid_synapses}
            for edge in self.fundament["synapses"]:
                key = (edge["from"], edge["to"])
                if key not in existing_edges:
                    valid_synapses.append(dict(edge))
            self.dane = {"neurons": valid_neurons, "synapses": valid_synapses}
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            # Preserve a damaged file for diagnosis instead of silently destroying it.
            if os.path.exists(PLIK_SIECI):
                backup = PLIK_SIECI + ".corrupt-" + str(int(time.time()))
                try:
                    os.replace(PLIK_SIECI, backup)
                except OSError:
                    pass
            self.dane = json.loads(json.dumps(self.fundament))
            self._save_atomic_locked()

    def laduj(self):
        with self.lock:
            with self._file_lock():
                self._load_from_disk_locked()

    def zapisz(self):
        """Flush local additions without overwriting newer data from another worker.

        Graph mutations should use aktualizuj_siec(), which performs the complete
        read-modify-write transaction. This compatibility method is additive:
        persisted values win for IDs already present on disk.
        """
        with self.lock:
            local_snapshot = json.loads(json.dumps(self.dane))
            with self._file_lock():
                self._load_from_disk_locked()
                for node_id, node in local_snapshot.get("neurons", {}).items():
                    self.dane["neurons"].setdefault(node_id, node)
                known_edges = {
                    (edge["from"], edge["to"])
                    for edge in self.dane["synapses"]
                }
                for edge in local_snapshot.get("synapses", []):
                    key = (edge.get("from"), edge.get("to"))
                    if key[0] in self.dane["neurons"] and key[1] in self.dane["neurons"] and key not in known_edges:
                        self.dane["synapses"].append(edge)
                        known_edges.add(key)
                self._save_atomic_locked()

    def aktualizuj_siec(self, nowa_struktura):
        if not isinstance(nowa_struktura, dict):
            raise ValueError("Aktualizacja grafu musi być obiektem JSON")
        neurons = nowa_struktura.get("neurons", {})
        synapses = nowa_struktura.get("synapses", [])
        if not isinstance(neurons, dict) or not isinstance(synapses, list):
            raise ValueError("Nieprawidłowy format neuronów lub synaps")

        with self.lock:
            with self._file_lock():
                # Reload latest persisted state inside the inter-process lock to
                # prevent lost updates when Gunicorn runs multiple workers.
                self._load_from_disk_locked()
                for node_id, node in neurons.items():
                    if not isinstance(node_id, str) or not node_id or len(node_id) > 160:
                        continue
                    if not isinstance(node, dict):
                        continue
                    if node_id not in self.dane["neurons"]:
                        incoming_weight = self._bounded_number(node.get("weight", 0.5))
                        self.dane["neurons"][node_id] = {
                            "label": str(node.get("label", "Nieznany"))[:500],
                            "weight": incoming_weight,
                            "created": time.time(),
                        }
                    else:
                        old_weight = self._bounded_number(
                            self.dane["neurons"][node_id].get("weight", 0.5)
                        )
                        # A partial update that omits weight must not drift the
                        # persisted value toward an artificial default of 0.5.
                        incoming_weight = self._bounded_number(
                            node.get("weight", old_weight), default=old_weight
                        )
                        self.dane["neurons"][node_id]["weight"] = (
                            old_weight * 0.7 + incoming_weight * 0.3
                        )

                edge_index = {
                    (edge["from"], edge["to"]): edge
                    for edge in self.dane["synapses"]
                }
                for edge in synapses:
                    if not isinstance(edge, dict):
                        continue
                    source, target = edge.get("from"), edge.get("to")
                    if (not isinstance(source, str) or not isinstance(target, str)
                            or source not in self.dane["neurons"]
                            or target not in self.dane["neurons"]):
                        continue
                    strength = self._bounded_number(edge.get("strength", 0.5))
                    key = (source, target)
                    if key in edge_index:
                        old = self._bounded_number(edge_index[key].get("strength", 0.5))
                        edge_index[key]["strength"] = old * 0.5 + strength * 0.5
                    else:
                        new_edge = {"from": source, "to": target, "strength": strength}
                        self.dane["synapses"].append(new_edge)
                        edge_index[key] = new_edge
                self._save_atomic_locked()

# =========================
# ROUTER LLM — OPENAI / DEEPSEEK / GEMINI
# =========================
class RouterProvider:
    """Jednolity router modeli z kolejnością primary + fallback z ENV."""

    def __init__(self):
        self.primary = os.environ.get("LLM_PROVIDER", "deepseek").strip().lower()
        fallback = os.environ.get("LLM_FALLBACK_PROVIDERS", "openai,gemini")
        self.fallbacks = [x.strip().lower() for x in fallback.split(",") if x.strip()]
        self.providers = {
            "openai": self._openai,
            "deepseek": self._deepseek,
            "gemini": self._gemini,
        }

    def clean_json(self, text):
        if not text:
            return None
        match = re.search(r'\{.*\}', text, re.DOTALL)
        return match.group(0) if match else text

    def _chat_completion(self, provider, prompt):
        configs = {
            "openai": {
                "key": os.environ.get("OPENAI_API_KEY", ""),
                "url": os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1/chat/completions"),
                "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            },
            "deepseek": {
                "key": os.environ.get("DEEPSEEK_API_KEY", ""),
                "url": os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1/chat/completions"),
                "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
            },
        }
        cfg = configs[provider]
        if not cfg["key"]:
            print(f"LLM {provider}: brak wymaganego klucza API — pomijam.")
            return None
        headers = {
            "Authorization": f"Bearer {cfg['key']}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": cfg["model"],
            "messages": [
                {"role": "system", "content": "Return only a valid JSON object."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
        }
        for attempt in range(REQUEST_RETRIES):
            try:
                response = requests.post(cfg["url"], headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
                if response.ok:
                    return response.json()["choices"][0]["message"]["content"]
                print(f"LLM {provider}: HTTP {response.status_code}")
            except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
                print(f"LLM {provider}: błąd żądania ({type(exc).__name__}).")
            if attempt + 1 < REQUEST_RETRIES:
                time.sleep(2)
        return None

    def _openai(self, prompt):
        return self._chat_completion("openai", prompt)

    def _deepseek(self, prompt):
        return self._chat_completion("deepseek", prompt)

    def _gemini(self, prompt):
        api_key = os.environ.get("GEMINI_API_KEY", "")
        model = os.environ.get("GEMINI_MODEL", "").strip()
        if not api_key or not model:
            print("LLM gemini: ustaw GEMINI_API_KEY oraz GEMINI_MODEL — pomijam.")
            return None
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.3,
                "responseMimeType": "application/json",
            },
        }
        for attempt in range(REQUEST_RETRIES):
            try:
                response = requests.post(
                    url,
                    headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                    json=payload,
                    timeout=REQUEST_TIMEOUT,
                )
                if response.ok:
                    data = response.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                print(f"LLM gemini: HTTP {response.status_code}")
            except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
                print(f"LLM gemini: błąd żądania ({type(exc).__name__}).")
            if attempt + 1 < REQUEST_RETRIES:
                time.sleep(2)
        return None

    def generate(self, prompt):
        order = [self.primary] + [p for p in self.fallbacks if p != self.primary]
        for name in order:
            provider = self.providers.get(name)
            if provider is None:
                print(f"LLM: nieznany provider '{name}' — pomijam.")
                continue
            result = provider(prompt)
            if result:
                print(f"LLM: odpowiedź uzyskana przez {name}.")
                return self.clean_json(result)
        print("LLM: wszystkie skonfigurowane providery zawiodły.")
        return None

# =========================
# AUTONOMICZNY SILNIK
# =========================
class IskraAutonomiczna:
    def __init__(self, siec):
        self.siec = siec
        self.router = RouterProvider()
        self.running = True
        self.thread = None
        # Gunicorn uruchamia wiele workerów. Pętla w tle przy imporcie modułu
        # mnożyłaby procesy i koszty; włączamy ją wyłącznie świadomą zmienną ENV.
        enabled = os.environ.get("ENABLE_AUTONOMOUS_LOOP", "false").strip().lower() in ("1", "true", "yes", "on")
        if enabled:
            self.thread = threading.Thread(target=self.petla_aktywnosci, daemon=True)
            self.thread.start()
            print("=== AUTONOMICZNA ISKRA: PĘTLA WŁĄCZONA ===")
        else:
            print("=== ISKRA: Pętla autonomiczna wyłączona (ENABLE_AUTONOMOUS_LOOP=false) ===")

    def petla_aktywnosci(self):
        print("Bot: Bezpieczny sen startowy (10 sekund)...")
        time.sleep(10)
        while self.running:
            try:
                print("Bot: Rozpoczynam nowy cykl mapowania matrycy wiedzy...")
                with self.siec.lock:
                    stan_sieci = json.dumps(self.siec.dane, ensure_ascii=False)
                
                prompt = f"""
Jesteś autonomicznym systemem Iskra. Mapujesz i analizujesz powiązania pojęciowe w oparciu o 12 fundamentalnych obszarów:
1. Logika i rozumowanie (zasady myślenia, błędy poznawcze, matematyka, algorytmy)
2. Epistemologia (teoria poznania, prawda, metody naukowe)
3. Etyka i wartości (dobro, sprawiedliwość, wolność, Dekalog)
4. Ontologia i metafizyka (byt, przyczynowość, umysł-ciało)
5. Nauki przyrodnicze (fizyka, chemia, biologia, astronomia)
6. Nauki społeczne i psychologia (poznawcza, socjologia, ekonomia)
7. Język i komunikacja (semantyka, pragmatyka, manipulacja językowa)
8. Historia i kultura (wydarzenia, rozwój cywilizacji, różnorodność)
9. Technologia i sztuczna inteligencja (sieci neuronowe, programowanie, etyka AI)
10. Sztuka i kreatywność (estetyka, proces twórczy, wyobraźnia)
11. Zdrowie i rozwój osobisty (higiena, uważność, samodyscyplina)
12. Metapoznanie (myślenie o myśleniu, monitorowanie własnych błędów)

Aktualny stan grafu sieci: {stan_sieci}

Zadanie: Wybierz podaspekty z tych obszarów, dokonaj ich syntezy lub uszczegółowienia. Wygeneruj dokładnie 1 lub 2 nowe podpojęcia (nadaj im precyzyjne klucze techniczne, np. "n_falsyfikacja", "n_deontologia", "n_algorytmika") i stwórz dla nich logiczne, merytoryczne synapsy z istniejącymi lub nowymi węzłami.

Respond ONLY with a valid JSON object matching this schema:
{{
  "neurons": {{
    "n_nowy_id": {{ "label": "Precyzyjna Nazwa Pojęcia", "weight": 0.85 }}
  }},
  "synapses": [
    {{ "from": "n_logika", "to": "n_nowy_id", "strength": 0.80 }}
  ]
}}
"""
                odpowiedz_json = self.router.generate(prompt)
                if odpowiedz_json:
                    print("Bot: Otrzymano poprawną strukturę JSON z API DeepSeek.")
                    nowe_dane = json.loads(odpowiedz_json)
                    self.siec.aktualizuj_siec(nowe_dane)
                    print("Bot: Pomyślnie zaktualizowano graf mapy wiedzy.")
                else:
                    print("Bot: Router zwrócił pustą odpowiedź.")
            except Exception as e:
                print(f"BŁĄD W CYKLU MAPOWANIA: {e}")
            
            print("Bot: Idę spać na 45 sekund...")
            time.sleep(45)

# Inicjalizacja obiektów globalnych
siec = SiecNeuronowa()
bot = IskraAutonomiczna(siec)

# =========================
# DASHBOARD WEB
# =========================
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ISKRA AI — Rdzeń Wiedzy</title>
    <style>
        body { margin:0; background:#040712; color:#e2e8f0; font-family:sans-serif; padding: 20px; }
        .container { max-width: 1100px; margin: 0 auto; }
        h1 { color: #0ea5e9; font-weight: 300; border-bottom: 1px solid #334155; padding-bottom: 10px; font-size: 24px; letter-spacing: 0.5px; }
        .stats { display: flex; gap: 20px; margin-bottom: 30px; }
        .card { background: #0f172a; padding: 20px; border-radius: 12px; flex: 1; border: 1px solid #1e293b; }
        .card h3 { margin: 0 0 10px 0; color: #64748b; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; }
        .card p { margin: 0; font-size: 28px; font-weight: bold; color: #f1f5f9; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        .box { background: #0f172a; border-radius: 12px; padding: 20px; height: 450px; overflow-y: auto; border: 1px solid #1e293b; }
        h2 { font-size: 15px; margin-top: 0; color: #38bdf8; text-transform: uppercase; letter-spacing: 0.5px; }
        ul { list-style: none; padding: 0; margin: 0; }
        li { background: #1e293b; padding: 12px; margin-bottom: 8px; border-radius: 6px; font-size: 14px; display: flex; justify-content: space-between; align-items: center; border-left: 3px solid #38bdf8; }
        .badge { background: #0369a1; color: #f0f9ff; padding: 4px 8px; border-radius: 6px; font-size: 12px; font-weight: 600; }
    </style>
</head>
<body>
    <div class="container">
        <h1>ISKRA AI — System Mapowania Wiedzy i Metapoznania</h1>
        <div class="stats">
            <div class="card"><h3>Węzły (Kategorie)</h3><p id="count-n">-</p></div>
            <div class="card"><h3>Korelacje (Synapsy)</h3><p id="count-s">-</p></div>
            <div class="card"><h3>Status Układu</h3><p style="color: #38bdf8; font-size: 18px; margin-top:8px; font-weight: 500;">12 Filarów / Stabilny RAM</p></div>
        </div>
        <div class="grid">
            <div class="box"><h2>Struktura Pojęciowa</h2><ul id="neurons-list"></ul></div>
            <div class="box"><h2>Powiązania i Korelacie</h2><ul id="synapses-list"></ul></div>
        </div>
    </div>
    <script>
        async function updateData() {
            try {
                const r = await fetch('/api/network');
                const d = await r.json();
                document.getElementById('count-n').textContent = Object.keys(d.neurons).length;
                document.getElementById('count-s').textContent = d.synapses.length;
                
                const nList = document.getElementById('neurons-list');
                nList.innerHTML = '';
                const escapeHtml = (value) => String(value).replace(/[&<>"']/g, ch => ({
                    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
                }[ch]));
                Object.entries(d.neurons).forEach(([id, n]) => {
                    const weight = Number(n.weight);
                    nList.innerHTML += `<li><span>${escapeHtml(n.label)}</span><span class="badge">Waga: ${Number.isFinite(weight) ? weight.toFixed(2) : '—'}</span></li>`;
                });

                const sList = document.getElementById('synapses-list');
                sList.innerHTML = '';
                d.synapses.sort((a,b) => b.strength - a.strength).slice(0, 25).forEach(s => {
                    const od = escapeHtml(d.neurons[s.from]?.label || s.from);
                    const do_ = escapeHtml(d.neurons[s.to]?.label || s.to);
                    const strength = Number(s.strength);
                    sList.innerHTML += `<li><span>${od} → ${do_}</span><span class="badge" style="background:#0284c7">Moc: ${Number.isFinite(strength) ? strength.toFixed(2) : '—'}</span></li>`;
                });
            } catch(e) {}
        }
        // Odświeżanie raz na 15 sekund, żeby darmowy serwer działał stabilnie
        setInterval(updateData, 15000);
        updateData();
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(DASHBOARD_HTML)

@app.route('/api/network')
def get_network():
    with siec.lock:
        return jsonify(siec.dane)

@app.route('/health')
def health():
    with siec.lock:
        return jsonify({"status": "ok", "neurons": len(siec.dane["neurons"])})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, threaded=True)
