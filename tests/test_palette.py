import io

from PIL import Image

from botlooks.domain.schemas import NamedColor
from botlooks.services.palette import render_palette


def test_render_palette():
    pal = [NamedColor(name=f"c{i}", hex=f"#{i:02x}8040") for i in range(8)]
    avoid = [NamedColor(name="a", hex="#00FF00")] * 3
    img = Image.open(io.BytesIO(render_palette(pal, avoid)))
    assert img.format == "PNG" and img.size == (800, 360)
    assert img.convert("RGB").getpixel((50, 90)) == (0x00, 0x80, 0x40)
    assert img.convert("RGB").getpixel((750, 90)) == (0x07, 0x80, 0x40)
    assert img.convert("RGB").getpixel((50, 270)) == (0, 255, 0)


def test_render_palette_cyrillic_labels():
    pal = [NamedColor(name="Тёплый беж", hex="#C8A27A")] * 6
    avoid = [NamedColor(name="Кислотный", hex="#00FF00")] * 3
    assert render_palette(pal, avoid).startswith(b"\x89PNG")
