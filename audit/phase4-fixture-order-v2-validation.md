# Fixture order v2 validation

- version: `andes_interleaved_v2`
- seed: `0xa4de5302`
- count: 300
- gates.ok: **true**
- failures: none
- categoryCounts: {"item":130,"multi_mixed":30,"position":80,"multi_false":30,"multi_true":30}

## Planner

Global under-representation deficit (not largest-pile-first). Soft P→I cadence. Band proportional floors (~45% of expected).

## Bands

```
band,position,item,multi_true,multi_mixed,multi_false,other
1-50,13,22,5,5,5,0
51-100,14,21,5,5,5,0
101-150,13,22,5,5,5,0
151-200,13,22,5,5,5,0
201-250,14,21,5,5,5,0
251-300,13,22,5,5,5,0
```

## Tail (last 20)

`item,multi_mixed,item,position,item,multi_false,position,item,multi_true,item,position,item,multi_mixed,position,item,multi_false,item,position,item,multi_true`
