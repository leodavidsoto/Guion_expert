"""Bridge Guion_expert ↔ OpenMontage.

Submódulos:
- openmontage_export  : Traduce proyectos Guion_expert al contrato OpenMontage v1.
- asset_generator     : Orquesta generación (FLUX/I2V/Suno/mmaudio) desde scene_plan.

`asset_generator` importa de `webapp/` (única excepción al rule
bridge-desacoplado-de-webapp; ver docstring del módulo para el porqué).
"""
from .openmontage_export import export_project_to_openmontage

# Import lazy opcional: asset_generator requiere httpx/structlog instalados.
# Si no están (ej. contenedor mínimo que solo corre el bridge de export),
# no queremos crashear import-time.
try:
    from .asset_generator import (
        BudgetExceeded,
        BudgetTracker,
        ResolvedAsset,
        SceneAssetBundle,
        generate_all_assets,
        generate_hero_music,
        plan_cost_estimate,
        process_scene,
        train_lora_if_needed,
    )

    __all__ = [
        "export_project_to_openmontage",
        # asset_generator
        "generate_all_assets",
        "process_scene",
        "train_lora_if_needed",
        "generate_hero_music",
        "plan_cost_estimate",
        "BudgetTracker",
        "BudgetExceeded",
        "ResolvedAsset",
        "SceneAssetBundle",
    ]
except ImportError:
    # Deps opcionales faltantes (httpx/structlog) — el export funciona igual.
    __all__ = ["export_project_to_openmontage"]
