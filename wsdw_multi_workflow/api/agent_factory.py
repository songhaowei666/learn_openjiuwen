# coding: utf-8
"""装配 ControllerAgent、模型与业务工作流。"""

from openjiuwen.core.controller.base import Controller, ControllerConfig
from openjiuwen.core.controller.modules import TaskExecutorDependencies
from openjiuwen.core.foundation.llm import Model, ModelClientConfig, ModelRequestConfig
from openjiuwen.core.runner import Runner
from openjiuwen.core.single_agent import AgentCard
from openjiuwen.core.single_agent.base import ControllerAgent

from . import config
from .executors import GeneralTaskExecutor, WorkflowTaskExecutor
from .handlers import EventHandlerWithIntentRecognition
from .workflows import build_financial_workflow


def build_workflow_task_executor(dependencies: TaskExecutorDependencies) -> WorkflowTaskExecutor:
    """构建工作流任务执行器。"""
    return WorkflowTaskExecutor(dependencies)


def build_general_task_executor(dependencies: TaskExecutorDependencies) -> GeneralTaskExecutor:
    """构建通用任务执行器。"""
    return GeneralTaskExecutor(dependencies)


def create_financial_agent() -> ControllerAgent:
    """创建并注册模型、工作流后返回金融 ControllerAgent。"""
    model = Model(
        model_client_config=ModelClientConfig(
            client_provider=config.MODEL_PROVIDER,
            api_base=config.API_BASE,
            api_key=config.API_KEY,
            verify_ssl=False,
            timeout=120,
        ),
        model_config=ModelRequestConfig(model=config.MODEL_NAME),
    )
    Runner.resource_mgr.add_model(
        model_id=config.MODEL_ID,
        model=lambda: model,
    )

    agent_card = AgentCard(
        id="financial_agent",
        name="Financial Agent",
        description="金融智能体",
    )
    controller = Controller()
    controller_config = ControllerConfig(
        enable_task_persistence=True,
        intent_llm_id=config.MODEL_ID,
        intent_confidence_threshold=0.3,
        event_timeout=120000.0,
        task_timeout=120000.0,
    )
    agent = ControllerAgent(
        card=agent_card,
        controller=controller,
        config=controller_config,
    )

    controller.set_event_handler(EventHandlerWithIntentRecognition())
    (
        controller.add_task_executor("workflow", build_workflow_task_executor).add_task_executor(
            "general", build_general_task_executor
        )
    )

    transfer_workflow = build_financial_workflow(
        workflow_id="transfer_flow_multi",
        workflow_name="转账服务",
        workflow_desc="处理用户转账请求，支持转账到指定账户",
        field_name="amount",
        field_desc="转账金额（数字）",
    )
    invest_workflow = build_financial_workflow(
        workflow_id="invest_flow_multi",
        workflow_name="理财服务",
        workflow_desc="提供理财产品推荐和购买服务",
        field_name="product",
        field_desc="理财产品名称",
    )
    balance_workflow = build_financial_workflow(
        workflow_id="balance_flow",
        workflow_name="余额查询",
        workflow_desc="查询用户账户余额信息",
        field_name="account",
        field_desc="账户号码",
    )

    Runner.resource_mgr.add_workflow(transfer_workflow.card, lambda: transfer_workflow)
    Runner.resource_mgr.add_workflow(invest_workflow.card, lambda: invest_workflow)
    Runner.resource_mgr.add_workflow(balance_workflow.card, lambda: balance_workflow)

    agent.ability_manager.add(invest_workflow.card)
    agent.ability_manager.add(transfer_workflow.card)
    agent.ability_manager.add(balance_workflow.card)

    return agent
