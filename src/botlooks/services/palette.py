import io

from PIL import Image, ImageDraw, ImageFont

from botlooks.domain.schemas import NamedColor

_WIDTH = 800
_HEIGHT = 360
_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _load_font() -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(_FONT_PATH, 12)
    except OSError:
        return ImageFont.load_default()


def _draw_row(
    draw: ImageDraw.ImageDraw,
    colors: list[NamedColor],
    swatch_y: int,
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
) -> None:
    for i, color in enumerate(colors):
        x = i * 100
        draw.rectangle((x, swatch_y, x + 99, swatch_y + 99), fill=color.hex)
        draw.text((x + 4, swatch_y + 104), color.name[:16], fill="black", font=font)
        draw.text((x + 4, swatch_y + 122), color.hex.upper(), fill="black", font=font)


def render_palette(palette: list[NamedColor], avoid: list[NamedColor]) -> bytes:
    img = Image.new("RGB", (_WIDTH, _HEIGHT), "white")
    draw = ImageDraw.Draw(img)
    font = _load_font()
    draw.text((4, 14), "Ваша палитра", fill="black", font=font)
    _draw_row(draw, palette, 40, font)
    draw.text((4, 194), "Лучше избегать", fill="black", font=font)
    _draw_row(draw, avoid, 220, font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
