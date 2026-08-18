---
name: codebase-design
description: Architecture vocabulary and design principles for building deep, testable modules. Use when designing interfaces, reviewing architecture, or deepening modules.
---

# Codebase Design

Vocabulary and principles for designing deep, testable modules with well-placed seams.

## Vocabulary

**Module** — a cohesive body of code behind an interface. Distinct from "file" (a physical boundary, not a logical one). A module can span files, or one file can host multiple modules.

**Interface** — the surface a module presents to the world: everything a caller must know to use it (signatures, types, error modes, ordering invariants, side effects).

**Depth** — leverage at the interface: the amount of behaviour a caller (or test) can exercise per unit of interface they have to learn. A module is **deep** when a large amount of behaviour sits behind a small interface, **shallow** when the interface is nearly as complex as the implementation.

**Seam** — a place where you can alter behaviour without editing in that place; the *location* at which a module's interface lives.

**Adapter** — a concrete thing that satisfies an interface at a seam.

**Leverage** — what callers get from depth: more capability per unit of interface they learn.

**Locality** — what maintainers get from depth: change, bugs, knowledge, and verification concentrate in one place.

## Deep vs Shallow

- **Deep module**: Small interface + lot of implementation capability
- **Shallow module**: Large interface + thin implementation (avoid)

## Principles

1. **Depth is a property of the interface, not the implementation.**
2. **The deletion test:** Imagine deleting the module. If complexity vanishes, it was a pass-through. If complexity reappears across callers, it was earning its keep.
3. **The interface is the test surface:** Callers and tests cross the same seam.
4. **One adapter means a hypothetical seam. Two adapters means a real one.**
