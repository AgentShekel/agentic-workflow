# Brand design system

Tokens live in `tokens.json`. Use the tokens; do not introduce raw values.

## Large-text-only pairs

`brand-accent-inverse` on `brand-accent` measures 3.45:1. It is approved for display text at
24px/700 and above only, where WCAG 2.1 AA requires 3:1. Body copy always uses `text-body`
(4.95:1 on `surface`) or `text-strong`.

## Focus ring on imagery

The default focus ring is a soft box-shadow (`focus.ring-default`). On photographic
backgrounds it disappears, so controls placed directly on imagery use
`focus.ring-on-imagery`: a 2px solid white outline with a 2px offset.

Every hero image ships with a fixed 45% black scrim, so no pixel under it can be lighter than
#8c8c8c (pure white under the scrim). Against that worst case the white outline is 3.35:1,
above the 3:1 required for non-text contrast (WCAG 1.4.11). Approved by the brand team; any control on imagery uses this variant.
