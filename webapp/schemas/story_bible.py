"""
Story Bible — Schema Pydantic para la memoria global compartida.
================================================================
M1: Diccionario Global / Shared Story Bible

El Story Bible actúa como la única fuente de verdad inmutable del proyecto.
Contiene logline, ADN de personajes (want/need/flaw), ADN visual (paleta,
firma de iluminación) y ADN sonoro. Se genera una vez (post-concepto) y se
inyecta como contexto en todos los expertos subsiguientes.

Objetivo cuantificable:
- Reducir deriva de paleta visual entre escenas en 70%.
- Disminuir tokens de contexto en 25% (Story Bible comprimida reemplaza
  copiar el concepto entero en cada prompt).

Uso:
    from webapp.schemas.story_bible import StoryBible, CharacterProfile

    bible = StoryBible.model_validate(payload)
    context_block = bible.to_context_block()
"""
from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


# ============================================================
# Bloques del Story Bible
# ============================================================


class CharacterProfile(BaseModel):
    """Perfil psicológico completo de un personaje. Fuente de verdad para el Dialoguista."""

    name: str = Field(description="Nombre canónico del personaje.")
    role: Literal["protagonist", "antagonist", "ally", "secondary"] = Field(
        description="Rol narrativo."
    )
    want: str = Field(
        min_length=10,
        description="Lo que el personaje cree que necesita (deseo externo).",
    )
    need: str = Field(
        min_length=10,
        description="Lo que el personaje realmente necesita para completar su arco (interno).",
    )
    flaw: str = Field(
        min_length=10,
        description="Defecto fatal que crea fricción dramática y bloquea el 'need'.",
    )
    vocal_dna: str = Field(
        min_length=20,
        description=(
            "ADN vocal: cadencia sintáctica, longitud de sentencias, vocabulario idiosincrásico, "
            "muletillas, silencios, registros (formal/coloquial). "
            "Ej: 'Frases cortas. Pocas metáforas. Seco y directo. Nunca pide permiso. "
            "Usa el silencio como amenaza.'"
        ),
    )
    physical_signature: str = Field(
        default="",
        description="Descripción física inmutable: edad, complexión, marcas, vestimenta tipo.",
    )
    is_alive: bool = Field(default=True, description="Estado vital del personaje.")
    arc_state: Literal["static", "in_progress", "completed"] = Field(
        default="in_progress",
        description="Estado del arco de transformación.",
    )


class VisualDNA(BaseModel):
    """ADN visual del proyecto. Fuente de verdad para el Localizador y el Director Flow."""

    color_palette: list[str] = Field(
        min_length=2,
        max_length=6,
        description=(
            "Paleta cromática inmutable en 2-6 tokens. "
            "Ej: ['amber warm key', 'deep teal shadows', 'rim orange', 'muted skin midtones']."
        ),
    )
    lighting_signature: str = Field(
        min_length=20,
        description=(
            "Firma de iluminación del proyecto: tipo (Rembrandt, Mariposa, Chiaroscuro), "
            "temperatura Kelvin, ratio key/fill, motivación diegética predominante."
        ),
    )
    color_temperature_kelvin: int = Field(
        ge=2000,
        le=10000,
        description=(
            "Temperatura de color base en Kelvin. "
            "2700-3200K = tungsteno/golden hour (nostálgico, cálido). "
            "5000-7000K = luz natural/neón (alienante, clínico)."
        ),
    )
    visual_style: Literal[
        "photoreal_8k",
        "cinematic_35mm_kodak",
        "cinematic_35mm_fuji",
        "editorial_fashion",
        "documentary_handheld",
        "dystopian_graded",
        "anime_still",
        "noir_bw",
        "vintage_70s",
        "y2k_digital",
        "indie_a24",
    ] = Field(description="Estilo visual global inmutable para todo el proyecto.")
    aspect_ratio: Literal["16:9", "9:16", "1:1", "2.39:1"] = Field(
        default="16:9"
    )
    recurring_textures: list[str] = Field(
        default_factory=list,
        description="Texturas que deben aparecer consistentemente: 'grano 35mm fino', 'flare anamórfico'.",
    )
    location_anchors: list[str] = Field(
        default_factory=list,
        description="Locaciones fijas del proyecto con su visual signature.",
    )


class SonicDNA(BaseModel):
    """ADN sonoro del proyecto. Fuente de verdad para el bloque SonicAtmosphere."""

    global_mood: list[str] = Field(
        min_length=1,
        max_length=5,
        description="Tono emocional global del proyecto en 1-5 keywords.",
    )
    music_genre: str = Field(
        min_length=10,
        description="Género/subgénero musical dominante y brief para Suno.",
    )
    bpm_range: str = Field(
        default="",
        description="Rango de BPM característico. Ej: '60-80bpm para momentos contemplativos'.",
    )
    key_references: list[str] = Field(
        default_factory=list,
        description="Artistas/scores de referencia global: 'Hans Zimmer', 'Max Richter'.",
    )
    leitmotifs: list[str] = Field(
        default_factory=list,
        description="Motivos recurrentes: 'piano descendente de 3 notas en momentos de duda'.",
    )
    sonic_textures: list[str] = Field(
        default_factory=list,
        description="Texturas sonoras que reaparecen: 'estática analógica', 'viento de páramo'.",
    )


class NarrativeBeat(BaseModel):
    """Beat estructural del Save the Cat. 15 beats con ventanas porcentuales vinculantes."""

    name: str
    pct_start: float = Field(ge=0.0, le=100.0)
    pct_end: float = Field(ge=0.0, le=100.0)
    description: str
    is_gate: bool = Field(
        default=False,
        description="Si True, el beat es un umbral de no retorno (Catalyst, Break Into Two, etc.).",
    )


# Tabla de los 15 beats Save the Cat con ventanas porcentuales vinculantes
SAVE_THE_CAT_BEATS: list[NarrativeBeat] = [
    NarrativeBeat(name="Opening Image",       pct_start=0.0,  pct_end=1.0,   description="Constante inicial. Estado ambiental que el héroe debe rectificar.", is_gate=False),
    NarrativeBeat(name="Theme Stated",        pct_start=4.5,  pct_end=5.5,   description="Variable temática encubierta. Función objetivo del cierre del arco.", is_gate=False),
    NarrativeBeat(name="Set-Up",              pct_start=1.0,  pct_end=10.0,  description="Carga completa de valores de referencia del protagonista (flaw incluido).", is_gate=False),
    NarrativeBeat(name="Catalyst",            pct_start=9.5,  pct_end=10.5,  description="Incidente perturbador. Quiebre dramático en la matriz de la historia.", is_gate=True),
    NarrativeBeat(name="Debate",              pct_start=10.0, pct_end=20.0,  description="Simulación de resistencia. Vacilación fisiológica ante el cambio.", is_gate=False),
    NarrativeBeat(name="Break Into Two",      pct_start=19.5, pct_end=20.5,  description="Puerta de enlace sin retorno. Transición al nuevo mundo operativo.", is_gate=True),
    NarrativeBeat(name="B Story",             pct_start=21.5, pct_end=22.5,  description="Hilo paralelo. Relaciones interpersonales que modulan el subtexto principal.", is_gate=False),
    NarrativeBeat(name="Fun and Games",       pct_start=20.0, pct_end=50.0,  description="Zona de exploración heurística. Promesa de la premisa.", is_gate=False),
    NarrativeBeat(name="Midpoint",            pct_start=49.5, pct_end=50.5,  description="Vértice del grafo. Falsa victoria o derrota absoluta. Altera el vector de riesgo.", is_gate=True),
    NarrativeBeat(name="Bad Guys Close In",   pct_start=50.0, pct_end=75.0,  description="Compresión de variables de supervivencia. Riesgo externo e interno.", is_gate=False),
    NarrativeBeat(name="All is Lost",         pct_start=74.5, pct_end=75.5,  description="Colapso catastrófico del estado local. Entropía máxima.", is_gate=True),
    NarrativeBeat(name="Dark Night of the Soul", pct_start=75.0, pct_end=80.0, description="Retroalimentación introspectiva. Evaluación de fracasos para recalibrar.", is_gate=False),
    NarrativeBeat(name="Break Into Three",    pct_start=79.5, pct_end=80.5,  description="Síntesis lógica: A Story + B Story = Estrategia de Resolución.", is_gate=True),
    NarrativeBeat(name="Finale",              pct_start=80.0, pct_end=99.0,  description="Bucle de ejecución. Confrontación final. Aprendizaje aplicado.", is_gate=False),
    NarrativeBeat(name="Final Image",         pct_start=99.0, pct_end=100.0, description="Delta de transformación. Reflejo invertido del Opening Image.", is_gate=False),
]


class StoryBible(BaseModel):
    """
    Shared Story Bible — Memoria global persistente del proyecto.

    Generada una sola vez por el expert 'bible_writer' (post-concepto),
    inyectada como contexto en todos los experts subsiguientes.
    Se serializa en output/<timestamp>/story_bible.json.
    """

    # Identificación del proyecto
    project_title: str = Field(description="Título de trabajo del proyecto.")
    logline: str = Field(
        min_length=20,
        max_length=300,
        description="Logline de alto impacto en una frase.",
    )
    premise: str = Field(
        min_length=20,
        description="Premisa dramática: qué está en juego y por qué importa.",
    )
    genre: str = Field(description="Género principal + subgénero + tono.")
    formato: str = Field(description="Formato del proyecto (ej. CORTO, REEL_INSTAGRAM).")
    estructura: str = Field(description="Estructura narrativa elegida (ej. SAVE_THE_CAT).")

    # ADN de personajes
    characters: list[CharacterProfile] = Field(
        min_length=1,
        description="Perfiles completos de todos los personajes con nombre propio.",
    )

    # ADN visual y sonoro
    visual_dna: VisualDNA
    sonic_dna: SonicDNA

    # Thematic spine
    theme: str = Field(
        min_length=10,
        description="Tema central que el relato explora (no el plot, sino el argumento filosófico).",
    )
    opening_image_description: str = Field(
        default="",
        description="Descripción de la imagen inicial que define el estado 0.",
    )
    final_image_description: str = Field(
        default="",
        description="Descripción de la imagen final que contrasta con la inicial.",
    )

    # Metadata de confianza del clasificador (M6)
    classifier_confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Puntaje de confianza calibrado del clasificador para formato+estructura.",
    )
    classifier_justification: str = Field(
        default="",
        description="Justificación del clasificador para las decisiones tomadas.",
    )

    def to_context_block(self) -> str:
        """
        Serializa el Story Bible en un bloque de texto comprimido para inyectar
        en los prompts de los expertos. Diseñado para minimizar tokens (M8).
        """
        chars = "\n".join(
            f"  {c.name} ({c.role}): WANT={c.want[:60]} | NEED={c.need[:60]} | FLAW={c.flaw[:60]} | VOCAL={c.vocal_dna[:80]}"
            for c in self.characters
        )
        return (
            f"=== STORY BIBLE (fuente de verdad inmutable) ===\n"
            f"TÍTULO: {self.project_title}\n"
            f"LOGLINE: {self.logline}\n"
            f"PREMISA: {self.premise[:200]}\n"
            f"GÉNERO: {self.genre} | FORMATO: {self.formato} | ESTRUCTURA: {self.estructura}\n"
            f"TEMA: {self.theme}\n"
            f"\nPERSONAJES:\n{chars}\n"
            f"\nADN VISUAL:\n"
            f"  Paleta: {', '.join(self.visual_dna.color_palette)}\n"
            f"  Estilo: {self.visual_dna.visual_style}\n"
            f"  Iluminación: {self.visual_dna.lighting_signature[:120]}\n"
            f"  Temperatura: {self.visual_dna.color_temperature_kelvin}K\n"
            f"  Texturas: {', '.join(self.visual_dna.recurring_textures)}\n"
            f"\nADN SONORO:\n"
            f"  Mood global: {', '.join(self.sonic_dna.global_mood)}\n"
            f"  Música: {self.sonic_dna.music_genre[:120]}\n"
            f"  Referencias: {', '.join(self.sonic_dna.key_references)}\n"
            f"  Leitmotifs: {', '.join(self.sonic_dna.leitmotifs)}\n"
            f"=== FIN STORY BIBLE ===\n"
        )

    def get_character(self, name: str) -> CharacterProfile | None:
        """Busca un personaje por nombre (case-insensitive)."""
        name_lower = name.lower()
        for c in self.characters:
            if c.name.lower() == name_lower:
                return c
        return None
