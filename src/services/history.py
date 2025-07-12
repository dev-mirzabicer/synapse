from _types.history import SynapseHistory
from _types.message import SynapseMessage, ToolResultMessage, MessageType, Visibility
from langchain_core.messages import HumanMessage, ToolMessage
from prompting.message_format import other_agent, system_message, user_message
from typing import List


class HistoryService:
    def __init__(self, history: SynapseHistory):
        self._history = history

    def personalize(
        self,
        actor_id: str,
    ) -> List[SynapseMessage]:
        personalized_messages = []
        for message in self._history.messages:
            if isinstance(message, SynapseMessage):
                if message.type == MessageType.AGENT:
                    if message.sender == actor_id:
                        personalized_messages.append(message.lc_message)
                    elif message.visibility == Visibility.PUBLIC:
                        personalized_messages.append(
                            HumanMessage(
                                other_agent(message.content, message.sender.name)
                            )
                        )
                elif message.type == MessageType.USER:
                    personalized_messages.append(
                        HumanMessage(user_message(message.content))
                    )
                elif message.type == MessageType.SYSTEM:
                    personalized_messages.append(
                        HumanMessage(system_message(message.content))
                    )
            elif (
                isinstance(message, ToolResultMessage) and message.caller.id == actor_id
            ):
                personalized_messages.append(
                    ToolMessage(
                        content=message.content,
                        tool_call_id=message.call_id,
                    )
                )
            else:
                raise ValueError(f"Unsupported message type: {type(message)}")
        return personalized_messages

    def add_message(
        self,
        message: SynapseMessage,
    ) -> None:
        self._history.messages.append(message)
        self._history.last_updated = message.timestamp

    @property
    def history(self) -> SynapseHistory:
        return self._history
