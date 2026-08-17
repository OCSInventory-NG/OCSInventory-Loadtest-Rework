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


def subnet_cidrs(site_idx):
    """
    The office-LAN / server-room CIDRs for one site, by its index in
    SITES - same "10.{10+idx}.1.0/24" / "10.{10+idx}.2.0/24" convention
    ipd_netgroup.py's build_topology() uses for its netid/mask pairs, so
    anything referencing a site's subnets (e.g. ipd_snmp.py's SnmpConfig/
    SnmpScanner) stays consistent with the actual seeded IPDiscover
    topology instead of inventing unrelated ranges.
    """
    second_octet = 10 + site_idx
    return [f"10.{second_octet}.1.0/24", f"10.{second_octet}.2.0/24"]
