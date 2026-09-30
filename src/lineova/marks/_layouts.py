"""Tile-map layouts: each region is one equal-sized tile placed roughly where it is on a map.

A layout maps a code to ``(column, row, name, aliases)``. Values can be joined by code,
by name (accents and case ignored) or by any alias (e.g. INE province numbers).
"""

from __future__ import annotations

import unicodedata

# Spanish provinces: vehicle-plate style codes; aliases are INE province numbers and common names
ES_PROVINCES = {
    "C": (0, 0, "A Coruña", ("15", "La Coruña", "Coruña")),
    "LU": (1, 0, "Lugo", ("27",)),
    "O": (2, 0, "Asturias", ("33", "Oviedo")),
    "S": (3, 0, "Cantabria", ("39", "Santander")),
    "BI": (4, 0, "Bizkaia", ("48", "Vizcaya")),
    "SS": (5, 0, "Gipuzkoa", ("20", "Guipúzcoa")),
    "NA": (6, 0, "Navarra", ("31", "Nafarroa")),
    "HU": (7, 0, "Huesca", ("22",)),
    "L": (8, 0, "Lleida", ("25", "Lérida")),
    "GI": (9, 0, "Girona", ("17", "Gerona")),
    "PO": (0, 1, "Pontevedra", ("36",)),
    "OU": (1, 1, "Ourense", ("32", "Orense")),
    "LE": (2, 1, "León", ("24",)),
    "P": (3, 1, "Palencia", ("34",)),
    "BU": (4, 1, "Burgos", ("09", "9")),
    "VI": (5, 1, "Araba/Álava", ("01", "1", "Álava", "Araba")),
    "LO": (6, 1, "La Rioja", ("26", "Rioja", "Logroño")),
    "Z": (7, 1, "Zaragoza", ("50",)),
    "T": (8, 1, "Tarragona", ("43",)),
    "B": (9, 1, "Barcelona", ("08", "8")),
    "ZA": (1, 2, "Zamora", ("49",)),
    "VA": (2, 2, "Valladolid", ("47",)),
    "SG": (3, 2, "Segovia", ("40",)),
    "SO": (4, 2, "Soria", ("42",)),
    "GU": (5, 2, "Guadalajara", ("19",)),
    "TE": (6, 2, "Teruel", ("44",)),
    "CS": (7, 2, "Castellón", ("12", "Castelló", "Castellón/Castelló")),
    "SA": (1, 3, "Salamanca", ("37",)),
    "AV": (2, 3, "Ávila", ("05", "5")),
    "M": (3, 3, "Madrid", ("28",)),
    "CU": (4, 3, "Cuenca", ("16",)),
    "V": (5, 3, "Valencia", ("46", "València")),
    "PM": (7, 3, "Illes Balears", ("07", "7", "Baleares", "Islas Baleares", "IB")),
    "CC": (1, 4, "Cáceres", ("10",)),
    "TO": (2, 4, "Toledo", ("45",)),
    "CR": (3, 4, "Ciudad Real", ("13",)),
    "AB": (4, 4, "Albacete", ("02", "2")),
    "A": (5, 4, "Alicante", ("03", "3", "Alacant", "Alicante/Alacant")),
    "BA": (1, 5, "Badajoz", ("06", "6")),
    "CO": (2, 5, "Córdoba", ("14",)),
    "J": (3, 5, "Jaén", ("23",)),
    "MU": (4, 5, "Murcia", ("30",)),
    "H": (0, 6, "Huelva", ("21",)),
    "SE": (1, 6, "Sevilla", ("41",)),
    "MA": (2, 6, "Málaga", ("29",)),
    "GR": (3, 6, "Granada", ("18",)),
    "AL": (4, 6, "Almería", ("04", "4")),
    "CA": (1, 7, "Cádiz", ("11",)),
    "TF": (0, 8.4, "S. C. de Tenerife", ("38", "Santa Cruz de Tenerife", "Tenerife")),
    "GC": (1, 8.4, "Las Palmas", ("35", "Gran Canaria")),
    "CE": (2.6, 8.4, "Ceuta", ("51",)),
    "ML": (3.6, 8.4, "Melilla", ("52",)),
}

# Spanish autonomous communities (ISO 3166-2:ES codes)
ES_REGIONS = {
    "GA": (0, 0, "Galicia", ("ES-GA", "12")),
    "AS": (1, 0, "Asturias", ("ES-AS", "03", "Principado de Asturias")),
    "CB": (2, 0, "Cantabria", ("ES-CB", "06")),
    "PV": (3, 0, "País Vasco", ("ES-PV", "16", "Euskadi", "Basque Country")),
    "NC": (4, 0, "Navarra", ("ES-NC", "15", "Comunidad Foral de Navarra")),
    "CT": (6, 0, "Cataluña", ("ES-CT", "09", "Catalunya", "Catalonia")),
    "CL": (1, 1, "Castilla y León", ("ES-CL", "07")),
    "RI": (3, 1, "La Rioja", ("ES-RI", "17", "Rioja")),
    "AR": (5, 1, "Aragón", ("ES-AR", "02", "Aragon")),
    "EX": (0, 2, "Extremadura", ("ES-EX", "11")),
    "MD": (2, 2, "Madrid", ("ES-MD", "13", "Comunidad de Madrid")),
    "CM": (3, 2, "Castilla-La Mancha", ("ES-CM", "08")),
    "VC": (4, 2, "C. Valenciana", ("ES-VC", "10", "Comunitat Valenciana", "Comunidad Valenciana", "Valencia")),
    "IB": (6, 2, "Illes Balears", ("ES-IB", "04", "Baleares", "Islas Baleares", "Balearic Islands")),
    "AN": (1, 3, "Andalucía", ("ES-AN", "01", "Andalucia", "Andalusia")),
    "MC": (3, 3, "Murcia", ("ES-MC", "14", "Región de Murcia")),
    "CN": (0, 4.4, "Canarias", ("ES-CN", "05", "Islas Canarias", "Canary Islands")),
    "CE": (2, 4.4, "Ceuta", ("ES-CE", "18")),
    "ML": (3, 4.4, "Melilla", ("ES-ML", "19")),
}

LAYOUTS = {"es-provinces": ES_PROVINCES, "es-regions": ES_REGIONS}


def fold(s) -> str:
    """Case- and accent-insensitive key."""
    s = unicodedata.normalize("NFKD", str(s).strip().lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def resolver(layout: dict):
    """A function mapping any code, name or alias to the layout's code (or None)."""
    table = {}
    for code, (_, _, name, aliases) in layout.items():
        for key in (code, name, *aliases):
            table.setdefault(fold(key), code)
    return lambda key: table.get(fold(key))
