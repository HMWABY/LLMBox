import time
from http import HTTPStatus
from logging import getLogger

import dashscope

from ..utils import ModelArguments
from .model import Model

logger = getLogger(__name__)


class Dashscope(Model):
    r"""The model for calling Dashscope APIs. (Aliyun)

    Please refer to https://help.aliyun.com/zh/dashscope/.

    We now support `qwen-turbo`, `qwen-plus`, `qwen-max`, `qwen-max-1201`, `qwen-max-longcontext`, `qwen1.5-72b-chat`,
                   `qwen1.5-14b-chat`, `qwen1.5-7b-chat`, `qwen-72b-chat`, `qwen-14b-chat`, `qwen-7b-chat`,
                   `qwen-1.8b-longcontext-chat`, `qwen-1.8b-chat`.
    """

    model_backend = "dashscope"

    _repr = ["model_type", "model_backend", "multi_turn"]

    def __init__(self, args: ModelArguments):
        super().__init__(args)
        if not args.dashscope_api_key:
            raise ValueError(
                "Dashscope API key is required. Please set it by passing a `--dashscope_api_key` or through environment variable `DASHSCOPE_API_KEY`."
            )
        private_key = args.dashscope_api_key[:8] + "*" * 23 + args.dashscope_api_key[-4:]
        logger.info(f"Trying to load Dashscope model with api_key='{private_key}'")
        self.api_key = args.dashscope_api_key

        self.args = args
        self.name = args.model_name_or_path
        self.model_type = "instruction"
        self.tokenizer = dashscope.get_tokenizer(args.tokenizer_name_or_path)
        self.max_try_times = 10

    def set_generation_args(self, **extra_model_args):
        """Set the configurations for open-ended generation. This is useful because different datasets may have different requirements for generation."""
        generation_kwargs = {}
        for key in [
            "temperature",
            "top_p",
            "top_k",
            "max_tokens",
            "repetition_penalty",
            "enable_search",
            "stop",
        ]:
            # ModelArguments > extra_model_args
            value = getattr(self.args, key, None)
            if value is None:
                value = extra_model_args.pop(key, None)

            if key == "max_tokens" and value is None:
                value = 1024
            if value is not None:
                generation_kwargs[key] = value

        if generation_kwargs.get("temperature", 1) == 0:
            generation_kwargs["seed"] = self.args.seed
        self.generation_kwargs = generation_kwargs
        self.multi_turn = extra_model_args.pop("multi_turn", False)
        return self.generation_kwargs

    def generation(self, batched_inputs):
        results = self.request(batched_inputs, self.generation_kwargs, multi_turn=self.multi_turn)
        answers = []
        for result in results:
            answer = result.content
            answers.append(answer)
        return [tuple(answers)] if self.multi_turn else answers

    def request(self, prompt, kwargs, multi_turn=False):
        r"""Call the DashScope API.

        Args:
            prompt (List[str]): The list of input prompts.
            model_args (dict): The additional calling configurations.
            multi_turn (bool): Default is False. Set to True if multi-turns needed.

        Returns:
            List[dict]: The responsed JSON results.
        """
        for _ in range(self.max_try_times):
            error_msg = "EMPTY_ERROR_MSG"
            try:
                messages = []
                results = []
                parts = prompt[0].split("__SEPARATOR__") if multi_turn else prompt
                for query in parts:
                    if len(query) == 0:
                        continue
                    messages.append({"role": "user", "content": query})
                    msg = dashscope.Generation.call(
                        model=self.name, messages=messages, result_format="message", **kwargs
                    )
                    if (msg.status_code != HTTPStatus.OK):
                        error_msg = msg.message
                    assert (msg.status_code == HTTPStatus.OK)
                    results.append(msg.output.choices[0].message)
                    messages.append({"role": "assistant", "content": msg.output.choices[0].message.content})
                return results
            except Exception as e:
                logger.warning("Receive error: {}".format(error_msg))
                logger.warning("retrying...")
                time.sleep(1)
        raise ConnectionError("Dashscope API error")
