from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

from .base import Model
from ..formatters import Formatter
from ..messages import Message, AssistantMessage, ModelResponse, Role, TokenUsage


class HuggingFaceModel(Model):
    def __init__(self, model_name: str, formatter: Formatter, **init_kwargs):
        """
        Wrapper around HuggingFace causal language models.
        """
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_name,
            **init_kwargs,
        )
        self.formatter = formatter

        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

    def __call__(
        self,
        messages: list[Message],
        *,
        max_new_tokens: int = 512,
        do_sample: bool = True,
        temperature: float = 0.7,
        top_p: float = 0.95,
        **generate_kwargs,
    ) -> ModelResponse:
        prompt = self.formatter(messages)

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

        return ModelResponse(
            message=AssistantMessage(
                role=Role.ASSISTANT,
                content=text
            ),
            model=self.model.config.name_or_path,
            usage=TokenUsage(inputs["input_ids"].shape[1], len(generated_tokens), outputs.shape[-1]),
            finish_reason="stop",
            raw_response=outputs
        )