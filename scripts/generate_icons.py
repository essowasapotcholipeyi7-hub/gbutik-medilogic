"""
Script ponctuel (dev only, nécessite `pip install pillow` — pas ajouté à
requirements.txt) : génère des icônes PWA temporaires "MB" sur fond bleu
nuit de marque, en attendant un vrai logo "Ma Boutik".

Utilisation :
    pip install pillow
    python scripts/generate_icons.py

Remplacer ensuite simplement les fichiers PNG dans static/icons/ par de
vraies icônes : aucun changement de code nécessaire (mêmes noms/tailles).
"""
import os

from PIL import Image, ImageDraw, ImageFont

BRAND_BG = (11, 29, 53)  # #0b1d35
TEXT_FG = (45, 212, 191)  # #2dd4bf (accent)
TEXT = "MB"

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "icons")

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\arial.ttf",
]


def load_font(size):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def make_icon(size, out_path):
    img = Image.new("RGB", (size, size), BRAND_BG)
    draw = ImageDraw.Draw(img)

    font = load_font(int(size * 0.34))  # taille réduite : icônes "maskable" (~20% rognés sur les bords)

    bbox = draw.textbbox((0, 0), TEXT, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - w) / 2 - bbox[0], (size - h) / 2 - bbox[1]), TEXT, fill=TEXT_FG, font=font)

    img.save(out_path)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for size in (192, 512):
        out_path = os.path.join(OUT_DIR, f"icon-{size}.png")
        make_icon(size, out_path)
        print(f"généré : icon-{size}.png")
    print(f"\nIcônes écrites dans {OUT_DIR}")


if __name__ == "__main__":
    main()
