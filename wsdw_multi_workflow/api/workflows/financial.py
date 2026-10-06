# coding: utf-8
"""金融类业务工作流：start -> questioner -> end。"""

from openjiuwen.core.foundation.llm import (
    BaseModelInfo,
    ModelClientConfig,
    ModelConfig,
    ModelRequestConfig,
)
from openjiuwen.core.workflow import (
    End,
    FieldInfo,
    QuestionerComponent,
    QuestionerConfig,
    Start,
    Workflow,
    WorkflowCard,
)

from .. import config


def _create_model_config() -> ModelConfig:
    """创建提问器使用的模型配置。"""
    return ModelConfig(
        model_provider=config.MODEL_PROVIDER,
        model_info=BaseModelInfo(
            model=config.MODEL_NAME,
            api_base=config.API_BASE,
            api_key=config.API_KEY,
            temperature=0.7,
            top_p=0.9,
            timeout=200,
        ),
    )


def build_financial_workflow(
    workflow_id: str,
    workflow_name: str,
    workflow_desc: str,
    field_name: str,
    field_desc: str,
) -> Workflow:
    """构建带中断提问节点的金融业务工作流。"""
    card = WorkflowCard(
        name=workflow_name,
        id=workflow_id,
        version="1.0",
        description=workflow_desc,
    )
    flow = Workflow(card=card)

    start = Start()

    key_fields = [
        FieldInfo(
            field_name=field_name,
            description=field_desc,
            required=True,
        ),
    ]
    model_config = _create_model_config()
    provider = model_config.model_provider
    if provider and provider.lower() == "openai":
        provider = "OpenAI"
    elif provider and provider.lower() == "siliconflow":
        provider = "SiliconFlow"

    questioner_config = QuestionerConfig(
        model_client_config=ModelClientConfig(
            client_provider=provider,
            api_key=model_config.model_info.api_key,
            api_base=model_config.model_info.api_base,
            timeout=model_config.model_info.timeout,
            verify_ssl=False,
        ),
        model_config=ModelRequestConfig(
            model=model_config.model_info.model_name,
            temperature=model_config.model_info.temperature,
            top_p=model_config.model_info.top_p,
        ),
        question_content="",
        extract_fields_from_response=True,
        field_names=key_fields,
        with_chat_history=False,
    )
    questioner = QuestionerComponent(questioner_config)
    end = End({"responseTemplate": f"{workflow_name}完成: {{{{{field_name}}}}}"})

    flow.set_start_comp("start", start, inputs_schema={"query": "${query}"})
    flow.add_workflow_comp(
        "questioner", questioner, inputs_schema={"query": "${start.query}"}
    )
    flow.set_end_comp(
        "end", end, inputs_schema={field_name: f"${{questioner.{field_name}}}"}
    )
    flow.add_connection("start", "questioner")
    flow.add_connection("questioner", "end")

    return flow
