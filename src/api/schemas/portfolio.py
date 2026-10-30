from pydantic import BaseModel, ConfigDict, Field, model_validator


class PositionCreate(BaseModel):
    name: str
    amount: float                                  # актив > 0, пассив < 0
    rate: float = Field(ge=0, description="% годовых")
    maturity_months: int = Field(gt=0)
    repricing_months: int = Field(gt=0)

    @model_validator(mode="after")
    def repricing_not_after_maturity(self):
        if self.repricing_months > self.maturity_months:
            raise ValueError("repricing_months must be <= maturity_months")
        return self


class PositionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    amount: float
    rate: float
    maturity_months: int
    repricing_months: int
