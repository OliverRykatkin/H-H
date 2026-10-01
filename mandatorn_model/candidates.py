"""mandatorn_model.candidates — utbrutet ordagrant ur app.py (fas 1)."""
from __future__ import annotations

from io import StringIO
import pandas as pd
import requests
from mandatorn_model.constants import (
    CANDIDATES_URL,
    CONSTITUENCIES,
    PARTIES,
    VALKRETS_MAPPING,
)

def fetch_candidates_text(url: str = CANDIDATES_URL) -> str:
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    # Dekoda med utf-8-sig för att ta bort BOM-tecknet i början av filen
    return resp.content.decode("utf-8-sig")


def parse_candidates(text: str) -> pd.DataFrame:
    """
    Kandidaturdata från Valmyndigheten för riksdagsvalet 2026.

    Filtrerar på VALTYP=RD, mappar valkretsnamn till appens interna format
    och returnerar en DataFrame med kolumnerna:
      parti, valkrets, namn, ordning, alder, kon, hemkommun
    """
    df = pd.read_csv(StringIO(text), sep=";", on_bad_lines="skip")

    # Namnfrekvens över HELA rådatan (innan filtrering) — används längre ner
    # för att avgöra vilken stavning som är den "riktiga" när samma person
    # råkar förekomma dubbelt med en stavningsvariant.
    name_freq = df["NAMN"].value_counts()

    rd = df[df["VALTYP"] == "RD"].copy()

    # Filtrera bort rikslistan ("HELA LANDET") — den innehåller nationellt
    # placerade kandidater som dyker upp under alla valkretsar i rådata och
    # skulle blanda ihop lokala listor med den nationella listan.
    rd = rd[rd["VALKRETSBETECKNING PÅ VALSEDELN"].str.strip() != "HELA LANDET"]

    rd["parti"] = rd["PARTIFÖRKORTNING"].str.strip()
    rd["valkrets"] = rd["VALKRETSNAMN"].map(VALKRETS_MAPPING)
    rd["ordning"] = pd.to_numeric(rd["ORDNING"], errors="coerce")
    # Tomma åldersfält i råfilen är blanksteg (" "), inte NaN — coerce till
    # numeriskt så att int(c["alder"]) inte kraschar i kandidattabellerna.
    rd["alder"] = pd.to_numeric(rd["ÅLDER_PÅ_VALDAGEN"], errors="coerce")

    rd = rd[["parti", "valkrets", "NAMN", "ordning", "alder", "KÖN", "FOLKBOKFÖRINGSKOMMUN"]].copy()
    rd.columns = ["parti", "valkrets", "namn", "ordning", "alder", "kon", "hemkommun"]
    rd = rd.dropna(subset=["valkrets", "namn"])
    rd = rd[rd["parti"].isin(PARTIES)]

    # Rådatan innehåller ibland dubbletter av samma kandidat på samma
    # listplats med en stavningsvariant i namnet (t.ex. "Rinqvist" vs
    # "Ringqvist" för samma person). Två kandidater kan inte dela listplats
    # på riktigt, så en krock på (parti, valkrets, ordning) är alltid ett
    # datafel i källan. Behåll den vanligast förekommande stavningen
    # (namnfrekvensen inkluderar rikslistans "HELA LANDET"-rader, där den
    # riktiga stavningen upprepas per valkrets) och släpp resten.
    rd["_namefreq"] = rd["namn"].map(name_freq)
    rd = rd.sort_values("_namefreq", ascending=False)
    rd = rd.drop_duplicates(subset=["parti", "valkrets", "ordning"], keep="first")
    rd = rd.drop(columns="_namefreq").sort_values(["valkrets", "parti", "ordning"])

    return rd.reset_index(drop=True)


def predict_elected_candidates(fixed_seats: dict, candidates_df: pd.DataFrame) -> dict:
    """
    Matchar mandatprediktionen mot kandidatlistorna och returnerar
    de förväntade invalda riksdagsledamöterna per valkrets och parti.

    Strategi (tre pass):
      1. Bygg hemkommun→valkrets-mappning från data: varje kommuns "hemvalkrets"
         är den valkrets som listar flest kandidater från den kommunen.
      2. Per valkrets (störst först): välj i första hand kandidater vars hemkommun
         tillhör denna valkrets — de "reserveras" för sin hemmavalkrets.
      3. Fyll resterande platser med kandidater vars hemkommun är okänd.
      4. Sista utväg: ta vem som helst på den lokala listan.

    Logiken gör att rikspolitiker (Ulf Kristersson i Södermanland, Elisabeth
    Svantesson i Örebro) tilldelas rätt valkrets även om de finns på fler listor.

    Returns: {valkrets: {parti: [{'namn':…, 'ordning':…, 'alder':…, 'kon':…, 'hemkommun':…}]}}
    """
    if candidates_df.empty:
        return {valkrets: {} for valkrets in fixed_seats}

    # ── Hemkommun → naturlig valkrets (datadrivet) ──────────────────────────
    # För varje hemkommun: den valkrets där flest kandidater med den kommunen
    # är listade. Ger en proxy för geografi utan hårdkodad geodata.
    _hk = candidates_df[candidates_df["hemkommun"].notna() & candidates_df["ordning"].notna()]
    hemkommun_to_valkrets: dict[str, str] = {}
    if not _hk.empty:
        # Primär sortering: lägsta ordningsnummer (en kandidat på plats 2 i
        # Dalarna men plats 32 i Stockholm pekar tydligt på Dalarna).
        # Sekundär sortering: antal kandidater vid oavgjort (Stockholm stad
        # har många fler plats-1-kandidater med hemkommun Stockholm än vad
        # Östergötland har, trots att båda har min_ordning = 1).
        _stats = (
            _hk.groupby(["hemkommun", "valkrets"])["ordning"]
            .agg(min_ordning="min", count="size")
            .reset_index()
            .sort_values(["min_ordning", "count"], ascending=[True, False])
        )
        hemkommun_to_valkrets = (
            _stats
            .drop_duplicates(subset="hemkommun")
            .set_index("hemkommun")["valkrets"]
            .to_dict()
        )

    cdf = candidates_df.copy()
    cdf["natural_valkrets"] = cdf["hemkommun"].map(hemkommun_to_valkrets)

    # ── Lås kandidater till sin hemmavalkrets ────────────────────────────────
    # En kandidat låses till sin naturliga valkrets om tre villkor är uppfyllda:
    #   1. Hemkommun mappas till en känd valkrets (natural_valkrets finns)
    #   2. Kandidaten faktiskt finns på den valkretsens lista
    #   3. Partiet vinner minst ett fast mandat i den valkretsen
    # Låsta kandidater är INTE tillgängliga för andra valkretsar — de räknas
    # enbart för sin hemmavalkrets, oavsett hur högt de listas på andras listor.

    party_wins_in: dict[str, set[str]] = {}
    for c, pdict in fixed_seats.items():
        for p, n in pdict.items():
            if n > 0:
                party_wins_in.setdefault(p, set()).add(c)

    listed_in: set[tuple] = set(zip(cdf["parti"], cdf["namn"], cdf["valkrets"]))
    const_seats_dict = {k: v["seats"] for k, v in CONSTITUENCIES.items()}

    locked_to: dict[str, str] = {}   # "{parti}|{namn}" → hemmavalkrets

    # Lås 1: hemkommun-baserad (primär)
    for _, row in cdf.drop_duplicates(["parti", "namn"]).iterrows():
        nv = row.get("natural_valkrets")
        if not nv:
            continue
        parti, namn = row["parti"], row["namn"]
        if (
            (parti, namn, nv) in listed_in
            and nv in party_wins_in.get(parti, set())
        ):
            locked_to[f"{parti}|{namn}"] = nv

    # Lås 2: för kandidater utan hemkommun som finns på flera listor
    # (t.ex. partiledare vars adress är skyddad) — tilldela minsta valkrets
    # där partiet vinner mandat och kandidaten är listad. Partiledare placeras
    # typiskt på sin hemmavalkrets listade oavsett storlek, och den minsta
    # listan de finns på är ofta den "riktiga" (de är mest unika/avgörande där).
    multi_no_hk = (
        cdf[cdf["natural_valkrets"].isna()]
        .groupby(["parti", "namn"])["valkrets"]
        .nunique()
    )
    for (parti, namn) in multi_no_hk[multi_no_hk > 1].index:
        key = f"{parti}|{namn}"
        if key in locked_to:
            continue   # redan låst via hemkommun
        appearances = cdf[
            (cdf["parti"] == parti) & (cdf["namn"] == namn)
        ]["valkrets"].tolist()
        eligible = [v for v in appearances if v in party_wins_in.get(parti, set())]
        if not eligible:
            continue
        home = min(eligible, key=lambda v: const_seats_dict.get(v, 999))
        locked_to[key] = home

    # ── Allokera mandat ──────────────────────────────────────────────────────
    # Processen behöver inte storleksordnas — låsningen hanterar konflikten.
    # Kandidater sorteras i ordningsföljd per valkretslista.
    # Pass 1: plocka kandidater som är tillgängliga (ej låsta till annan valkrets)
    # Pass 2: sista utväg — ta låsta-till-annan om lokala kandidater inte räcker

    elected: set[str] = set()
    result: dict = {}

    for valkrets, party_seats in fixed_seats.items():
        result[valkrets] = {}
        for parti, n_seats in party_seats.items():
            if n_seats == 0:
                continue

            local = cdf[
                (cdf["parti"] == parti) &
                (cdf["valkrets"] == valkrets)
            ].sort_values("ordning")

            chosen: list = []

            # Pass 1: ta kandidater som inte är låsta till annan valkrets
            for _, row in local.iterrows():
                key = f"{parti}|{row['namn']}"
                if key in elected:
                    continue
                lock = locked_to.get(key)
                if lock and lock != valkrets:
                    continue   # reserverad för sin hemmavalkrets
                chosen.append(row.to_dict())
                elected.add(key)
                if len(chosen) == n_seats:
                    break

            # Pass 2: sista utväg — ta låsta kandidater om listan är för kort
            if len(chosen) < n_seats:
                for _, row in local.iterrows():
                    key = f"{parti}|{row['namn']}"
                    if key in elected:
                        continue
                    chosen.append(row.to_dict())
                    elected.add(key)
                    if len(chosen) == n_seats:
                        break

            if chosen:
                result[valkrets][parti] = chosen

    return result


def predict_adjustment_constituencies(
    adjustment: dict,
    fixed_seats: dict,
    constituency_votes: dict,
) -> dict:
    """
    Beräknar vilka valkretsar som ger ett parti dess utjämningsmandat.

    Använder samma Sainte-Laguë-logik som Valmyndigheten: efter att fasta
    mandat är fördelade fortsätter kvotserien för varje (parti, valkrets)-par.
    Utjämningssätet går iterativt till den valkrets med högst nästa kvot.

    Divisorserien: 1,2 → 3 → 5 → 7 → … (modifierad Sainte-Laguë)

    Returns: {parti: [valkrets1, valkrets2, …]}  (längd = antal adj-mandat)
    """
    def _next_divisor(k: int) -> float:
        return 1.2 if k == 0 else float(2 * k + 1)

    # Skalningsfaktor per valkrets: antal fasta mandatplatser är proportionellt
    # mot antalet röstberättigade. Genom att multiplicera röstandel med
    # mandatantal approximerar vi faktiska röstetal — annars "vinner" alltid
    # Gotland (2 mandat, delar med 1,2) mot Stockholm (42 mandat, delar med 17).
    const_seats = {k: v["seats"] for k, v in CONSTITUENCIES.items()}

    # Startläge: antal fasta mandat per (parti, valkrets)
    seat_tally: dict = {}
    for constituency, party_dict in fixed_seats.items():
        for party, seats in party_dict.items():
            seat_tally[(party, constituency)] = int(seats)

    result = {}
    for party, n_adj in adjustment.items():
        if n_adj == 0:
            continue
        local_tally = {c: seat_tally.get((party, c), 0) for c in constituency_votes}
        assigned = []
        for _ in range(n_adj):
            best_c, best_q = None, -1.0
            for constituency, votes in constituency_votes.items():
                pct = votes.get(party, 0.0)
                # Skala till pseudo-röster via valkretsens mandatantal
                scaled_votes = pct * const_seats.get(constituency, 1)
                k = local_tally.get(constituency, 0)
                q = scaled_votes / _next_divisor(k)
                if q > best_q:
                    best_q = q
                    best_c = constituency
            if best_c:
                assigned.append(best_c)
                local_tally[best_c] = local_tally.get(best_c, 0) + 1
        if assigned:
            result[party] = assigned
    return result


def predict_adjustment_candidates(
    adj_constituencies: dict,
    candidates_df: pd.DataFrame,
    elected_fixed: dict,
) -> dict:
    """
    Plockar rätt kandidat för varje utjämningsmandat baserat på vilken
    valkrets mandatet tilldelas (från predict_adjustment_constituencies).

    För varje (parti, valkrets)-utjämningssäte väljs nästa icke-invalda
    kandidat på den valkretsens lista i ordningsföljd.

    Args:
        adj_constituencies: {parti: [valkrets1, valkrets2, …]}
        candidates_df:      kandidatregistret
        elected_fixed:      redan invalda via fasta mandat

    Returns: {parti: [{'namn':…, 'ordning':…, 'alder':…, 'kon':…,
                        'hemkommun':…, 'adj_valkrets':…}]}
    """
    if candidates_df.empty:
        return {}

    # Samla alla som redan vunnit ett fast mandat
    already_elected: set[str] = set()
    for valkrets, party_dict in elected_fixed.items():
        for parti, cands in party_dict.items():
            for c in cands:
                already_elected.add(f"{parti}|{c['namn']}")

    result = {}
    for parti, constituencies in adj_constituencies.items():
        chosen = []
        picked_this_round: set[str] = set()

        for adj_valkrets in constituencies:
            pool = candidates_df[
                (candidates_df["parti"] == parti) &
                (candidates_df["valkrets"] == adj_valkrets)
            ].sort_values("ordning")

            for _, row in pool.iterrows():
                key = f"{parti}|{row['namn']}"
                if key in already_elected or key in picked_this_round:
                    continue
                rec = row.to_dict()
                rec["adj_valkrets"] = adj_valkrets
                chosen.append(rec)
                picked_this_round.add(key)
                break

        if chosen:
            result[parti] = chosen
    return result
