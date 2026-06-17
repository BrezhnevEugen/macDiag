# CBF output-parameter format (authoritative)

Reverse-engineered against **jglim/CaesarSuite** (the CBF parser reversed from
`c32s.dll`) and cross-checked with **rnd-ash/OpenVehicleDiag**. This is the
source of truth for decoding measurement/output parameters correctly. It
supersedes the name-heuristic (`presentation_meta`) and the old
`_diag_output_layout` hack in `tools/caesar_vc.py`.

References:
- https://github.com/jglim/CaesarSuite — `Caesar/Caesar/{ECU,DiagService,DiagPreparation,DiagPresentation,Scale}.cs`
- https://github.com/rnd-ash/OpenVehicleDiag — independent Rust CBF parser

The unlock/security tooling (https://github.com/jglim/UnlockECU,
https://github.com/jglim/SecurityAccessQuery) is a *separate* concern (gaining
access to protected services), not output decoding.

## The decode chain

```
ECU header (pool triples) ─► Presentations pool ─► DiagPresentation
                                                     (TypeLength, ByteOrder,
                                                      SignBit, Scale, Unit)
DiagService ─► W_OutPres list ─► DiagPreparation ─► presentation ref
                                  (bitPos, ModeConfig, PresPoolIndex)
```

A parameter is read at `bitPos`, `width` bits wide, in `ByteOrder`, interpreted
as signed/unsigned per `SignBit`, then `value * factor + offset`, displayed with
`Unit`.

## ECU header pool triples (extended bitflags)

Our `_ecu_vc_pool` already parses fields 1..36 and stops at VcDomain. After
VcDomain each pool is a **4-field** descriptor (Offset, EntryCount, EntrySize,
BlockSize); `*_BlockOffset` is relative and needs `+ dataBufferOffset`
(`StringPoolSize + StubHeaderSize + CffHeaderSize + 4`, = our `data_buffer`):

```
... VcDomain(Offset,Count,Size,BlockSize),
    Presentations(Offset,Count,Size,BlockSize),
    InternalPresentations(Offset,Count,Size,BlockSize),
    Unk(...), Unk39
```

So `Presentations_BlockOffset` is the field after `VcDomain_BlockSize`.

## Presentations pool

`ReadEcuPool(BlockOffset, EntryCount, EntrySize)`; each entry is 8 bytes
(`offset` i32, `size` i32). A `DiagPresentation` lives at
`offset + Presentations_BlockOffset`.

### DiagPresentation body

Header is **u32 main bitflag + u16 extended** (the fields we need are all in the
first 32 bits). Bitflag field order (CaesarReader-style; each may be absent):

| # | field | type | meaning |
|--:|---|---|---|
| 1 | Qualifier | str | `PRES_*` name |
| 2 | Description_CTF | i32 | |
| 3 | ScaleTableOffset | i32 | scale records |
| 4 | ScaleCountMaybe | i32 | scale count |
| 5–12 | Unk5..UnkC | i32 | |
| 13–15 | UnkD..UnkF | i16 | |
| 16 | DisplayedUnit_CTF | i32 | **unit** (CTF) |
| 17–25 | Unk11,Unk12,EnumMaxValue,Unk14,Unk15,Description2,Unk17..19 | i32 | |
| 26 | **TypeLength_1A** | i32 | width (see Type_1C) |
| 27 | InternalDataType | i8 | |
| 28 | **Type_1C** | i8 | if `0`, TypeLength is **bytes** → ×8 for bits |
| 29 | Unk1d | i8 | |
| 30 | **SignBit** | i8 | `1`/`2` = signed |
| 31 | **ByteOrder** | i8 | unset/`0` = HiLo (**big-endian**), `1` = LoHi (little-endian) |
| 33 | TypeLengthBytesMaybe_21 | i32 | fallback width |

`width_bits = (Type_1C == 0) ? TypeLength_1A * 8 : TypeLength_1A`
(fallback to `TypeLengthBytesMaybe_21` when `TypeLength_1A <= 0`).

Scale (factor/offset) lives at `ScaleTableOffset`; applied as
`value = value * MultiplyFactor + AddConstOffset` (see `Scale.cs`).

## DiagService output presentations (W_OutPres)

After `RequestBytes_*`, the DiagService header has `W_OutPres_Count` /
`W_OutPres_Offset`. Two levels:

- **Outer** at `BaseAddress + W_OutPres_Offset + presIndex*8`: `count` i32,
  `offset` i32.
- **Inner** table at `outerBase + offset`, entries of **10 bytes**:
  `prepOffset` i32, `bitPos` i32, `mode` (ModeConfig) u16. The `DiagPreparation`
  body is at `innerBase + prepOffset`.

### DiagPreparation body (size source)

Body fields: Qualifier, Name_CTF, Unk1, Unk2, AlternativeBitWidth, IITOffset,
InfoPoolIndex, **PresPoolIndex**, Field1E, SystemParam, DumpMode, DumpSize, Dump.

`GetSizeInBits(ModeConfig)` (`IntegerSizeMapping = {0,1,4,8,16,32,64}` bits, =
our `FRAG_LEN_TABLE`):
- `(mode & 0xF00)==0x300`: `0x320`→`IntegerSizeMapping[mode&0xF]`,
  `0x330`→`AlternativeBitWidth`.
- special (`SystemParam==-1`): `modeE 0x2000`→`GlobalPresentations[PresPoolIndex]`
  TypeLength; `0x8000`→`GlobalInternalPresentations[InfoPoolIndex]`.
- `0x420`→`IntegerSizeMapping[mode&0xF]`, `0x430`→`AlternativeBitWidth`,
  `0x410`→extended bit-dump (rest of response).

## Validation (CEPC_MFA, from CBF only)

- W_OutPres `bitPos` == our stored `bit_pos`: **982/982** (positions already
  correct; the old `bit_len` was a constant, not a width — see ROADMAP).
- Presentations pool parsed: **539** presentations, all qualifiers resolve.
- **ByteOrder: 539/539 = 0 (big-endian)** → `int.from_bytes(...,'big')` is
  correct here; other ECUs may carry `1` (little-endian) and must be honored.
- **SignBit: 512 unsigned, 27 signed** (authoritative; beats name heuristics).
- **TypeLength vs heuristic byte_len: mismatches are heuristic errors**, e.g.
  `PRES_DC_CNTR_U8` (real 1B, heuristic 2B), `PRES_DC_DST_KM` (real 4B, heuristic
  2B), `PRES_ENVCOND_*_STATE` (real 1B, heuristic 2B).

## Implementation plan

1. `caesar_vc.py`: extend ECU-header parse to `Presentations_BlockOffset/Count/
   Size`; add `_diag_presentations()` (pool → DiagPresentation: width_bits,
   signed, byte_order, unit, factor/offset) keyed by index and qualifier.
2. Parse `W_OutPres`/`DiagPreparation` for real `bitPos` + `PresPoolIndex`,
   resolve the presentation; keep `GetSizeInBits` for inline integer modes.
3. `build_measure_db`: store authoritative `byte_len`, `byte_order`, `signed`,
   `unit`, `formula` per output (schema bump); drop the dead `bit_len`.
4. Backend `_raw_value`: honor `byte_order` (big/little) and `signed` from the
   DB instead of heuristics; never emit a value when width is unknown.
5. Rebuild `measurements.sqlite`; the stride guard and new per-field tests
   confirm no regression.
