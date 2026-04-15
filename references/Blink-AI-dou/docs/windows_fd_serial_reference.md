# Windows FD Serial Reference

This document exists only as a hardware sanity-check fallback.

## When To Use It

Use Windows FD only when:

- the Mac serial path is failing
- you need to answer "is the hardware alive at all?"
- you want a second host to separate adapter or macOS issues from obvious bus or servo failure

## When Not To Use It

Do not treat Windows FD as:

- the maintained development workflow
- the maintained acceptance workflow
- the source of truth for artifacts
- the source of truth for calibration, tuning, or runtime status

The primary path remains:

1. Mac CLI
2. Mac Servo Lab (`servo-lab-*` and `/console`)
3. `desktop_serial_body`
4. `/console`
5. session export and Stage E bench artifacts

## Minimum Use

If the Mac path is degraded, Windows FD may answer only these questions:

- does the adapter enumerate?
- does one known-good baud respond?
- do the expected IDs reply at all?

Once that is answered, return to the Mac workflow and continue diagnosis there. All maintained runbooks, motion gates, and evidence packaging live on the Mac path.
