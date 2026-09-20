import re
import random
from typing import Any
from collections.abc import Sequence
from .const import WorkflowError
from ..util import average, normalize_mean


class Prompt:
    def __init__(self, prompt: str, weight: float) -> None:
        self.prompt = prompt
        self.weight = weight


    def danbooru_tag(self, danbooru_tags: dict[str, Any]) -> dict[str, Any] | None:
        tag = danbooru_tags.get(self.prompt, None)

        if tag is not None:
            while True:
                alias = tag.get("alias_for", None)

                if alias is not None:
                    tag = danbooru_tags[alias]
                else:
                    break

            return tag


    def anima(self) -> str:
        return self.prompt.replace("_", " ").replace("(", "\\(").replace(")", "\\)")


    def serialize(self) -> str:
        assert self.weight != 0.0

        if self.weight == 1.0:
            return self.prompt
        else:
            return f"({self.prompt}:{self.weight})"


class ParserState:
    def __init__(self, bundles: dict[str, Any]) -> None:
        self.bundles = bundles
        self.positive: list[Prompt] = []
        self.negative: list[Prompt] = []
        self.loras: list[dict[str, Any]] = []


    def parse_function(self, prompt: str, weight: float, seen_bundles: frozenset[str]) -> None:
        if weight != 0.0:
            function = re.fullmatch(r'<([a-z\-]+):([^>]*)>', prompt)

            if function is not None:
                name = function.group(1)
                value = function.group(2).strip()

                if name == "bundle":
                    bundle = self.bundles.get(value, None)

                    if bundle is None:
                        raise WorkflowError(f"Bundle {value} not found.")

                    if value in seen_bundles:
                        raise WorkflowError(f"Infinite recursion when inserting bundle {value}")

                    self.parse(bundle["prompt"], weight, seen_bundles.union({ value }))

                elif name == "lora":
                    self.loras.append({
                        "path": value,
                        "model_weight": weight,
                        "clip_weight": weight,
                    })

                else:
                    raise WorkflowError(f"Unknown function {prompt}")

            else:
                for prompt in re.split(r'[\s,]*[\n\r,]+[\s,]*', prompt):
                    if prompt != "":
                        if weight > 0.0:
                            self.positive.append(Prompt(prompt, weight))
                        elif weight < 0.0:
                            self.negative.append(Prompt(prompt, -weight))


    def parse_line(self, line: str, global_weight: float, seen_bundles: frozenset[str]) -> None:
        # Search for a weight for the line
        match = re.fullmatch(r'(.*)\* *([\-\d\.]+)', line)

        if match is not None:
            prompt = match.group(1).strip()
            weight = float(match.group(2))

        else:
            prompt = line
            weight = 1.0

        weight = weight * global_weight

        if prompt != "":
            # Splits | alternates and picks one of them
            prompt = random.choice(re.split(r' *\| *', prompt))

            if prompt != "":
                # If there are multiple functions in a line, split them into separate prompts
                for prompt in re.split(r'(<[a-z\-]+:[^>]*>)[, ]*', prompt):
                    if prompt != "":
                        self.parse_function(prompt, weight, seen_bundles)


    def parse(self, text: str, global_weight: float, seen_bundles: frozenset[str]) -> None:
        if re.search(r'BREAK', text) is not None:
            raise WorkflowError("BREAK is not supported:\n\n" + text)

        # Clean up the text so it doesn't have any tabs
        text = re.sub(r'\t+', r' ', text)

        # Remove /* ... */ comments
        text = re.sub(r'/\*[\s\S]*\*/', "", text)

        for line in text.splitlines():
            # TODO handle \\// and \\# properly

            # Remove // and # comments
            # They can be escaped by using \
            line = re.sub(r'(?<!\\)(?://|#).*', r'', line)

            # Remove the escaping \ before the comments
            line = re.sub(r'\\(?=//|#)', r'', line)

            line = line.strip()

            if line != "":
                self.parse_line(line, global_weight, seen_bundles)


class Parsed:
    def __init__(self, positive: list[Prompt], negative: list[Prompt], loras: list[dict[str, Any]]) -> None:
        self.positive = positive
        self.negative = negative
        self.loras = loras


    def convert_to_anima(self, prompts: Sequence[Prompt], danbooru_tags: dict[str, Any]) -> None:
        for prompt in prompts:
            tag = prompt.danbooru_tag(danbooru_tags)

            if tag is not None:
                # https://danbooru.donmai.us/wiki_pages/api%3Atags
                match tag["category"]:
                    # Artist
                    case 1:
                        prompt.prompt = "@" + prompt.anima()
                    case _:
                        prompt.prompt = prompt.anima()


    def normalize_weights(self, prompts: Sequence[Prompt], danbooru_tags: dict[str, Any]) -> None:
        danbooru_prompts: list[Prompt] = []

        post_counts: list[int] = []

        for prompt in prompts:
            tag = prompt.danbooru_tag(danbooru_tags)

            if tag is not None:
                danbooru_prompts.append(prompt)
                post_counts.append(tag["post_count"])

        if len(post_counts) > 0:
            normalized = normalize_mean(post_counts, average(post_counts), min(post_counts), max(post_counts), 1.0)

            for weight, prompt in zip(normalized, danbooru_prompts):
                prompt.weight = prompt.weight * weight


    def serialize(self, prompts: Sequence[Prompt]) -> str:
        return ",\n".join([prompt.serialize() for prompt in prompts])


class PromptParser:
    def __init__(self, bundles: dict[str, Any]) -> None:
        self.bundles = bundles


    def parse(self, text: str, global_weight: float = 1.0) -> Parsed:
        state = ParserState(self.bundles)
        state.parse(text, global_weight, frozenset())
        return Parsed(state.positive, state.negative, state.loras)
