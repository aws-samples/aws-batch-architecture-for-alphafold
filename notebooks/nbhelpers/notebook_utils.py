# Copyright 2021 DeepMind Technologies Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Helper methods for the AlphaFold Colab notebook."""
import enum
import json
from typing import Any, Mapping, Optional, Sequence, Tuple

MODEL_PRESETS = {
    "monomer": (
        "model_1",
        "model_2",
        "model_3",
        "model_4",
        "model_5",
    ),
    "monomer_ptm": (
        "model_1_ptm",
        "model_2_ptm",
        "model_3_ptm",
        "model_4_ptm",
        "model_5_ptm",
    ),
    "multimer": (
        "model_1_multimer",
        "model_2_multimer",
        "model_3_multimer",
        "model_4_multimer",
        "model_5_multimer",
    ),
}

MODEL_PRESETS["monomer_casp14"] = MODEL_PRESETS["monomer"]

# This is the standard residue order when coding AA type as a number.
# Reproduce it by taking 3-letter AA codes and sorting them alphabetically.
restypes = [
    "A",
    "R",
    "N",
    "D",
    "C",
    "Q",
    "E",
    "G",
    "H",
    "I",
    "L",
    "K",
    "M",
    "F",
    "P",
    "S",
    "T",
    "W",
    "Y",
    "V",
]


@enum.unique
class ModelType(enum.Enum):
    MONOMER = 0
    MULTIMER = 1


def clean_and_validate_sequence(
    input_sequence: str, min_length: int, max_length: int
) -> str:
    """Checks that the input sequence is ok and returns a clean version of it."""
    # Remove all whitespaces, tabs and end lines; upper-case.
    clean_sequence = input_sequence.translate(str.maketrans("", "", " \n\t")).upper()
    aatypes = set(restypes)  # 20 standard aatypes.
    if not set(clean_sequence).issubset(aatypes):
        raise ValueError(
            f"Input sequence contains non-amino acid letters: "
            f"{set(clean_sequence) - aatypes}. AlphaFold only supports 20 standard "
            "amino acids as inputs."
        )
    if len(clean_sequence) < min_length:
        raise ValueError(
            f"Input sequence is too short: {len(clean_sequence)} amino acids, "
            f"while the minimum is {min_length}"
        )
    if len(clean_sequence) > max_length:
        raise ValueError(
            f"Input sequence is too long: {len(clean_sequence)} amino acids, while "
            f"the maximum is {max_length}. You may be able to run it with the full "
            f"AlphaFold system depending on your resources (system memory, "
            f"GPU memory)."
        )
    return clean_sequence


def validate_input(
    input_sequences: Sequence[str],
    min_length: int,
    max_length: int,
    max_multimer_length: int,
) -> Tuple[Sequence[str], ModelType]:
    """Validates and cleans input sequences and determines which model to use."""
    sequences = []

    for input_sequence in input_sequences:
        if input_sequence.strip():
            input_sequence = clean_and_validate_sequence(
                input_sequence=input_sequence,
                min_length=min_length,
                max_length=max_length,
            )
            sequences.append(input_sequence)

    if len(sequences) == 1:
        print("Using the single-chain model.")
        return sequences, ModelType.MONOMER

    elif len(sequences) > 1:
        total_multimer_length = sum([len(seq) for seq in sequences])
        if total_multimer_length > max_multimer_length:
            raise ValueError(
                f"The total length of multimer sequences is too long: "
                f"{total_multimer_length}, while the maximum is "
                f"{max_multimer_length}. Please use the full AlphaFold "
                f"system for long multimers."
            )
        elif total_multimer_length > 1536:
            print(
                "WARNING: The accuracy of the system has not been fully validated "
                "above 1536 residues, and you may experience long running times or "
                f"run out of memory for your complex with {total_multimer_length} "
                "residues."
            )
        print(f"Using the multimer model with {len(sequences)} sequences.")
        return sequences, ModelType.MULTIMER

    else:
        raise ValueError(
            "No input amino acid sequence provided, please provide at "
            "least one sequence."
        )
