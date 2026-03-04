"""
wordcloud_helper.py
────────────────────
Genera imágenes de nube de palabras (WordCloud) a partir de diccionarios de frecuencia.
Requiere: pip install wordcloud

Si la librería no está instalada, retorna None y el dashboard usa el fallback de barras.
"""

try:
    from wordcloud import WordCloud
    _HAS_WORDCLOUD = True
except ImportError:
    _HAS_WORDCLOUD = False

import io

# Paleta de colores UNAM
_UNAM_COLORS = [
    "#002B5C", "#003F8A", "#0057B8", "#1E6FB5", "#3A86C8",
    "#D4AF37", "#B6932B", "#8C7121", "#5F4D15",
    "#2ECC71", "#27AE60", "#1ABC9C",
]

def _unam_color_func(word, font_size, position, orientation, random_state=None, **kwargs):
    import random
    return random.choice(_unam_colors_global)

_unam_colors_global = _UNAM_COLORS


def generate_wordcloud_image(
    word_freq: dict,
    width: int = 800,
    height: int = 400,
    background_color: str = "white",
    max_words: int = 80,
) -> bytes | None:
    """
    Genera una imagen PNG de nube de palabras.

    Parameters
    ----------
    word_freq : dict
        {palabra: frecuencia}
    width, height : int
        Tamaño de la imagen en píxeles.
    background_color : str
        Color de fondo.
    max_words : int
        Palabras máximas a mostrar.

    Returns
    -------
    bytes | None
        Imagen PNG como bytes, o None si wordcloud no está instalado.
    """
    if not _HAS_WORDCLOUD or not word_freq:
        return None

    try:
        wc = WordCloud(
            width=width,
            height=height,
            background_color=background_color,
            max_words=max_words,
            color_func=_unam_color_func,
            prefer_horizontal=0.85,
            relative_scaling=0.5,
            min_font_size=10,
            max_font_size=80,
        )
        wc.generate_from_frequencies(word_freq)
        buf = io.BytesIO()
        wc.to_image().save(buf, format="PNG")
        buf.seek(0)
        return buf.getvalue()
    except Exception:
        return None
