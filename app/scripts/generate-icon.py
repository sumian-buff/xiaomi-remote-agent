"""Generate the project's GPL-3.0 microphone icon without external artwork."""

from pathlib import Path

from PIL import Image, ImageDraw


def generate_icon() -> Path:
    image = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, 248, 248), radius=52, fill="#172033")
    draw.rounded_rectangle((99, 48, 157, 145), radius=29, outline="white", width=12)
    draw.arc((76, 78, 180, 180), 0, 180, fill="white", width=12)
    draw.line((128, 177, 128, 208), fill="white", width=12)
    draw.line((99, 208, 157, 208), fill="white", width=12)
    destination = Path(__file__).resolve().parents[1] / "source" / "assets" / "app.ico"
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)])
    return destination


if __name__ == "__main__":
    print(generate_icon())
