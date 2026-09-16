# Design-system integration · 2026-09-16

Source: user-supplied `ZHIDAO Protocol Design System.zip`.
`reference/` preserves its CSS, component examples, guidelines and assets as
reference material. Demo JSX, its content and sample values are not executed.
No React dependency was added. Existing server contracts remain unchanged.

Build: `python tools/build_design_system.py`, then `python tools/stamp_assets.py`.
Generated CSS loads after legacy styles; `design-system-bridge.css` adapts it
to the existing DOM. Structural aliases keep existing IDs and event handlers.
Do not edit the generated CSS directly or deploy the reference demo as the app.

## Verified in this pass

- 8 tests passed: generated CSS consistency, local font resources, structural
  aliases, motion settings, stylesheet ordering, asset hashes and references.
- Browser preview: home, profile/settings, event catalogue and cases; daytime
  Luna-Aqua and daytime/nighttime Aqua were visually inspected.
- Cases: actual CSS viewport widths 360 / 390 / 430; document widths
  348 / 378 / 418 respectively (scrollbar excluded), no horizontal overflow.
- Found and fixed profile-button gloss escaping its containing block in Aqua.
  Verified pseudo-element height 22.03px inside a 43.99px button afterward.
- Preview case operation remains disabled; no personal data was substituted.

## Not yet a release acceptance

This is the initial shared visual layer, not a claim of complete one-to-one
conversion of every reference screen. Existing screen composition is retained.
All multiplayer phases, admin screens, MAX on real devices, keyboard/contrast
audit and the full four-theme responsive matrix still need validation.
No production deployment or repository push performed in this pass.
