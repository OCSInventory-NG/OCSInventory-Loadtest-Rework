"""
Static, fixed reference list of company sites (agencies/cities).

Shared by locustfiles that need consistent, site-based reference data
across runs (asset TAGs, IPDiscover network topology, ...) so the same
site codes/names are used everywhere instead of being duplicated and
possibly drifting between files.
"""

SITES = [
    {"code": "PAR", "city": "Paris"},
    {"code": "LYO", "city": "Lyon"},
    {"code": "MRS", "city": "Marseille"},
    {"code": "BOR", "city": "Bordeaux"},
    {"code": "LIL", "city": "Lille"},
    {"code": "NAN", "city": "Nantes"},
    {"code": "TLS", "city": "Toulouse"},
    {"code": "REN", "city": "Rennes"},
]
