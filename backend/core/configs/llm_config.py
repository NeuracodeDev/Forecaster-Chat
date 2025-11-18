import os
from dotenv import load_dotenv
load_dotenv()

MODEL_NAME="gpt-5.1-2025-11-13"
OPENAI_API_KEY=os.getenv("OPENAI_API_KEY")
REASONING_EFFORT="high"
VERBOSITY="high"

