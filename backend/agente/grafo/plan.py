"""Contrato estricto para decidir cómo atender una consulta del usuario."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agente.utils.logger import log_event
from agente.utils.tooler import list_templates, validate_template_parameters

AccionPlan = Literal["responder_directo", "usar_plantilla", "generar_cypher"]
Cardinality = Literal["one", "many"]


class Plan(BaseModel):
    """Decisión validada del planificador antes de cualquier ejecución."""

    model_config = ConfigDict(extra="forbid", strict=True)

    accion: AccionPlan
    usar_schema: bool = False
    template_id: str | None = None
    parametros: dict[str, Any] = Field(default_factory=dict)
    objetivo_cypher: str | None = None
    cardinality: Cardinality = "one"

    @model_validator(mode="before")
    @classmethod
    def normalizar_variantes_proveedor(cls, value: Any) -> Any:
        """Normalize harmless structured-output variants before strict validation."""
        if not isinstance(value, Mapping):
            return value

        normalized = dict(value)
        for field_name in ("template_id", "objetivo_cypher"):
            field_value = normalized.get(field_name)
            if isinstance(field_value, str) and not field_value.strip():
                normalized[field_name] = None
        if "parametros" in normalized and normalized["parametros"] is None:
            normalized["parametros"] = {}
        return normalized

    @model_validator(mode="after")
    def validar_accion(self) -> Plan:
        """Aplica las combinaciones permitidas para cada acción del plan."""
        log_event("plan", "validation_started", action=self.accion)
        if self.accion == "responder_directo":
            if self.cardinality != "one":
                raise ValueError("responder_directo debe usar cardinality=one")
            if self.template_id is not None or self.objetivo_cypher is not None:
                raise ValueError("responder_directo no admite template_id ni objetivo_cypher")
            if self.usar_schema:
                raise ValueError("responder_directo debe usar_schema=false")
            return self

        if self.accion == "usar_plantilla":
            if self.cardinality != "one":
                raise ValueError("usar_plantilla debe usar cardinality=one")
            template_ids = {template.id for template in list_templates()}
            if self.template_id not in template_ids:
                raise ValueError("usar_plantilla requiere un template_id válido del catálogo")
            if self.objetivo_cypher is not None:
                raise ValueError("usar_plantilla no admite objetivo_cypher")
            if self.usar_schema:
                raise ValueError("usar_plantilla debe usar_schema=false")
            try:
                validate_template_parameters(
                    self.template_id,
                    self.parametros,
                    allow_entity_candidates=True,
                )
            except ValueError as exc:
                raise ValueError(
                    "usar_plantilla requiere parámetros completos y seguros"
                ) from exc
            return self

        if self.template_id is not None:
            raise ValueError("generar_cypher no admite template_id")
        if not isinstance(self.objetivo_cypher, str) or not self.objetivo_cypher.strip():
            raise ValueError("generar_cypher requiere un objetivo_cypher no vacío")
        if not self.usar_schema:
            raise ValueError("generar_cypher debe usar_schema=true")
        self.objetivo_cypher = self.objetivo_cypher.strip()
        return self
