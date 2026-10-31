#!/usr/bin/env python3
"""
FIT DIXON-COLES — estimation des paramètres sur l'historique réel
==================================================================
Estime l'avantage domicile (γ) et la correction petits scores (ρ) par
maximum de vraisemblance sur les matchs passés (Understat, gratuit).

Méthode: les forces attaque/défense des équipes sont fixées par leur xG
(fiable, faible variance), puis on n'estime que 3 paramètres globaux
(μ, γ, ρ) en poolant toutes les ligues et saisons → estimation robuste.

Usage:  python fit.py
Sortie: γ (→ home_advantage = exp(γ)) et ρ (→ RHO).
"""

import json, urllib.request, urllib.parse, gzip, time
from math import log, exp, lgamma

import numpy as np
from scipy.optimize import minimize

import understat  # pour HEADERS / LEAGUE_KEYS

LEAGUES = {"EPL": "PL", "Bundesliga": "BL1", "Ligue 1": "FL1", "La liga": "PD"}
SEASONS = ["2022", "2023", "2024", "2025"]  # 4 saisons pleines


def fetch_league(league_key, season):
    url = f"https://understat.com/getLeagueData/{urllib.parse.quote(league_key)}/{season}"
    req = urllib.request.Request(url, headers=understat.HEADERS)
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = r.read()
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
    return json.loads(raw)


def team_xg_stats(data):
    """{titre: (attaque, défense)} = (xG marqué/m, xGA encaissé/m)."""
    out = {}
    for t in data["teams"].values():
        hist = t.get("history", [])
        if not hist:
            continue
        xgs = [m["xG"] for m in hist if m.get("xG") is not None]
        xgas = [m["xGA"] for m in hist if m.get("xGA") is not None]
        if xgs and xgas:
            out[t["title"]] = (sum(xgs) / len(xgs), sum(xgas) / len(xgas))
    return out


def collect_matches():
    all_matches = []
    for key, code in LEAGUES.items():
        for season in SEASONS:
            try:
                d = fetch_league(key, season)
                stats = team_xg_stats(d)
                for m in d.get("dates", []):
                    if not m.get("isResult"):
                        continue
                    h, a = m["h"]["title"], m["a"]["title"]
                    if h in stats and a in stats:
                        att_h, def_h = stats[h]
                        att_a, def_a = stats[a]
                        all_matches.append(
                            (att_h, def_h, att_a, def_a,
                             int(m["goals"]["h"]), int(m["goals"]["a"]))
                        )
            except Exception as e:
                print(f"  ⚠️ {key} {season}: {e}")
            time.sleep(0.4)
    return all_matches


def fit(all_matches):
    def negll(p):
        mu, gamma, rho = p
        ll = 0.0
        for att_h, def_h, att_a, def_a, hg, ag in all_matches:
            lam_h = exp(mu + log(att_h) + log(def_a) + gamma)
            lam_a = exp(mu + log(att_a) + log(def_h))
            ll += -lam_h + hg * log(lam_h) - lgamma(hg + 1)
            ll += -lam_a + ag * log(lam_a) - lgamma(ag + 1)
            tau = 1.0
            if hg == 0 and ag == 0:
                tau = 1.0 - lam_h * lam_a * rho
            elif hg == 0 and ag == 1:
                tau = 1.0 + lam_h * rho
            elif hg == 1 and ag == 0:
                tau = 1.0 + lam_a * rho
            elif hg == 1 and ag == 1:
                tau = 1.0 - rho
            if tau <= 1e-8:
                tau = 1e-8
            ll += log(tau)
        return -ll

    x0 = [log(1.35), 0.10, -0.10]
    res = minimize(negll, x0, method="Nelder-Mead",
                   options={"xatol": 1e-6, "fatol": 1e-6, "maxiter": 2000})
    return res.x, res  # mu, gamma, rho


if __name__ == "__main__":
    print("📥 Récupération des matchs historiques (Understat)...")
    matches = collect_matches()
    print(f"   → {len(matches)} matchs poolés")

    (mu, gamma, rho), res = fit(matches)
    print("\n=== RÉSULTATS DU FIT (Dixon-Coles) ===")
    print(f"μ (baseline log): {mu:+.4f}")
    print(f"γ (avantage domicile, log): {gamma:+.4f}")
    print(f"  → home_advantage = exp(γ) = {exp(gamma):.4f}")
    print(f"ρ (correction petits scores): {rho:+.4f}")
    print(f"convergence: {res.success}")

    print("\n=== À METTRE DANS LE MODÈLE ===")
    print(f"home_advantage = {exp(gamma):.2f}   (asymétrique: home ×{exp(gamma):.2f}, away inchangé)")
    print(f"RHO = {rho:.2f}")
