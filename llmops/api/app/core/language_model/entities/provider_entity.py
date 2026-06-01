from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.core.exceptions import FailException, NotFoundException

from .default_model_parameter_template import DEFAULT_MODEL_PARAMETER_TEMPLATE
from .model_entity import ModelEntity, ModelType


class ProviderEntity(BaseModel):
    name: str = ""
    label: str = ""
    description: str = ""
    icon: str = ""
    background: str = ""
    supported_model_types: list[ModelType] = Field(default_factory=list)


class Provider(BaseModel):
    name: str
    position: int
    provider_entity: ProviderEntity
    provider_path: Path
    model_entity_map: dict[str, ModelEntity] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._provider_init()

    def get_model_entity(self, model_name: str) -> ModelEntity:
        model_entity = self.model_entity_map.get(model_name)
        if model_entity is None:
            raise NotFoundException("Language model does not exist")
        return model_entity

    def get_model_entities(self) -> list[ModelEntity]:
        return list(self.model_entity_map.values())

    def _provider_init(self) -> None:
        if self.model_entity_map:
            return

        positions_yaml_path = self.provider_path / "positions.yaml"
        with positions_yaml_path.open(encoding="utf-8") as f:
            positions_yaml_data = yaml.safe_load(f) or []
        if not isinstance(positions_yaml_data, list):
            raise FailException("positions.yaml must contain a list")

        for model_name in positions_yaml_data:
            model_yaml_path = self.provider_path / f"{model_name}.yaml"
            with model_yaml_path.open(encoding="utf-8") as f:
                model_yaml_data = yaml.safe_load(f) or {}
            model_yaml_data["parameters"] = self._normalize_parameters(model_yaml_data.get("parameters") or [])
            self.model_entity_map[str(model_name)] = ModelEntity(**model_yaml_data)

    @staticmethod
    def _normalize_parameters(yaml_parameters: list[dict]) -> list[dict]:
        parameters = []
        for parameter in yaml_parameters:
            parameter_data = dict(parameter)
            template_key = parameter_data.pop("use_template", None)
            if template_key:
                default_parameter = DEFAULT_MODEL_PARAMETER_TEMPLATE.get(str(template_key))
                if default_parameter is None:
                    raise FailException(f"Unknown model parameter template: {template_key}")
                parameters.append({**default_parameter, **parameter_data})
            else:
                parameters.append(parameter_data)
        return parameters
