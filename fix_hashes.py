import hashlib
import re

def hash_file(path):
    with open(path, 'rb') as f:
        content = f.read().replace(b'\r\n', b'\n')
    with open(path, 'wb') as f:
        f.write(content)
    return hashlib.sha256(content).hexdigest()

manual_hash = hash_file('docs/references/real-agent-review-loop-mvp-001-acceptance-manual.md')

ptr_path = 'docs/references/current-execution-packet.md'
with open(ptr_path, 'r', encoding='utf-8') as f:
    ptr = f.read()

ptr = re.sub(r'ACTIVE_PACKET_SHA256: [a-f0-9]+', f'ACTIVE_PACKET_SHA256: {manual_hash}', ptr)
ptr = re.sub(r'real-agent-review-loop-mvp-001-acceptance-00[0-9].md', 'real-agent-review-loop-mvp-001-acceptance-manual.md', ptr)

with open(ptr_path, 'w', encoding='utf-8', newline='\n') as f:
    f.write(ptr)
