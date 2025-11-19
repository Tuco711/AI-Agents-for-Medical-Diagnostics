from pathlib import Path
from openai import OpenAI
import sys
import io
import os
from dotenv import load_dotenv
from pathlib import Path

env_path = Path(__file__).resolve().parents[1] / '.env'
load_dotenv(env_path)

# Ensure stdout is configured to UTF-8 to avoid Windows cp1252 encoding errors
try:
    # Python 3.7+ has reconfigure
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    # Fallback: wrap the buffer with a UTF-8 text wrapper
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    except Exception:
        # Last resort: leave stdout as-is; prints may still fail on some characters
        pass

client = OpenAI(
  base_url="https://openrouter.ai/api/v1",
  api_key= os.getenv("OPENROUTER_API_KEY"),
)

completion = client.chat.completions.create(
  extra_body={},
  model="openai/gpt-oss-20b:free",
  messages=[
    {
      "role": "user",
      "content": "List the top 5 Cardiologists in coimbra, portugal and their contact details."
    }
  ]
)

# Print safely: replace characters that can't be encoded as a fallback
content = completion.choices[0].message.content
try:
    print(content)
except UnicodeEncodeError:
    # Fallback: replace unencodable characters with a visible placeholder
    print(content.encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8', errors='replace'))