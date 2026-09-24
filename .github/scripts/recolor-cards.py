#!/usr/bin/env python3
"""Remappe les couleurs de langages GitHub vers la palette Tokyo Night.

github-profile-summary-cards code en dur les couleurs officielles de GitHub
par langage (Shell vert vif, HTML rouge brique, JS jaune...). Aucun thème ne
les change, et elles jurent avec le fond tokyonight. On les remplace donc
après génération, avant le commit.

Une couleur inconnue est laissée telle quelle : un nouveau langage garde sa
couleur GitHub plutôt que de disparaître.
"""
import pathlib
import sys

# couleur GitHub -> équivalent Tokyo Night
PALETTE = {
    "#89e051": "#9ece6a",  # Shell        -> vert
    "#3572a5": "#7dcfff",  # Python       -> cyan
    "#00add8": "#73daca",  # Go           -> turquoise
    "#3178c6": "#7aa2f7",  # TypeScript   -> bleu
    "#f1e05a": "#e0af68",  # JavaScript   -> jaune
    "#e34c26": "#f7768e",  # HTML         -> rouge
    "#b07219": "#ff9e64",  # Java         -> orange
    "#563d7c": "#bb9af7",  # CSS          -> violet
    "#844fba": "#9d7cd8",  # HCL          -> violet foncé
    "#a52a22": "#db4b4b",  # Jinja        -> rouge sombre
    "#427819": "#41a6b5",  # Makefile     -> sarcelle
    "#c6538c": "#ff007c",  # SCSS         -> magenta
    "#724b3b": "#9a7151",  # Mustache     -> brun
    "#384d54": "#394b70",  # Dockerfile   -> bleu nuit
    "#cb171e": "#db4b4b",  # YAML         -> rouge sombre
    "#41b883": "#41a6b5",  # Vue          -> sarcelle
    "#ecdebe": "#cfc9c2",  # Roff         -> beige
    "#292929": "#565f89",  # JSON         -> gris-bleu
    "#4f5d95": "#7aa2f7",  # PHP          -> bleu
    "#701516": "#db4b4b",  # Ruby         -> rouge sombre
    "#dea584": "#ff9e64",  # Rust         -> orange
    "#a270ba": "#bb9af7",  # C#           -> violet
    "#f34b7d": "#f7768e",  # C++          -> rouge
    "#555555": "#565f89",  # C            -> gris-bleu
}

root = pathlib.Path(__file__).resolve().parents[2] / "profile-summary-card-output"
if not root.is_dir():
    sys.exit(f"dossier introuvable : {root}")

changed = 0
for svg in sorted(root.rglob("*.svg")):
    original = svg.read_text(encoding="utf-8")
    text = original
    for github_color, tokyo in PALETTE.items():
        # les SVG mélangent les casses (#3572A5 / #3572a5)
        text = text.replace(github_color, tokyo).replace(github_color.upper(), tokyo)
    if text != original:
        svg.write_text(text, encoding="utf-8")
        changed += 1
        print(f"  recolorié  {svg.relative_to(root.parent)}")

print(f"{changed} fichier(s) recolorié(s)")
