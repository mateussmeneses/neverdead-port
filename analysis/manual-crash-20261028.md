# Manual launcher test: release blocker

User reports a crash after the first phase while loading a cutscene, and worse
stability than earlier runs. This transition has not been reproduced by the agent.

Session `session-20261028-075146.log` ends at 07:54:23.244 with:

```text
[FATAL] Call to invalid or unregistered function at guest address 0x825D5770 (LR=0x821F083C, SP=0x7018F2E0)
```

Six pause-thunk markers at `0x8253B640` immediately precede this fatal entry.
The log contains 1,264 invalid texture-fetch warnings. Neither these warnings
nor the fresh launcher cache are established causes of the performance report.
No comparable frame-time capture was collected from this manual session.

SHA-256 comparisons confirmed that the candidate's three binaries match the
current `build/n2-neverdead` binaries. Launcher data/cache live separately under
`%LOCALAPPDATA%/NeverDeadPort`; historical warm-cache benchmarks are not an
equivalent comparison. Preserve the user's saves and cache when investigating.

Next: inspect and reproduce the missing guest function boundary, validate the
same transition after correction, then measure equivalent cold/warm gameplay.
Prerelease acceptance remains blocked. No fix has been verified for this crash.
