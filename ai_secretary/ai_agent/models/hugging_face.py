from __future__ import annotations

import json
from typing import Optional, Any

from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

from .base import Model
from ..chat_formatters import ChatFormatter
from ..tool_formatters import ToolFormatter
from ..tool_parsers import ToolParser, ToolParsingError
from ..messages import Message, AssistantMessage, ModelResponse, Role, TokenUsage
from ..tools import ToolSet


class HuggingFaceModel(Model):
    def __init__(
            self, 
            model_name: str,
            tool_parser: ToolParser,
            chat_formatter: Optional[ChatFormatter],
            tool_formatter: Optional[ToolFormatter],
            **init_kwargs
        ):
        """
        Wrapper around HuggingFace causal language models.
        """
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_name,
            **init_kwargs,
        )
        self.chat_formatter = chat_formatter
        self.tool_formatter = tool_formatter
        self.tool_parser = tool_parser

        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

    def _to_hf_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        """
        Преобразует список объектов Message в формат, ожидаемый методом 
        `tokenizer.apply_chat_template` от HuggingFace.
        """
        hf_messages = []
        for msg in messages:
            role = msg.role.value
            
            hf_msg = {
                "role": role,
                "content": msg.content,
            }
                
            hf_messages.append(hf_msg)
            
        return hf_messages

    def _get_tools_description(self, tools: ToolSet) -> str:
        """
        Возвращает строковое описание инструментов.
        Если передан tool_formatter — использует его, иначе сериализует
        встроенную схему ToolSet в JSON.
        """
        if self.tool_formatter is not None:
            return self.tool_formatter(tools)
        return json.dumps(tools.to_llm_definition(), ensure_ascii=False, indent=2)

    def _inject_tools_into_first_message(
        self, 
        messages: list[Message], 
        tools_description: str,
    ) -> list[Message]:
        """
        Создаёт копию списка сообщений, в которой в конец content первого
        сообщения (системного промпта) дописывается описание инструментов.
        Исходный список не мутируется.
        """
        if not messages:
            return messages
        
        messages = list(messages)
        first_msg = messages[0]
        
        separator = "\n\n" if first_msg.content else ""
        new_content = (first_msg.content or "") + separator + tools_description
        
        new_first_msg = Message(
            role=first_msg.role,
            content=new_content,
        )
        
        messages[0] = new_first_msg
        return messages

    def __call__(
        self,
        messages: list[Message],
        tools: Optional[ToolSet] = None,
        *,
        max_new_tokens: int = 512,
        do_sample: bool = True,
        temperature: float = 0.7,
        top_p: float = 0.95,
        **generate_kwargs,
    ) -> ModelResponse:
        use_apply_template = self.chat_formatter is None
        
        if use_apply_template:
            hf_messages = self._to_hf_messages(messages)
            
            hf_tools = tools.to_llm_definition() if tools is not None else None
            
            prompt = self.tokenizer.apply_chat_template(
                hf_messages,
                tools=hf_tools,
                tokenize=False,
                add_generation_prompt=True,
            )
        else:
            if tools is not None:
                tools_description = self._get_tools_description(tools)
                messages = self._inject_tools_into_first_message(
                    messages, tools_description
                )
            
            prompt = self.chat_formatter(messages)

        inputs = self.tokenizer(
            prompt,
            return_tensors="pt",
        )

        inputs = {
            key: value.to(self.model.device)
            for key, value in inputs.items()
        }

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=do_sample,
                temperature=temperature,
                top_p=top_p,
                pad_token_id=self.tokenizer.pad_token_id,
                **generate_kwargs,
            )

        generated_tokens = outputs[0][inputs["input_ids"].shape[1]:]

        text = self.tokenizer.decode(
            generated_tokens,
            skip_special_tokens=True,
        )

        try:
            tool_calls = self.tool_parser(text)
            tool_call_error = None
        except ToolParsingError as e:
            tool_call_error = e.message
            tool_calls = []

        return ModelResponse(
            message=AssistantMessage(
                role=Role.ASSISTANT,
                content=text,
                tool_calls=tool_calls,
                tool_call_error=tool_call_error
            ),
            model=self.model.config.name_or_path,
            usage=TokenUsage(
                inputs["input_ids"].shape[1], 
                len(generated_tokens), 
                outputs.shape[-1]
            ),
            finish_reason="stop",
            raw_response=outputs
        )