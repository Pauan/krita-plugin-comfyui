# Adapted from these files:
#   https://github.com/laksjdjf/cgem156-ComfyUI/blob/1f5533f7f31345bafe4b833cbee15a3c4ad74167/scripts/attention_couple/node.py
#   https://github.com/Acly/comfyui-tooling-nodes/blob/dfe014ae88491658c4af206c11f79aa703b89103/region.py

from __future__ import annotations
import torch
import torch.nn.functional as F
import math
from torch import Tensor, Size


def downsample_mask(mask: Tensor, batch: int, target_size: int, original_shape: Size) -> Tensor:
    h, w = original_shape[2], original_shape[3]
    hm, wm = mask.shape[2], mask.shape[3]
    if (h, w) == (hm, wm):  # Mask is already in latent resolution
        base_factor = 1
    elif (h * 8, w * 8) == (hm, wm):  # Mask is in image resolution, downsample by 8
        base_factor = 8
    else:
        raise ValueError(f"Bad mask size. Expected {w}x{h}, got {wm}x{hm}.")

    result = mask
    for factor in [1, 2, 4, 8]:
        size = (math.ceil(h / factor), math.ceil(w / factor))
        if size[0] * size[1] == target_size and base_factor * factor > 1:
            result = F.interpolate(mask, size=size, mode="nearest")
            break

    num_conds = mask.shape[0]
    result = result.view(num_conds, target_size, 1)
    result = result.repeat_interleave(batch, dim=0)
    return result


def lcm(a: int, b: int):
    return a * b // math.gcd(a, b)


def lcm_for_list(numbers: list[int]):
    current_lcm = numbers[0]
    for number in numbers[1:]:
        current_lcm = lcm(current_lcm, number)
    return current_lcm


class AttentionMaskPatch:
    def __init__(self, conditionings, masks):
        mask = torch.stack(masks, dim=0)
        mask_sum = mask.sum(dim=0, keepdim=True)
        #print((mask.sum(dim=0).min() > 0).item())
        #assert (mask.sum(dim=0).min() > 0).item(), "There are areas that are zero in all masks."
        #assert mask_sum.sum().item() > 0, "There are areas that are zero in all masks."

        self.mask = mask / mask_sum
        self.conds = [conditioning[0][0] for conditioning in conditionings]
        self.num_tokens = [cond.shape[1] for cond in self.conds]
        self.num_conds = len(conditionings)
        self.batch_size = 0


    def apply(self, model):
        new_model = model.clone()
        new_model.set_model_attn2_patch(self.attn2_patch)
        new_model.set_model_attn2_output_patch(self.attn2_output_patch)
        return new_model


    def attn2_patch(self, q, k, v, extra_options):
        assert k.mean() == v.mean(), "k and v must be the same."
        device, dtype = q.device, q.dtype

        if self.conds[0].device != device or self.conds[0].dtype != dtype:
            self.conds = [cond.to(device, dtype=dtype) for cond in self.conds]
        if self.mask.device != device or self.mask.dtype != dtype:
            self.mask = self.mask.to(device, dtype=dtype)

        cond_or_unconds = extra_options["cond_or_uncond"]
        num_chunks = len(cond_or_unconds)
        self.batch_size = q.shape[0] // num_chunks
        q_chunks = q.chunk(num_chunks, dim=0)
        k_chunks = k.chunk(num_chunks, dim=0)
        lcm_tokens = lcm_for_list(self.num_tokens + [k.shape[1]])
        conds_tensor = [
            cond.repeat(self.batch_size, lcm_tokens // self.num_tokens[i], 1)
            for i, cond in enumerate(self.conds)
        ]
        conds_tensor = torch.cat(conds_tensor, dim=0)

        qs, ks = [], []
        for i, cond_or_uncond in reversed(list(enumerate(cond_or_unconds))):
            if cond_or_uncond == 1:  # uncond
                k_target = k_chunks[i].repeat(1, lcm_tokens // k.shape[1], 1)
                qs.insert(0, q_chunks[i])
                ks.insert(0, k_target)
            else:
                qs.insert(0, q_chunks[i].repeat(self.num_conds, 1, 1))
                ks.insert(0, conds_tensor)
                for _ in range(self.num_conds - 1):
                    cond_or_unconds.insert(i, 0)

        qs = torch.cat(qs, dim=0)
        ks = torch.cat(ks, dim=0)
        return qs, ks, ks


    def attn2_output_patch(self, out, extra_options):
        num_conds = self.num_conds
        cond_or_unconds = extra_options["cond_or_uncond"]
        mask_downsample = downsample_mask(
            self.mask, self.batch_size, out.shape[1], extra_options["original_shape"]
        )
        outputs: list[Tensor] = []
        pos = 0
        i = 0
        while i < len(cond_or_unconds):
            if cond_or_unconds[i] == 1:  # uncond
                outputs.append(out[pos : pos + self.batch_size])
                pos += self.batch_size
            else:
                masked = out[pos : pos + num_conds * self.batch_size] * mask_downsample
                masked = masked.view(num_conds, self.batch_size, out.shape[1], out.shape[2])
                masked = masked.sum(dim=0)
                outputs.append(masked)
                pos += num_conds * self.batch_size
                for _ in range(num_conds - 1):
                    cond_or_unconds.pop(i)
            i += 1

        return torch.cat(outputs, dim=0)
