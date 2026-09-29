import json

from openai import AsyncAzureOpenAI, AsyncOpenAI

from app.ai.interpretation.base import MovementInterpreter
from app.ai.interpretation.prompts import PROMPT_VERSION, SYSTEM_PROMPT
from app.ai.interpretation.schemas import InterpretationInput
from app.schemas.movement import InterpretationOutput
from app.core.config import get_settings


class AzureMovementInterpreter(MovementInterpreter):
    def __init__(self):
        settings = get_settings()
        key = settings.azure_openai_api_key
        if settings.azure_openai_uses_foundry_v1:
            self.client = AsyncOpenAI(base_url=settings.azure_openai_endpoint, api_key=key)
        else:
            self.client = AsyncAzureOpenAI(azure_endpoint=settings.azure_openai_endpoint, api_key=key, api_version=settings.azure_openai_api_version)
        self.deployment = settings.azure_openai_deployment

    async def interpret(self, context: InterpretationInput) -> InterpretationOutput:
        schema = InterpretationOutput.model_json_schema()
        response = await self.client.chat.completions.create(model=self.deployment, messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": json.dumps(context.model_dump(mode="json"))}], response_format={"type": "json_schema", "json_schema": {"name": "movement_interpretation", "strict": True, "schema": schema}})
        return InterpretationOutput.model_validate_json(response.choices[0].message.content or "{}")


class FakeMovementInterpreter(MovementInterpreter):
    async def interpret(self, context: InterpretationInput) -> InterpretationOutput:
        signal = str(context.risk.get("risk_signal", "INSUFFICIENT_DATA"))
        return InterpretationOutput(summary=f"{signal.title()} movement-control signal requiring clinician review.", observations=[], risk_interpretation="The movement risk signal is decision support only.", suggested_prevention_focus=[], clinician_questions=["Do the video findings match the clinical examination?"], limitations=["This interpretation uses two-dimensional pose estimates and is not a diagnosis."])


def get_interpreter() -> MovementInterpreter:
    settings = get_settings()
    if settings.llm_provider in {"fake", "disabled"} or not settings.azure_openai_api_key or not settings.azure_openai_endpoint:
        return FakeMovementInterpreter()
    return AzureMovementInterpreter()
