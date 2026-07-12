# Rogue Source Selection

Do not copy a Rogue implementation into this repository until its license and redistribution conditions are verified.

## Candidate Summary

| Candidate | Version | Source | License | Modification | Headless Difficulty | Seed Reproducibility | Testability | Recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Original Rogue restoration ports | 3.x / 5.x variants | Public mirrors and restoration projects | Must verify per source tree | Likely C code, closer to desired game | Medium to high if curses-coupled | Unknown until inspected | Medium | Promising only after license and build review |
| NetHack | 3.6.x / current line | Official NetHack project | NetHack General Public License | Large codebase | Medium; strong existing ecosystem | Good candidate with effort | High | Useful reference, but may be broader than Rogue target |
| NetHack Learning Environment | NLE | `facebookresearch/nle` / successor home referenced by that repository | Open-source project; verify exact repository license before use | Python-friendly RL environment | Low for experiments | Designed for evaluation | High | Strong research baseline, but not original Rogue |
| From-scratch minimal Rogue-like | Project-owned | This repository | Repository license | Highest control | Low once designed | High | High | Good fallback if source licensing blocks reuse |

## Selection Criteria

- license clarity,
- redistribution permission,
- build simplicity on Ubuntu,
- deterministic seed control,
- clean separation from curses,
- ease of adding headless `reset` and `step`,
- action and observation extraction cost,
- long-term maintainability.

## Current Recommendation

Use a two-track investigation:

1. Evaluate original Rogue restoration candidates for authenticity and scope.
2. Keep a from-scratch minimal Rogue-like engine as the fallback if license or coupling risk is too high.

NetHack and NLE are valuable references for environment design and evaluation methodology, but they may be larger than necessary for the stated Rogue target.

## License Notes

- NetHack publishes the NetHack General Public License on `nethack.org`; it permits copying and modification under its stated conditions, including source availability and license preservation.
- The `facebookresearch/nle` repository is archived and points readers to a newer home. It describes NLE as a reinforcement-learning environment based on NetHack 3.6.6. Verify the active repository license before copying code.
- Public Rogue mirrors may not all carry clear license metadata. Treat absence of a license file as a blocker for importing source.

## Reference URLs

- https://www.nethack.org/common/license.html
- https://github.com/facebookresearch/nle

## Required Next Steps

- Identify 2-3 concrete Rogue source repositories or tarballs.
- Inspect each candidate license file and source headers.
- Build each candidate on the mini PC.
- Check whether seed control is available.
- Prototype a non-invasive observation path.
- Select one implementation or choose the from-scratch fallback.
