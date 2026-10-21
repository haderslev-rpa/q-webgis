import subprocess

cmd = r"""
mkdir -p tests_local

find . \
    -type f \
    \( -name "*.py" -o -name "pyproject.toml" \) \
    ! -path "./tests_local/*" \
    ! -path "./.venv/*" \
| sort \
| while IFS= read -r file; do
    echo ""
    echo "===== $file ====="
    cat "$file"
done > tests_local/copilot.txt
"""

subprocess.run(cmd, shell=True, executable="/bin/bash", check=True)

print("Færdig: tests_local/copilot.txt")
