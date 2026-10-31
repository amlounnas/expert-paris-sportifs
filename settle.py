#!/usr/bin/env python3
"""
RÈGLEMENT DES PARIS (settlement)
================================
Marque les paris 'pending' en 'won' / 'lost' en fonction des résultats réels
(Football-Data.org), recalcule les stats (ROI, win rate) et sauvegarde tracking.json.

À exécuter après les matchs (workflow quotidien) ET en début de 'email' pour
afficher un ROI à jour.
"""

import os, json, urllib.request
from datetime import datetime, timedelta

FOOTBALL_API_KEY = os.environ.get("FOOTBALL_API_KEY", "")
FOOTBALL_API_URL = "https://api.football-data.org/v4"
TRACKING_FILE = "tracking.json"


# ============== DÉTERMINATION DU RÉSULTAT ==============
def determine_result(bet_type, home_goals, away_goals):
    """Retourne 'won' ou 'lost' (ou None si scores indisponibles)."""
    if home_goals is None or away_goals is None:
        return None
    total = home_goals + away_goals
    if bet_type == "1":
        return "won" if home_goals > away_goals else "lost"
    if bet_type == "2":
        return "won" if away_goals > home_goals else "lost"
    if bet_type == "N":
        return "won" if home_goals == away_goals else "lost"
    if bet_type == "+2.5":
        return "won" if total > 2.5 else "lost"
    if bet_type == "-2.5":
        return "won" if total < 2.5 else "lost"
    if bet_type == "+1.5":
        return "won" if total > 1.5 else "lost"
    if bet_type == "-1.5":
        return "won" if total < 1.5 else "lost"
    if bet_type == "+3.5":
        return "won" if total > 3.5 else "lost"
    if bet_type == "-3.5":
        return "won" if total < 3.5 else "lost"
    if bet_type == "BTTS_yes":
        return "won" if (home_goals > 0 and away_goals > 0) else "lost"
    if bet_type == "BTTS_no":
        return "won" if (home_goals == 0 or away_goals == 0) else "lost"
    return None


# ============== RÉCUPÉRATION DES RÉSULTATS ==============
def fetch_json(url):
    try:
        req = urllib.request.Request(url)
        req.add_header("X-Auth-Token", FOOTBALL_API_KEY)
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"  ⚠️ Erreur API: {e}")
        return None


def fetch_result(competition_code, home, away, match_date_iso):
    """Cherche le score final d'un match FINISHED."""
    if not competition_code or not match_date_iso:
        return None
    try:
        day = match_date_iso[:10]  # "YYYY-MM-DD"
    except:
        return None

    data = fetch_json(
        f"{FOOTBALL_API_URL}/competitions/{competition_code}/matches"
        f"?status=FINISHED&dateFrom={day}&dateTo={day}"
    )
    if not data or "matches" not in data:
        return None

    for m in data["matches"]:
        if m["homeTeam"]["name"] == home and m["awayTeam"]["name"] == away:
            hg = m["score"]["fullTime"]["home"]
            ag = m["score"]["fullTime"]["away"]
            if hg is not None and ag is not None:
                return (hg, ag)
    return None


# ============== SETTLEMENT ==============
def settle_bets(tracking, verbose=True):
    """Marque tous les paris pending dont le match est terminé."""
    settled_count = 0
    for b in tracking["bets"]:
        if b.get("status") != "pending":
            continue

        result = fetch_result(
            b.get("competition_code"),
            b.get("home"),
            b.get("away"),
            b.get("match_iso"),
        )

        if result is None:
            continue  # match pas encore joué / introuvable → reste pending

        hg, ag = result
        outcome = determine_result(b.get("bet_type"), hg, ag)
        if outcome is None:
            continue

        b["status"] = outcome
        b["result"] = f"{hg}-{ag}"
        if outcome == "won":
            b["profit"] = round(b["stake"] * (b["odds"] - 1), 2)
        else:
            b["profit"] = round(-b["stake"], 2)

        settled_count += 1
        if verbose:
            mark = "✅" if outcome == "won" else "❌"
            print(f"  {mark} {b['home']} {b['result']} vs {b['away']} "
                  f"({b['bet_type']} @ {b['odds']}) → {b['profit']:+.2f}€")

    _recalc_stats(tracking)
    return settled_count


def _recalc_stats(tracking):
    bets = tracking["bets"]
    total = len(bets)
    won = sum(1 for b in bets if b.get("status") == "won")
    lost = sum(1 for b in bets if b.get("status") == "lost")
    pending = sum(1 for b in bets if b.get("status") == "pending")
    profit = sum(b.get("profit", 0) or 0 for b in bets if b.get("status") != "pending")
    staked = sum(b.get("stake", 0) for b in bets if b.get("status") != "pending")
    roi = (profit / staked * 100) if staked > 0 else 0
    tracking["stats"] = {
        "total": total, "won": won, "lost": lost, "pending": pending,
        "profit": round(profit, 2), "staked": round(staked, 2), "roi": round(roi, 1),
    }


def load_tracking():
    try:
        if os.path.exists(TRACKING_FILE):
            with open(TRACKING_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {"bets": [], "stats": {}}


def save_tracking(tracking):
    with open(TRACKING_FILE, "w") as f:
        json.dump(tracking, f, indent=2, default=str)


def main():
    print("=" * 60)
    print("🏁 RÈGLEMENT DES PARIS")
    print("=" * 60)

    if not FOOTBALL_API_KEY:
        print("❌ FOOTBALL_API_KEY non configurée")
        return

    tracking = load_tracking()
    pending = sum(1 for b in tracking["bets"] if b.get("status") == "pending")
    print(f"📊 {pending} pari(s) en attente sur {len(tracking['bets'])}")

    settled = settle_bets(tracking)

    save_tracking(tracking)

    s = tracking.get("stats", {})
    print(f"\n✅ {settled} pari(s) réglé(s) ce run")
    print(f"📈 Bilan: {s.get('won', 0)}W / {s.get('lost', 0)}L | "
          f"ROI {s.get('roi', 0):+.1f}% | Profit {s.get('profit', 0):+.2f}€")


if __name__ == "__main__":
    main()
