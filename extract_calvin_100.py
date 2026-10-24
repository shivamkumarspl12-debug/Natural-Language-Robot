import numpy as np

path = r".\datasets\calvin\calvin\dataset\calvin_debug\calvin_debug_dataset\training\lang_annotations\auto_lang_ann.npy"

data = np.load(path, allow_pickle=True).item()

print("=" * 70)
print("CALVIN TRAINING LANGUAGE DATA")
print("=" * 70)

language = data["language"]
info = data["info"]

print("\nLANGUAGE:")

for key, value in language.items():
    try:
        length = len(value)
    except TypeError:
        length = "N/A"

    print(
        f"{key} -> "
        f"type={type(value).__name__}, "
        f"length={length}"
    )

print("\nINFO:")

for key, value in info.items():
    try:
        length = len(value)
    except TypeError:
        length = "N/A"

    print(
        f"{key} -> "
        f"type={type(value).__name__}, "
        f"length={length}"
    )

print("\n" + "=" * 70)
print("CHECK COMPLETED")
print("=" * 70)