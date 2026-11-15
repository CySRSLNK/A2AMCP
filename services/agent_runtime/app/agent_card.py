from pydantic import BaseModel, Field


class AgentCard(BaseModel):
    agent_id: str = Field(alias="id")
    name: str
    description: str
    url: str
    capabilities: dict = {
        "operations": ["message/send", "tasks/get", "tasks/cancel", "message/stream"]
    }

    model_config = {"populate_by_name": True}

    def model_dump(self, *args, **kwargs):
        kwargs.setdefault("by_alias", True)
        return super().model_dump(*args, **kwargs)
