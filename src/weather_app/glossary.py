"""Plain-language explanations of aviation terms, shared by every page.

Use them as Streamlit tooltips, e.g. st.metric("Wind", value, help=GLOSSARY["Knots (kt)"]),
or list them all with views.common.show_glossary(). Add new terms here so every page stays
consistent. (No Streamlit code in this package: it only holds logic and data.)
"""

GLOSSARY = {
    "ICAO code": "A 4-letter code that identifies an airport worldwide, e.g. LEMD = Madrid-Barajas, "
                 "EGLL = London Heathrow, LFPG = Paris Charles de Gaulle.",
    "METAR": "The weather an airport has just observed, in a short coded format pilots read. "
             "Most airports publish one every 30 or 60 minutes.",
    "TAF": "Terminal Aerodrome Forecast: the airport's official weather forecast, usually for the "
           "next 24-30 hours.",
    "UTC (Z)": "Aviation uses one clock worldwide: UTC, written 'Z' (Zulu). Madrid is UTC+1 in winter "
               "and UTC+2 in summer.",
    "Flight category": "A quick traffic-light summary of cloud height and visibility: VFR (good), "
                       "MVFR (moderate), IFR (poor), LIFR (very poor).",
    "Ceiling": "The height of the lowest cloud layer that covers more than half the sky. "
               "Low ceilings make landing harder.",
    "Visibility": "How far you can see horizontally. Fog, mist, rain and haze reduce it.",
    "Knots (kt)": "The speed unit used in aviation: 1 knot = 1 nautical mile per hour = 1.852 km/h.",
    "Gust": "A short burst of wind that is noticeably stronger than the average wind.",
    "QNH (pressure)": "Air pressure adjusted to sea level, in hectopascals (hPa). Pilots set it on "
                      "their altimeter so it shows the correct height.",
    "Feet (ft)": "Aviation measures height in feet: 1,000 ft is about 305 m.",
    "Alternate airport": "A back-up airport the flight can divert to if it cannot land at the "
                         "destination, for example because of bad weather.",
    "TEMPO": "In a TAF: a temporary change, expected to last less than an hour at a time.",
    "BECMG": "In a TAF: conditions gradually changing to a new state during the period.",
    "PROB30 / PROB40": "In a TAF: a 30% or 40% chance that these conditions happen.",
    "FM": "In a TAF: 'from this time', a lasting change that starts at the given time.",
}
