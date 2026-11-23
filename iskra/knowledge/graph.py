"""Persistent knowledge graph domain model (latest unified-core implementation)."""
import json
import math
import os
import tempfile
import threading
import time
from contextlib import contextmanager

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

DATA_DIR = os.path.abspath(os.environ.get("DATA_DIR", os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
PLIK_SIECI = os.path.join(DATA_DIR, "wiedza.json")

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
