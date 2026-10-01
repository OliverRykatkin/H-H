"""Verbal sannolikhetsskala och procentformat — definierade på ett enda ställe (D3)."""
from __future__ import annotations

def verbal(p: float) -> str:
    """Gränserna 0,10 / 0,35 / 0,65 / 0,90 (D3). Exakt 0,35 och 0,65 ger 'Jämnt'."""
    if p < 0.10:
        return "Väldigt osannolikt"
    if p < 0.35:
        return "Osannolikt"
    if p <= 0.65:
        return "Jämnt"
    if p <= 0.90:
        return "Troligt"
    return "Väldigt troligt"


def display_pct(p: float) -> str:
    """Visar aldrig 0 % eller 100 % från simuleringar."""
    if p < 0.01:
        return "<1 %"
    if p > 0.99:
        return ">99 %"
    return f"{round(p * 100):.0f} %"
