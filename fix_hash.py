import hashlib
import os

filepath = 'docs/references/real-agent-review-loop-mvp-001-acceptance-003.md'
with open(filepath, 'rb') as f:
    content = f.read()

content = content.replace(b'\r\n', b'\n')

with open(filepath, 'wb') as f:
    f.write(content)

sha256 = hashlib.sha256(content).hexdigest()

ptr_path = 'docs/references/current-execution-packet.md'
with open(ptr_path, 'r', encoding='utf-8') as f:
    ptr_content = f.read()

import re
ptr_content = re.sub(r'ACTIVE_PACKET_SHA256: [a-f0-9]+', f'ACTIVE_PACKET_SHA256: {sha256}', ptr_content)
ptr_content = re.sub(r'real-agent-review-loop-mvp-001-acceptance-002.md', 'real-agent-review-loop-mvp-001-acceptance-003.md', ptr_content)

with open(ptr_path, 'w', encoding='utf-8', newline='\n') as f:
    f.write(ptr_content)
