"""Draws the app logo and writes app/assets/icon.png, icon-64.png and icon.ico.

The logo: a dark tile with a phone outline and a heartbeat line that spikes
through it (a "panic" on the phone's pulse), in the app's cyan accent.
Run:  python tools/make_icon.py   (needs Pillow; only for changing the logo)
"""
import os
from PIL import Image, ImageDraw, ImageFilter

S = 1024                     # draw large, then scale down for smooth edges
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app", "assets")
CYAN = (34, 211, 238)
AMBER = (251, 146, 60)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def draw() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # tile with a vertical gradient
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        gd.line([(0, y), (S, y)], fill=lerp((22, 32, 52), (8, 12, 22), y / S) + (255,))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([24, 24, S - 24, S - 24], radius=210, fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([24, 24, S - 24, S - 24], radius=210, outline=(48, 64, 92, 255), width=10)

    # phone outline
    px0, py0, px1, py1 = 330, 170, 694, 854
    d.rounded_rectangle([px0, py0, px1, py1], radius=70, outline=(150, 170, 200, 255), width=30)

    # heartbeat line, with a soft glow under it
    y = 540
    pts = [(110, y), (360, y), (420, y - 40), (470, y + 60), (530, 280), (590, 760), (640, y - 20),
           (680, y), (914, y)]
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).line(pts, fill=CYAN + (170,), width=70, joint="curve")
    glow = glow.filter(ImageFilter.GaussianBlur(28))
    img = Image.alpha_composite(img, glow)
    d = ImageDraw.Draw(img)
    d.line(pts, fill=CYAN + (255,), width=46, joint="curve")
    for x in (110, 914):                      # round line ends
        d.ellipse([x - 23, y - 23, x + 23, y + 23], fill=CYAN + (255,))

    # the "panic" point: amber dot at the top of the spike
    d.ellipse([530 - 50, 280 - 50, 530 + 50, 280 + 50], fill=AMBER + (255,), outline=(8, 12, 22, 255), width=14)
    return img


def main():
    os.makedirs(OUT, exist_ok=True)
    big = draw()
    big.resize((256, 256), Image.LANCZOS).save(os.path.join(OUT, "icon.png"))
    big.resize((64, 64), Image.LANCZOS).save(os.path.join(OUT, "icon-64.png"))
    big.resize((256, 256), Image.LANCZOS).save(
        os.path.join(OUT, "icon.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    big.resize((512, 512), Image.LANCZOS).save(os.path.join(OUT, "..", "..", "logo.png"))
    print("wrote", os.path.abspath(OUT))


if __name__ == "__main__":
    main()
