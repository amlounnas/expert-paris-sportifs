#!/usr/bin/env python3
"""
UNDERSTAT — vrai xG (expected goals) gratuit
=============================================
Récupère le xG / xGA réel par équipe (domicile/extérieur) depuis Understat,
pour remplacer l'approximation par buts marqués/encaissés du modèle.

Endpoint: https://understat.com/getLeagueData/{league}/{season}
(nécessite headers Referer + X-Requested-With, réponse gzip)

Si le scraping casse, une alerte Telegram est envoyée (voir send_alert).
"""

import os, json, urllib.request, urllib.parse, gzip
from datetime import datetime

UNDERSTAT_URL = "https://understat.com"

# Competition code (football-data.org) -> league key Understat
LEAGUE_KEYS = {
    "PL": "EPL",
    "BL1": "Bundesliga",
    "FL1": "Ligue 1",
    "PD": "La liga",
}

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": f"{UNDERSTAT_URL}/league/EPL",
    "X-Requested-With": "XMLHttpRequest",
    "Accept-Encoding": "gzip",
}


def get_season():
    """Saison Understat (année de début). La saison 2026/27 -> '2026'."""
    now = datetime.now()
    return now.year if now.month >= 8 else now.year - 1


def _fetch_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding", "") == "gzip" or raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        return json.loads(raw.decode("utf-8"))


def send_alert(message):
    """Alerte Telegram si le scraping casse."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception:
        return False


def fetch_league_xg(league_key, season=None, alert=True):
    """
    Retourne {titre_équipe: {"xg", "xga", "xg_home", "xga_home",
                              "xg_away", "xga_away", "played"}}
    ou None en cas d'échec (avec alerte Telegram).
    """
    if season is None:
        season = get_season()

    url = f"{UNDERSTAT_URL}/getLeagueData/{urllib.parse.quote(league_key)}/{season}"
    try:
        data = _fetch_json(url)
    except Exception as e:
        if alert:
            send_alert(
                f"🚨 <b>Understat KO</b>\n\n"
                f"Échec du scraping xG pour <b>{league_key}</b> (saison {season}).\n\n"
                f"Erreur: <code>{e}</code>\n\n"
                f"Le modèle retombe sur l'xG approximé par buts."
            )
        return None

    teams = data.get("teams")
    if not teams:
        if alert:
            send_alert(
                f"🚨 <b>Understat KO</b>\n\n"
                f"Aucune donnée d'équipe pour <b>{league_key}</b> (saison {season}).\n"
                f"Vérifie que la saison {season} est bien lancée."
            )
        return None

    result = {}
    for team in teams.values():
        title = team.get("title")
        history = team.get("history", [])
        if not title or not history:
            continue

        def avg(vals):
            vals = [v for v in vals if v is not None]
            return round(sum(vals) / len(vals), 3) if vals else None

        home = [m for m in history if m.get("h_a") == "h"]
        away = [m for m in history if m.get("h_a") == "a"]

        result[title] = {
            "xg": avg([m.get("xG") for m in history]),
            "xga": avg([m.get("xGA") for m in history]),
            "xg_home": avg([m.get("xG") for m in home]),
            "xga_home": avg([m.get("xGA") for m in home]),
            "xg_away": avg([m.get("xG") for m in away]),
            "xga_away": avg([m.get("xGA") for m in away]),
            "played": len(history),
        }

    return result


if __name__ == "__main__":
    # Auto-test: fetch les 4 ligues et affiche un échantillon
    season = get_season()
    print(f"Saison Understat: {season}")
    for code, key in LEAGUE_KEYS.items():
        data = fetch_league_xg(key, season, alert=False)
        if data:
            sample = list(data.items())[:3]
            print(f"\n{key} ({len(data)} équipes):")
            for title, s in sample:
                print(f"  {title}: xG={s['xg']} xGA={s['xga']} "
                      f"(dom {s['xg_home']}/{s['xga_home']}, ext {s['xg_away']}/{s['xga_away']})")
        else:
            print(f"\n{key}: ÉCHEC")
