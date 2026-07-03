# Debug Session: og-root-link-error
- **Status**: [OPEN]
- **Issue**: Converted `cola_can_og.usd` still triggers OmniGibson `Exactly one single root link should have been found` when loaded as `USDObject`.
- **Debug Server**: N/A
- **Log File**: N/A

## Reproduction Steps
1. Load `cola_can_og.usd` in the user's OmniGibson environment as a `USDObject`.
2. Observe the assertion from `entity_prim.py` about root link detection.

## Hypotheses & Verification
| ID | Hypothesis | Likelihood | Effort | Evidence |
|----|------------|------------|--------|----------|
| A | OG identifies links by a stricter schema or metadata than only `PhysicsRigidBodyAPI`, so `root_link` is ignored. | High | Low | Pending |
| B | The default prim / referenced hierarchy shape is still incompatible, so OG traverses into the referenced subtree and finds zero valid root links. | High | Low | Pending |
| C | The collision / visuals split is incomplete, and OG rejects the link before root-link selection. | Medium | Medium | Pending |
| D | OG expects a specific prim naming or `xformOp` / reset stack pattern for single-link objects. | Medium | Medium | Pending |
| E | The wrapper USDA syntax is valid USD, but not authored in the exact composed form that Isaac / OG expects for applied APIs on referenced meshes. | Medium | Medium | Pending |

## Log Evidence
- Source inspection: OmniGibson `EntityPrim.update_links()` determines links only from the object's immediate child prims whose type is `Xform`, then requires exactly one root link candidate after excluding joint-children.
- Source inspection: `RigidPrim.update_meshes()` classifies descendant meshes as collision meshes when `CollisionAPI` is applied.
- Runtime evidence from user: USDA parser fails inside `cola_can.usd` at line 94 while composing `base_link`, with messages about attribute type / variability conflicts.
- Local file inspection: the failing material section used non-ASCII shader prim names (`原理化_BSDF`, `图像纹理`) in both `def Shader` and connection paths.
- Runtime evidence from user: after fixing shader names, OG proceeds further and now fails when constructing `MaterialPrim` for `/test_0/base_link/_materials/Body_1`, because every relative prim path component must start with a letter.
- Local file inspection: Blender export created a material scope named `_materials`, which violates OmniGibson's `PrimBase` naming assertion.
- Runtime evidence from user: after fixing `_materials`, environment construction succeeds and the failure moves to `env.step()`, specifically `object_states/toggle.py -> RigidContactAPI.get_all_impulses()`, with PhysX reporting `Simulation view object is invalidated`.
- Local script inspection: the user's `test/test.py` explicitly enables `gm.ENABLE_OBJECT_STATES = True` and `gm.ENABLE_TRANSITION_RULES = True`, and also binds `R` to `env.reset()`, all of which exercise the older v3.7.1 contact-view path.

## Verification Conclusion
- Static source evidence supports Hypothesis A and B as most likely, but runtime evidence from the user's OG environment is still pending.
- A second conversion variant was generated that reduces the hierarchy to `object -> base_link -> referenced geometry`, with collision APIs authored directly on the descendant meshes.
- New evidence strongly supports an additional root cause: Blender-exported non-ASCII shader prim names are not being parsed robustly in the user's USD / Isaac / OG stack, so the material subtree must be ASCII-normalized first.
- New evidence also confirms Hypothesis E: the wrapped asset still carries source-authored prim names that violate OmniGibson naming assumptions, so the material scope had to be renamed from `_materials` to `materials`.
- New evidence narrows the remaining runtime problem to the BEHAVIOR state / transition stack rather than the custom USD itself; for smoke-testing the converted asset, the test driver should disable object states, transition rules, and hot-reset.
