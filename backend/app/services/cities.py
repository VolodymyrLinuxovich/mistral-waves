"""Major Ukrainian cities for the national hazard overview and city search.

Coordinates are city-centre points (WGS84). Population figures are pre-war
official estimates and are shown only for ordering/context, never as current
exposure counts (wartime displacement makes them uncertain — see limitations).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class City:
    id: str
    name_en: str
    name_uk: str
    lat: float
    lon: float
    oblast_en: str
    population_est: int  # pre-war estimate, context only


CITIES: list[City] = [
    City("kyiv", "Kyiv", "Київ", 50.4501, 30.5234, "Kyiv City", 2952000),
    City("kharkiv", "Kharkiv", "Харків", 49.9935, 36.2304, "Kharkiv", 1421000),
    City("odesa", "Odesa", "Одеса", 46.4825, 30.7233, "Odesa", 1010000),
    City("dnipro", "Dnipro", "Дніпро", 48.4647, 35.0462, "Dnipropetrovsk", 980000),
    City("donetsk", "Donetsk", "Донецьк", 48.0159, 37.8028, "Donetsk", 905000),
    City("zaporizhzhia", "Zaporizhzhia", "Запоріжжя", 47.8388, 35.1396, "Zaporizhzhia", 722000),
    City("lviv", "Lviv", "Львів", 49.8397, 24.0297, "Lviv", 717000),
    City("kryvyi_rih", "Kryvyi Rih", "Кривий Ріг", 47.9105, 33.3918, "Dnipropetrovsk", 619000),
    City("mykolaiv", "Mykolaiv", "Миколаїв", 46.9750, 31.9946, "Mykolaiv", 476000),
    City("vinnytsia", "Vinnytsia", "Вінниця", 49.2331, 28.4682, "Vinnytsia", 369000),
    City("kherson", "Kherson", "Херсон", 46.6354, 32.6169, "Kherson", 283000),
    City("poltava", "Poltava", "Полтава", 49.5883, 34.5514, "Poltava", 284000),
    City("chernihiv", "Chernihiv", "Чернігів", 51.4982, 31.2893, "Chernihiv", 285000),
    City("cherkasy", "Cherkasy", "Черкаси", 49.4444, 32.0598, "Cherkasy", 272000),
    City("zhytomyr", "Zhytomyr", "Житомир", 50.2547, 28.6587, "Zhytomyr", 261000),
    City("uzhhorod", "Uzhhorod", "Ужгород", 48.6208, 22.2879, "Zakarpattia", 115000),
]

CITY_BY_ID = {c.id: c for c in CITIES}


def search(query: str) -> list[City]:
    q = query.strip().lower()
    if not q:
        return CITIES
    return [c for c in CITIES
            if q in c.name_en.lower() or q in c.name_uk.lower() or q in c.id]
