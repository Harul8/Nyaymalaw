"""Neutral checks for advocate-facing text, independent of any brain."""
import re


# Preserved from the retired internal-ID sweep. Current new_id() emits twelve
# hexadecimal characters; the eight-or-more range also covers historical keys.
INTERNAL_ID = re.compile(r"\b(?:mat|thr|fact|turn|adv)_[0-9a-f]{8,}\b")
