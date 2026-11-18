from pydantic import BaseModel, Field, model_validator

FIELD_LABELS = {
    "name": "Объект", "stage": "Стадия", "state": "Состояние", "progress": "Готовность",
    "customer": "Заказчик", "construction_deputy": "Строительный заместитель",
    "project_manager": "Руководитель проекта", "contract_cost": "Стоимость по договорам",
    "spent": "Освоено", "risks": "Риски", "external_id": "Идентификатор в ВИС",
}


class TrafficRules(BaseModel):
    exchange_yellow_days: int = Field(default=8, ge=1, le=3650)
    exchange_red_days: int = Field(default=15, ge=2, le=3650)
    overdue_red_days: int = Field(default=31, ge=1, le=3650)
    unsigned_red_percent: int = Field(default=50, ge=0, le=100)
    stagnation_days: int = Field(default=56, ge=7, le=365)
    required_fields: list[str] = Field(default_factory=lambda: [
        "name", "stage", "state", "progress", "customer",
        "construction_deputy", "project_manager", "contract_cost",
    ])

    @model_validator(mode="after")
    def valid_thresholds(self):
        if self.exchange_yellow_days >= self.exchange_red_days:
            raise ValueError("Красный порог обмена должен быть больше жёлтого")
        allowed = {"name", "stage", "state", "progress", "customer", "construction_deputy",
                   "project_manager", "contract_cost", "spent", "risks", "external_id"}
        if not set(self.required_fields) <= allowed:
            raise ValueError("Неизвестное обязательное поле")
        return self
