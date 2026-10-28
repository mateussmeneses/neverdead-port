# PPC 0x825D5770 investigation (incomplete)

Baseline: `617822a58cb775ca39c135ac17f886834d2f34c6`.
Branch: `fix/ppc-cutscene-825d5770`.

## Observations from existing generated artifacts

- `src/generated/default/codegen.partition.json` includes `825D5760` and
  `825D5780`, but not `825D5770`. The registration and init tables likewise
  omit the fatal target. This is not proof of the target's extent.
- `neverdead_recomp.95.cpp` sets LR to `0x821F083C` immediately before
  `REX_CALL_INDIRECT_FUNC(ctx.ctr.u32)`. Its target comes from a load at byte
  offset 76 of the table loaded from `r31 + 0`. The generated sequence moves
  `r31` into `r3` and points `r4` at stack offset 96 before this call.
- Neighbor `sub_825D5760` in shard 48 loads `r11` from `r3 - 4`, subtracts
  it from `r3`, subtracts 152, then tail-calls `sub_8236F580`.
  This neighboring adjustor does not establish the missing target's body.
- Dispatcher `GetFunction` checks its flat table then its address map; the
  current generated registration list has no entry for the failing address.
  No evidence yet demonstrates corruption of either dispatcher table.

These are observations of previously generated C++, not freshly verified PPC
disassembly. The codegen stamp records fingerprint
`fa4bd2838272ac523bc96ac4e6099ad1`; it is not the XEX SHA-256.

## Missing evidence

The manifest and codegen dependency file both point to
`C:/projetos/neverdeadxex/default.xex`, which is absent in the current environment.
The requested original SHA-256 cannot currently be verified. Original bytes,
`.pdata`, incoming vtable references and surrounding branch targets remain
unverified. Do not infer a 16-byte function from the gap or copy a neighbor.

No correction, codegen, build or transition replay has been performed. The
manual fatal remains the runtime failure evidence; regression acceptance is
pending access to the matching XEX and the same gameplay transition.
