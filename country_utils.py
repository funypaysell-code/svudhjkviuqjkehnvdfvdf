from __future__ import annotations

import re
from dataclasses import dataclass


try:
    import pycountry
except ImportError:  # pragma: no cover - optional until requirements are installed
    pycountry = None

try:
    import phonenumbers
except ImportError:  # pragma: no cover - optional until requirements are installed
    phonenumbers = None


def normalize_code(code: str | None) -> str:
    """Normalize country code to lowercase.
    
    Ensures all country codes are consistently lowercase regardless of input.
    This fixes issues where codes might be returned in different formats.
    """
    if not code:
        return ""
    return str(code).lower().strip()


@dataclass(slots=True)
class ResolvedCountry:
    code: str
    name: str
    
    def __post_init__(self) -> None:
        # Ensure code is always normalized to lowercase
        object.__setattr__(self, 'code', normalize_code(self.code))


ALIASES: dict[str, ResolvedCountry] = {
    "\u0443\u0437\u0431\u0435\u043a\u0438\u0441\u0442\u0430\u043d": ResolvedCountry("uz", "Uzbekistan"),
    "uzbekistan": ResolvedCountry("uz", "Uzbekistan"),
    "\u0443\u0437": ResolvedCountry("uz", "Uzbekistan"),
    "\u0440\u043e\u0441\u0441\u0438\u044f": ResolvedCountry("ru", "Russia"),
    "\u0440\u0444": ResolvedCountry("ru", "Russia"),
    "russia": ResolvedCountry("ru", "Russia"),
    "\u043a\u0430\u0437\u0430\u0445\u0441\u0442\u0430\u043d": ResolvedCountry("kz", "Kazakhstan"),
    "kazakhstan": ResolvedCountry("kz", "Kazakhstan"),
    "\u043a\u0438\u0440\u0433\u0438\u0437\u0438\u044f": ResolvedCountry("kg", "Kyrgyzstan"),
    "\u043a\u044b\u0440\u0433\u044b\u0437\u0441\u0442\u0430\u043d": ResolvedCountry("kg", "Kyrgyzstan"),
    "kyrgyzstan": ResolvedCountry("kg", "Kyrgyzstan"),
    "\u0442\u0430\u0434\u0436\u0438\u043a\u0438\u0441\u0442\u0430\u043d": ResolvedCountry("tj", "Tajikistan"),
    "tajikistan": ResolvedCountry("tj", "Tajikistan"),
    "\u0443\u043a\u0440\u0430\u0438\u043d\u0430": ResolvedCountry("ua", "Ukraine"),
    "ukraine": ResolvedCountry("ua", "Ukraine"),
    "\u0431\u0435\u043b\u0430\u0440\u0443\u0441\u044c": ResolvedCountry("by", "Belarus"),
    "belarus": ResolvedCountry("by", "Belarus"),
    "\u0442\u0443\u0440\u0446\u0438\u044f": ResolvedCountry("tr", "Turkey"),
    "turkey": ResolvedCountry("tr", "Turkey"),
    "\u0441\u0448\u0430": ResolvedCountry("us", "United States"),
    "usa": ResolvedCountry("us", "United States"),
    "united states": ResolvedCountry("us", "United States"),
    "\u0438\u043d\u0434\u043e\u043d\u0435\u0437\u0438\u044f": ResolvedCountry("id", "Indonesia"),
    "indonesia": ResolvedCountry("id", "Indonesia"),
    "\u0438\u043d\u0434\u0438\u044f": ResolvedCountry("in", "India"),
    "india": ResolvedCountry("in", "India"),
    "\u043a\u0438\u0442\u0430\u0439": ResolvedCountry("cn", "China"),
    "china": ResolvedCountry("cn", "China"),
    "\u0432\u044c\u0435\u0442\u043d\u0430\u043c": ResolvedCountry("vn", "Vietnam"),
    "vietnam": ResolvedCountry("vn", "Vietnam"),
    "\u0442\u0430\u0439\u043b\u0430\u043d\u0434": ResolvedCountry("th", "Thailand"),
    "\u0442\u0430\u0438\u043b\u0430\u043d\u0434": ResolvedCountry("th", "Thailand"),
    "thailand": ResolvedCountry("th", "Thailand"),
    "niue": ResolvedCountry("nu", "Niue"),
    "\u043d\u0438\u0443\u044d": ResolvedCountry("nu", "Niue"),
    "\u043d\u0438\u044e\u044d": ResolvedCountry("nu", "Niue"),
}

CALLING_CODE_FALLBACKS: dict[str, ResolvedCountry] = {
    "1": ResolvedCountry("us", "United States"),
    "7": ResolvedCountry("ru", "Russia"),
    "20": ResolvedCountry("eg", "Egypt"),
    "27": ResolvedCountry("za", "South Africa"),
    "30": ResolvedCountry("gr", "Greece"),
    "31": ResolvedCountry("nl", "Netherlands"),
    "32": ResolvedCountry("be", "Belgium"),
    "33": ResolvedCountry("fr", "France"),
    "34": ResolvedCountry("es", "Spain"),
    "36": ResolvedCountry("hu", "Hungary"),
    "39": ResolvedCountry("it", "Italy"),
    "40": ResolvedCountry("ro", "Romania"),
    "41": ResolvedCountry("ch", "Switzerland"),
    "43": ResolvedCountry("at", "Austria"),
    "44": ResolvedCountry("gb", "United Kingdom"),
    "45": ResolvedCountry("dk", "Denmark"),
    "46": ResolvedCountry("se", "Sweden"),
    "47": ResolvedCountry("no", "Norway"),
    "48": ResolvedCountry("pl", "Poland"),
    "49": ResolvedCountry("de", "Germany"),
    "51": ResolvedCountry("pe", "Peru"),
    "52": ResolvedCountry("mx", "Mexico"),
    "53": ResolvedCountry("cu", "Cuba"),
    "54": ResolvedCountry("ar", "Argentina"),
    "55": ResolvedCountry("br", "Brazil"),
    "56": ResolvedCountry("cl", "Chile"),
    "57": ResolvedCountry("co", "Colombia"),
    "58": ResolvedCountry("ve", "Venezuela"),
    "60": ResolvedCountry("my", "Malaysia"),
    "61": ResolvedCountry("au", "Australia"),
    "62": ResolvedCountry("id", "Indonesia"),
    "63": ResolvedCountry("ph", "Philippines"),
    "64": ResolvedCountry("nz", "New Zealand"),
    "65": ResolvedCountry("sg", "Singapore"),
    "66": ResolvedCountry("th", "Thailand"),
    "81": ResolvedCountry("jp", "Japan"),
    "82": ResolvedCountry("kr", "South Korea"),
    "84": ResolvedCountry("vn", "Vietnam"),
    "86": ResolvedCountry("cn", "China"),
    "90": ResolvedCountry("tr", "Turkey"),
    "91": ResolvedCountry("in", "India"),
    "92": ResolvedCountry("pk", "Pakistan"),
    "93": ResolvedCountry("af", "Afghanistan"),
    "94": ResolvedCountry("lk", "Sri Lanka"),
    "95": ResolvedCountry("mm", "Myanmar"),
    "98": ResolvedCountry("ir", "Iran"),
    "212": ResolvedCountry("ma", "Morocco"),
    "213": ResolvedCountry("dz", "Algeria"),
    "216": ResolvedCountry("tn", "Tunisia"),
    "218": ResolvedCountry("ly", "Libya"),
    "220": ResolvedCountry("gm", "Gambia"),
    "221": ResolvedCountry("sn", "Senegal"),
    "222": ResolvedCountry("mr", "Mauritania"),
    "223": ResolvedCountry("ml", "Mali"),
    "224": ResolvedCountry("gn", "Guinea"),
    "225": ResolvedCountry("ci", "Cote d'Ivoire"),
    "226": ResolvedCountry("bf", "Burkina Faso"),
    "227": ResolvedCountry("ne", "Niger"),
    "228": ResolvedCountry("tg", "Togo"),
    "229": ResolvedCountry("bj", "Benin"),
    "230": ResolvedCountry("mu", "Mauritius"),
    "231": ResolvedCountry("lr", "Liberia"),
    "232": ResolvedCountry("sl", "Sierra Leone"),
    "233": ResolvedCountry("gh", "Ghana"),
    "234": ResolvedCountry("ng", "Nigeria"),
    "235": ResolvedCountry("td", "Chad"),
    "236": ResolvedCountry("cf", "Central African Republic"),
    "237": ResolvedCountry("cm", "Cameroon"),
    "238": ResolvedCountry("cv", "Cape Verde"),
    "239": ResolvedCountry("st", "Sao Tome and Principe"),
    "240": ResolvedCountry("gq", "Equatorial Guinea"),
    "241": ResolvedCountry("ga", "Gabon"),
    "242": ResolvedCountry("cg", "Congo"),
    "243": ResolvedCountry("cd", "DR Congo"),
    "244": ResolvedCountry("ao", "Angola"),
    "245": ResolvedCountry("gw", "Guinea-Bissau"),
    "248": ResolvedCountry("sc", "Seychelles"),
    "249": ResolvedCountry("sd", "Sudan"),
    "250": ResolvedCountry("rw", "Rwanda"),
    "251": ResolvedCountry("et", "Ethiopia"),
    "252": ResolvedCountry("so", "Somalia"),
    "253": ResolvedCountry("dj", "Djibouti"),
    "254": ResolvedCountry("ke", "Kenya"),
    "255": ResolvedCountry("tz", "Tanzania"),
    "256": ResolvedCountry("ug", "Uganda"),
    "257": ResolvedCountry("bi", "Burundi"),
    "258": ResolvedCountry("mz", "Mozambique"),
    "260": ResolvedCountry("zm", "Zambia"),
    "261": ResolvedCountry("mg", "Madagascar"),
    "263": ResolvedCountry("zw", "Zimbabwe"),
    "264": ResolvedCountry("na", "Namibia"),
    "265": ResolvedCountry("mw", "Malawi"),
    "266": ResolvedCountry("ls", "Lesotho"),
    "267": ResolvedCountry("bw", "Botswana"),
    "268": ResolvedCountry("sz", "Eswatini"),
    "269": ResolvedCountry("km", "Comoros"),
    "290": ResolvedCountry("sh", "Saint Helena"),
    "291": ResolvedCountry("er", "Eritrea"),
    "297": ResolvedCountry("aw", "Aruba"),
    "298": ResolvedCountry("fo", "Faroe Islands"),
    "299": ResolvedCountry("gl", "Greenland"),
    "350": ResolvedCountry("gi", "Gibraltar"),
    "351": ResolvedCountry("pt", "Portugal"),
    "352": ResolvedCountry("lu", "Luxembourg"),
    "353": ResolvedCountry("ie", "Ireland"),
    "354": ResolvedCountry("is", "Iceland"),
    "355": ResolvedCountry("al", "Albania"),
    "356": ResolvedCountry("mt", "Malta"),
    "357": ResolvedCountry("cy", "Cyprus"),
    "358": ResolvedCountry("fi", "Finland"),
    "359": ResolvedCountry("bg", "Bulgaria"),
    "370": ResolvedCountry("lt", "Lithuania"),
    "371": ResolvedCountry("lv", "Latvia"),
    "372": ResolvedCountry("ee", "Estonia"),
    "373": ResolvedCountry("md", "Moldova"),
    "374": ResolvedCountry("am", "Armenia"),
    "375": ResolvedCountry("by", "Belarus"),
    "376": ResolvedCountry("ad", "Andorra"),
    "377": ResolvedCountry("mc", "Monaco"),
    "378": ResolvedCountry("sm", "San Marino"),
    "380": ResolvedCountry("ua", "Ukraine"),
    "381": ResolvedCountry("rs", "Serbia"),
    "382": ResolvedCountry("me", "Montenegro"),
    "383": ResolvedCountry("xk", "Kosovo"),
    "385": ResolvedCountry("hr", "Croatia"),
    "386": ResolvedCountry("si", "Slovenia"),
    "387": ResolvedCountry("ba", "Bosnia and Herzegovina"),
    "389": ResolvedCountry("mk", "North Macedonia"),
    "420": ResolvedCountry("cz", "Czechia"),
    "421": ResolvedCountry("sk", "Slovakia"),
    "423": ResolvedCountry("li", "Liechtenstein"),
    "500": ResolvedCountry("fk", "Falkland Islands"),
    "501": ResolvedCountry("bz", "Belize"),
    "502": ResolvedCountry("gt", "Guatemala"),
    "503": ResolvedCountry("sv", "El Salvador"),
    "504": ResolvedCountry("hn", "Honduras"),
    "505": ResolvedCountry("ni", "Nicaragua"),
    "506": ResolvedCountry("cr", "Costa Rica"),
    "507": ResolvedCountry("pa", "Panama"),
    "508": ResolvedCountry("pm", "Saint Pierre and Miquelon"),
    "509": ResolvedCountry("ht", "Haiti"),
    "590": ResolvedCountry("gp", "Guadeloupe"),
    "591": ResolvedCountry("bo", "Bolivia"),
    "592": ResolvedCountry("gy", "Guyana"),
    "593": ResolvedCountry("ec", "Ecuador"),
    "594": ResolvedCountry("gf", "French Guiana"),
    "595": ResolvedCountry("py", "Paraguay"),
    "596": ResolvedCountry("mq", "Martinique"),
    "597": ResolvedCountry("sr", "Suriname"),
    "598": ResolvedCountry("uy", "Uruguay"),
    "599": ResolvedCountry("cw", "Curacao"),
    "670": ResolvedCountry("tl", "Timor-Leste"),
    "672": ResolvedCountry("nf", "Norfolk Island"),
    "673": ResolvedCountry("bn", "Brunei"),
    "674": ResolvedCountry("nr", "Nauru"),
    "675": ResolvedCountry("pg", "Papua New Guinea"),
    "676": ResolvedCountry("to", "Tonga"),
    "677": ResolvedCountry("sb", "Solomon Islands"),
    "678": ResolvedCountry("vu", "Vanuatu"),
    "679": ResolvedCountry("fj", "Fiji"),
    "680": ResolvedCountry("pw", "Palau"),
    "681": ResolvedCountry("wf", "Wallis and Futuna"),
    "682": ResolvedCountry("ck", "Cook Islands"),
    "683": ResolvedCountry("nu", "Niue"),
    "685": ResolvedCountry("ws", "Samoa"),
    "686": ResolvedCountry("ki", "Kiribati"),
    "687": ResolvedCountry("nc", "New Caledonia"),
    "688": ResolvedCountry("tv", "Tuvalu"),
    "689": ResolvedCountry("pf", "French Polynesia"),
    "690": ResolvedCountry("tk", "Tokelau"),
    "691": ResolvedCountry("fm", "Micronesia"),
    "692": ResolvedCountry("mh", "Marshall Islands"),
    "850": ResolvedCountry("kp", "North Korea"),
    "852": ResolvedCountry("hk", "Hong Kong"),
    "853": ResolvedCountry("mo", "Macao"),
    "855": ResolvedCountry("kh", "Cambodia"),
    "856": ResolvedCountry("la", "Laos"),
    "880": ResolvedCountry("bd", "Bangladesh"),
    "886": ResolvedCountry("tw", "Taiwan"),
    "960": ResolvedCountry("mv", "Maldives"),
    "961": ResolvedCountry("lb", "Lebanon"),
    "962": ResolvedCountry("jo", "Jordan"),
    "963": ResolvedCountry("sy", "Syria"),
    "964": ResolvedCountry("iq", "Iraq"),
    "965": ResolvedCountry("kw", "Kuwait"),
    "966": ResolvedCountry("sa", "Saudi Arabia"),
    "967": ResolvedCountry("ye", "Yemen"),
    "968": ResolvedCountry("om", "Oman"),
    "970": ResolvedCountry("ps", "Palestine"),
    "971": ResolvedCountry("ae", "United Arab Emirates"),
    "972": ResolvedCountry("il", "Israel"),
    "973": ResolvedCountry("bh", "Bahrain"),
    "974": ResolvedCountry("qa", "Qatar"),
    "975": ResolvedCountry("bt", "Bhutan"),
    "976": ResolvedCountry("mn", "Mongolia"),
    "977": ResolvedCountry("np", "Nepal"),
    "992": ResolvedCountry("tj", "Tajikistan"),
    "993": ResolvedCountry("tm", "Turkmenistan"),
    "994": ResolvedCountry("az", "Azerbaijan"),
    "995": ResolvedCountry("ge", "Georgia"),
    "996": ResolvedCountry("kg", "Kyrgyzstan"),
    "998": ResolvedCountry("uz", "Uzbekistan"),
}

REGION_NAME_FALLBACKS: dict[str, str] = {
    "AF": "Afghanistan",
    "AL": "Albania",
    "DZ": "Algeria",
    "AD": "Andorra",
    "AO": "Angola",
    "AR": "Argentina",
    "AM": "Armenia",
    "AU": "Australia",
    "AT": "Austria",
    "AZ": "Azerbaijan",
    "BH": "Bahrain",
    "BD": "Bangladesh",
    "BY": "Belarus",
    "BE": "Belgium",
    "BJ": "Benin",
    "BO": "Bolivia",
    "BA": "Bosnia and Herzegovina",
    "BR": "Brazil",
    "BG": "Bulgaria",
    "KH": "Cambodia",
    "CM": "Cameroon",
    "CA": "Canada",
    "CL": "Chile",
    "CN": "China",
    "CO": "Colombia",
    "HR": "Croatia",
    "CY": "Cyprus",
    "CZ": "Czechia",
    "DK": "Denmark",
    "EG": "Egypt",
    "EE": "Estonia",
    "FK": "Falkland Islands",
    "FI": "Finland",
    "FR": "France",
    "GE": "Georgia",
    "DE": "Germany",
    "GH": "Ghana",
    "GR": "Greece",
    "HK": "Hong Kong",
    "HU": "Hungary",
    "IN": "India",
    "ID": "Indonesia",
    "IR": "Iran",
    "IQ": "Iraq",
    "IE": "Ireland",
    "IL": "Israel",
    "IT": "Italy",
    "JP": "Japan",
    "JO": "Jordan",
    "KZ": "Kazakhstan",
    "KE": "Kenya",
    "KG": "Kyrgyzstan",
    "KW": "Kuwait",
    "LA": "Laos",
    "LV": "Latvia",
    "LB": "Lebanon",
    "LT": "Lithuania",
    "MY": "Malaysia",
    "MX": "Mexico",
    "MD": "Moldova",
    "MN": "Mongolia",
    "MA": "Morocco",
    "MM": "Myanmar",
    "NP": "Nepal",
    "NL": "Netherlands",
    "NZ": "New Zealand",
    "NU": "Niue",
    "NG": "Nigeria",
    "NO": "Norway",
    "OM": "Oman",
    "PK": "Pakistan",
    "PE": "Peru",
    "PH": "Philippines",
    "PL": "Poland",
    "PT": "Portugal",
    "QA": "Qatar",
    "RO": "Romania",
    "RU": "Russia",
    "SA": "Saudi Arabia",
    "RS": "Serbia",
    "SG": "Singapore",
    "SK": "Slovakia",
    "SI": "Slovenia",
    "ZA": "South Africa",
    "KR": "South Korea",
    "ES": "Spain",
    "LK": "Sri Lanka",
    "SE": "Sweden",
    "CH": "Switzerland",
    "SY": "Syria",
    "TW": "Taiwan",
    "TJ": "Tajikistan",
    "TH": "Thailand",
    "TN": "Tunisia",
    "TR": "Turkey",
    "TM": "Turkmenistan",
    "UA": "Ukraine",
    "AE": "United Arab Emirates",
    "GB": "United Kingdom",
    "US": "United States",
    "UY": "Uruguay",
    "UZ": "Uzbekistan",
    "VE": "Venezuela",
    "VN": "Vietnam",
    "YE": "Yemen",
}


def resolve_country(value: str) -> ResolvedCountry | None:
    text = normalize_country_input(value)
    if not text:
        return None

    by_calling_code = resolve_calling_code(text)
    if by_calling_code:
        return by_calling_code

    parsed = parse_code_name(text)
    if parsed:
        return parsed

    if text in ALIASES:
        return ALIASES[text]

    if len(text) == 2 and text.isalpha():
        code = text.lower()
        return ResolvedCountry(code, country_name_by_code(code))

    if pycountry:
        try:
            country = pycountry.countries.search_fuzzy(text)[0]
            return ResolvedCountry(country.alpha_2.lower(), country.name)
        except LookupError:
            return None

    return None


def resolve_calling_code(text: str) -> ResolvedCountry | None:
    digits = re.sub(r"\D", "", text)
    if not digits:
        return None

    country_code = detect_country_calling_code(digits)
    if country_code is None:
        return None

    if str(country_code) in CALLING_CODE_FALLBACKS:
        return CALLING_CODE_FALLBACKS[str(country_code)]

    if phonenumbers is None:
        return None

    regions = phonenumbers.region_codes_for_country_code(country_code)
    region = choose_region(regions)
    if not region or region == "ZZ":
        return None
    code = region.lower()
    return ResolvedCountry(code, country_name_by_code(code))


def detect_country_calling_code(digits: str) -> int | None:
    for length in range(min(3, len(digits)), 0, -1):
        prefix = digits[:length]
        code = int(prefix)
        if prefix in CALLING_CODE_FALLBACKS:
            return code
        if phonenumbers and phonenumbers.region_codes_for_country_code(code):
            return code
    return None


def choose_region(regions: tuple[str, ...]) -> str | None:
    real_regions = [region for region in regions if region and region != "001"]
    if not real_regions:
        return None
    return real_regions[0]


def country_name_by_code(code: str) -> str:
    if pycountry:
        country = pycountry.countries.get(alpha_2=code.upper())
        if country:
            return country.name
    return REGION_NAME_FALLBACKS.get(code.upper(), code.upper())


def normalize_country_input(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def parse_code_name(text: str) -> ResolvedCountry | None:
    match = re.match(r"^([a-z\u0430-\u044f]{2})\s+(.+)$", text, flags=re.IGNORECASE)
    if not match:
        return None
    code = match.group(1).lower()
    name = match.group(2).strip()
    if re.fullmatch(r"[a-z]{2}", code) and name:
        return ResolvedCountry(code, name.title())
    return None
