"""Official India roadside-assistance / helpline numbers, checked against each carmaker's own site
on 2026-09-30. Only numbers the brand publishes are listed; brands we could not verify
(e.g. Honda, Mercedes-Benz) are left out so the agent never reads out a guessed number.
"""
from __future__ import annotations

import re

_HELPLINES: dict[str, dict[str, str]] = {
    "maruti": {"number": "1800 102 1800", "label": "Maruti Suzuki 24x7 roadside assistance", "source": "marutisuzuki.com/arena/service/roadside-assistance"},
    "hyundai": {"number": "1800 102 4645", "label": "Hyundai 24x7 roadside assistance", "source": "hyundai.com/in/en/connect-to-service/road-side-assistance"},
    "tata": {"number": "1800 209 8282", "label": "Tata Motors cars customer care and roadside assistance", "source": "cars.tatamotors.com/support.html"},
    "mahindra": {"number": "1800 102 7006", "label": "Mahindra 24 hour roadside assistance (personal vehicles)", "source": "auto.mahindra.com/contact-us"},
    "kia": {"number": "1800 108 5000", "label": "Kia roadside assistance", "source": "kia.com/in/service/kia-owners/road-side-assistance.html"},
    "mg": {"number": "1800 100 6464", "label": "MG Motor India helpline", "source": "mgmotor.co.in/contact-us"},
    "toyota": {"number": "1800 102 5001", "label": "Toyota 24x7 roadside assistance", "source": "toyotabharat.com/contact-us"},
    "skoda": {"number": "1800 209 4646", "label": "Skoda roadside assistance", "source": "skoda-auto.co.in/service-and-parts/roadside-assistance"},
    "volkswagen": {"number": "1800 102 1155", "label": "Volkswagen mobile support", "source": "volkswagen.co.in owners and services, mobile support"},
    "renault": {"number": "1800 315 4444", "label": "Renault Assist roadside assistance", "source": "renault.co.in/renault-service/renault-assist.html"},
    "nissan": {"number": "1800 209 3456", "label": "Nissan roadside assistance", "source": "nissan.in/ownership/nissan-roadside-assistance.html"},
    "bmw": {"number": "1800 102 2269", "label": "BMW India customer support", "source": "bmw.in/en/more-bmw/customer-support.html"},
}
_ALIASES = {"suzuki": "maruti", "nexa": "maruti", "vw": "volkswagen", "morris": "mg"}


def helpline_for(make: str) -> dict[str, str] | None:
    key = re.sub(r"[^a-z]", "", (make.split() or [""])[0].lower())
    return _HELPLINES.get(_ALIASES.get(key, key))
