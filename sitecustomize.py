import os

# Ensure pyannote-audio never tries to use torchcodec, which is unstable
# on this Windows setup and was causing segmentation faults.
os.environ.setdefault("PYANNOTE_AUDIO_DISABLE_TORCHCODEC", "1")

