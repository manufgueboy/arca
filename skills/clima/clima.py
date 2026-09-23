"""Skill ejecutable de ejemplo: recibe los parámetros como JSON en stdin (y como ARCA_<PARAM>).
Usa Open-Meteo (gratis, sin llave) y wttr.in de respaldo."""
import json
import sys
import urllib.parse
import urllib.request

CODIGOS = {0: "despejado", 1: "casi despejado", 2: "parcialmente nublado", 3: "nublado", 45: "niebla", 48: "niebla",
           51: "llovizna ligera", 53: "llovizna", 55: "llovizna fuerte", 61: "lluvia ligera", 63: "lluvia", 65: "lluvia fuerte",
           71: "nieve ligera", 73: "nieve", 75: "nieve fuerte", 80: "chubascos ligeros", 81: "chubascos", 82: "chubascos fuertes",
           95: "tormenta", 96: "tormenta con granizo", 99: "tormenta con granizo"}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Arca/0.1"})
    return json.load(urllib.request.urlopen(req, timeout=15))


def open_meteo(ciudad):
    if ciudad.lower() == "auto":
        ip = get("https://ipapi.co/json/")
        lat, lon, nombre = ip["latitude"], ip["longitude"], f"{ip.get('city')}, {ip.get('country_name')}"
    else:
        g = get("https://geocoding-api.open-meteo.com/v1/search?count=1&language=es&name=" + urllib.parse.quote(ciudad))
        if not g.get("results"):
            raise RuntimeError(f"no encontré la ciudad '{ciudad}'")
        r = g["results"][0]
        lat, lon, nombre = r["latitude"], r["longitude"], f"{r['name']}, {r.get('admin1', '')}, {r.get('country', '')}"
    d = get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&timezone=auto&forecast_days=3"
            "&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,precipitation"
            "&daily=temperature_2m_min,temperature_2m_max,precipitation_probability_max,weather_code")
    c = d["current"]
    print(f"Lugar: {nombre}")
    print(f"Ahora: {c['temperature_2m']}°C (sensación {c['apparent_temperature']}°C), "
          f"{CODIGOS.get(c['weather_code'], 'variable')}, humedad {c['relative_humidity_2m']}%")
    dd = d["daily"]
    for i, fecha in enumerate(dd["time"]):
        print(f"{fecha}: mín {dd['temperature_2m_min'][i]}°C, máx {dd['temperature_2m_max'][i]}°C, "
              f"{CODIGOS.get(dd['weather_code'][i], 'variable')}, prob. de lluvia {dd['precipitation_probability_max'][i]}%")


def wttr(ciudad):
    url = "https://wttr.in/" + ("" if ciudad.lower() == "auto" else urllib.parse.quote(ciudad)) + "?format=j1&lang=es"
    d = get(url)
    hoy = d["current_condition"][0]
    desc = (hoy.get("lang_es") or hoy.get("weatherDesc"))[0]["value"]
    print(f"Ahora: {hoy['temp_C']}°C (sensación {hoy['FeelsLikeC']}°C), {desc}, humedad {hoy['humidity']}%")
    for dia in d.get("weather", [])[:3]:
        lluvia = max(int(h.get("chanceofrain", 0)) for h in dia.get("hourly", [{}]))
        print(f"{dia['date']}: mín {dia['mintempC']}°C, máx {dia['maxtempC']}°C, prob. de lluvia hasta {lluvia}%")


args = json.load(sys.stdin)
ciudad = (args.get("ciudad") or "auto").strip()
errores = []
for fuente in (open_meteo, wttr):
    try:
        fuente(ciudad)
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as e:
        errores.append(f"{fuente.__name__}: {e}")
print("[error] No pude consultar el clima (" + "; ".join(errores) + ")")
