import sys

with open('app.py', 'r') as f:
    content = f.read()

# Remove any existing import os to clean up
content = content.replace('import os\n', '')

# Remove the old if block
import re
content = re.sub(r'if __name__ == "__main__":.*', '', content, flags=re.DOTALL)

# Append clean block
content += '\nimport os\nif __name__ == "__main__":\n    port = int(os.environ.get("PORT", 5000))\n    app.run(host="0.0.0.0", port=port)\n'

with open('app.py', 'w') as f:
    f.write(content)
