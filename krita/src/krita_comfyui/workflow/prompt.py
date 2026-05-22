import re
import json
from .const import WorkflowError


class Prompt:
    def __init__(self, prompt, weight):
        self.prompt = prompt
        self.weight = weight


    def cleanup_prompt(self):
        prompt = self.prompt

        # Replace tabs with a space
        prompt = re.sub(r'\t+', r' ', prompt)

        # Replace _ with a space
        #prompt = re.sub(r'_', r' ', prompt)

        # Replace newlines with a comma
        prompt = re.sub(r'[\n\r]+', r', ', prompt)

        # Removes commas and spaces at the start and end
        prompt = re.sub(r'(?:^[, ]+)|(?:[, ]+$)', r'', prompt)

        # Removes repeated commas
        prompt = re.sub(r',[, ]+', r', ', prompt)

        # Removes spaces before a comma
        prompt = re.sub(r' +(?=,)', r'', prompt)

        # Adds a space after commas
        prompt = re.sub(r',(?! )', r', ', prompt)

        # Removes repeated spaces
        prompt = re.sub(r' {2,}', r' ', prompt)

        # Replaces ( with \\(
        #prompt = re.sub(r'(?<!\\)\(', r'\\(', prompt)

        # Replaces ) with \\)
        #prompt = re.sub(r'(?<!\\)\)', r'\\)', prompt)

        return prompt


    def serialize(self):
        assert self.weight != 0.0

        prompt = self.cleanup_prompt()

        if self.weight == 1.0:
            return prompt
        else:
            return f"({prompt}:{self.weight})"


class ParserState:
    def __init__(self, bundles):
        self.bundles = bundles
        self.positive = []
        self.negative = []
        self.loras = []


    def parse_function(self, prompt, weight, seen_bundles):
        if weight != 0.0:
            function = re.fullmatch(r'<([a-z\-]+):([^>]*)>', prompt)

            if function is not None:
                name = function.group(1)
                value = function.group(2).strip()

                if name == "bundle":
                    bundle = self.bundles.get(value, default=None)

                    if bundle is None:
                        raise WorkflowError(f"Bundle {value} not found.")

                    if value in seen_bundles:
                        raise WorkflowError(f"Infinite recursion when inserting bundle {value}")

                    self.parse(bundle, weight, seen_bundles.union({ value }))

                elif name == "lora":
                    self.loras.append({
                        "path": value,
                        "model_weight": weight,
                        "clip_weight": weight,
                    })

                else:
                    raise WorkflowError(f"Unknown function {prompt}")

            else:
                if weight > 0.0:
                    self.positive.append(Prompt(prompt, weight))
                elif weight < 0.0:
                    self.negative.append(Prompt(prompt, -weight))


    def parse_line(self, line, global_weight, seen_bundles):
        # Search for a weight for the line
        match = re.fullmatch(r'(.*)\* *([\-\d\.]+)', line)

        if match is not None:
            prompt = match.group(1).strip()
            weight = float(match.group(2))

        else:
            prompt = line
            weight = 1.0

        weight = weight * global_weight

        # If there are multiple functions in a line, split them into separate prompts
        for prompt in re.split(r'(<[a-z\-]+:[^>]*>)[, ]*', prompt):
            if prompt != "":
                self.parse_function(prompt, weight, seen_bundles)


    def parse(self, text, global_weight, seen_bundles):
        if re.search(r'BREAK', text) is not None:
            raise WorkflowError("BREAK is not supported:\n\n" + text)

        # Clean up the text so it doesn't have any tabs
        text = re.sub(r'\t+', r' ', text)

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
    def __init__(self, positive, negative, loras):
        self.positive = positive
        self.negative = negative
        self.loras = loras


    def serialize_positive(self):
        return ", ".join(prompt.serialize() for prompt in self.positive)

    def serialize_negative(self):
        return ", ".join(prompt.serialize() for prompt in self.negative)


class PromptParser:
    def __init__(self, bundles):
        self.bundles = bundles


    def parse(self, text, global_weight=1.0):
        state = ParserState(self.bundles)
        state.parse(text, global_weight, frozenset())
        return Parsed(state.positive, state.negative, state.loras)
