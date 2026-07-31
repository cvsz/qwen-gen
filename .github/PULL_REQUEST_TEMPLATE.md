## Summary

<!-- One-line summary of what this PR does. -->

## Type of change

- [ ] Bug fix
- [ ] New feature / enhancement
- [ ] New provider preset
- [ ] Documentation
- [ ] CI / workflow change
- [ ] Refactor / cleanup

## Related issues

Closes #<!-- issue number -->

## Changes

<!--
List the key changes made in this PR.
- Added X to qwen-omega.py
- Updated install-qwen-coder.sh to handle Y
-->

## Testing

<!--
Describe how you tested this change.
Include any relevant dry-run output or test commands.
-->

```bash
# Example test command
python qwen-omega.py install-coder --backend ollama --dry-run
```

<details>
<summary>Test output</summary>

```
# Paste output here
```

</details>

## Checklist

- [ ] `python -m pytest test_qwen_omega.py -v` passes locally.
- [ ] `python qwen-omega.py --version` reflects the new version (if bumped).
- [ ] `bash -n install-qwen-coder.sh` / `bash -n install.sh` passes (no syntax errors).
- [ ] README / CHANGELOG updated if user-visible behavior changed.
- [ ] No API keys or credentials are committed.
