# WINDOWS-OPENCLI-LONG-ARGV-001

**Status:** Non-active Blocker / Technical Debt
**Date:** 2026-08-11

## Description
When running opencli.cmd via subprocess on Windows, sending a large payload (e.g., ~12236 characters) results in the OS-level error:
The command line is too long.

This blocked REAL-AGENT-REVIEW-LOOP-MVP-001-ACCEPTANCE-003 from completing the automated Transport validation.

## Resolution Plan
1. Do NOT immediately modify stdin or file transport, or redesign ACF.
2. The first candidate solution must be DIRECT_NODE_ARGV.
3. Minimal discriminating test:
   opencli.cmd + same long argv vs 
ode <OpenCLI dist/src/main.js> + same long argv
4. If YES (Node bypasses the CMD length limit), modify Windows ind_opencli() invocation resolution.
5. If NO, then consider thin reference envelope, stdin, file-backed prompt, etc.
